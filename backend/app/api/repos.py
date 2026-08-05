import shutil
import subprocess
import uuid as uuid_mod
import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.config import settings
from app.models.base import get_db
from app.models.repo import Repo
from app.models.schemas import BranchItem, PRItem, CommitItem, RepoCreate, RepoResponse
from app.services.git_host import GitHostError, get_open_pulls, parse_git_repository

router = APIRouter(prefix="/api/repos", tags=["repos"])


@router.get("", response_model=list[RepoResponse])
def list_repos(db: Session = Depends(get_db)):
    return db.query(Repo).order_by(Repo.created_at.desc()).all()


@router.post("", response_model=RepoResponse, status_code=201)
def create_repo(body: RepoCreate, db: Session = Depends(get_db)):
    # 确定 clone 目标目录
    repo_uuid = str(uuid_mod.uuid4())
    clone_dir = Path(settings.repos_dir) / repo_uuid
    clone_dir.mkdir(parents=True, exist_ok=True)

    # 构造 clone URL（私有 GitHub/Gitee 仓库注入对应 token）
    clone_url = body.git_url
    try:
        clone_url = parse_git_repository(body.git_url).clone_url(body.git_url)
    except GitHostError:
        # 保持本地/其他 Git 远程地址的原有 clone 能力；仅 PR API 需要受支持的平台。
        pass

    # 执行 clone
    result = subprocess.run(
        ["git", "clone", clone_url, str(clone_dir)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
    )
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        # 清理失败的空目录
        if clone_dir.exists():
            shutil.rmtree(clone_dir)
        raise HTTPException(status_code=400, detail=f"Git clone 失败: {stderr}")

    repo = Repo(
        id=repo_uuid,
        name=body.name,
        git_url=body.git_url,
        local_path=str(clone_dir.resolve()),
    )
    db.add(repo)
    db.commit()
    db.refresh(repo)
    return repo


@router.get("/{repo_id}", response_model=RepoResponse)
def get_repo(repo_id: str, db: Session = Depends(get_db)):
    repo = db.query(Repo).filter(Repo.id == repo_id).first()
    if not repo:
        raise HTTPException(status_code=404, detail="仓库不存在")
    return repo


@router.delete("/{repo_id}", status_code=204)
def delete_repo(repo_id: str, db: Session = Depends(get_db)):
    repo = db.query(Repo).filter(Repo.id == repo_id).first()
    if not repo:
        raise HTTPException(status_code=404, detail="仓库不存在")
    db.delete(repo)
    db.commit()


@router.put("/{repo_id}", response_model=RepoResponse)
def update_repo(repo_id: str, body: RepoCreate, db: Session = Depends(get_db)):
    repo = db.query(Repo).filter(Repo.id == repo_id).first()
    if not repo:
        raise HTTPException(status_code=404, detail="仓库不存在")
    repo.name = body.name
    repo.git_url = body.git_url
    if body.local_path is not None:
        repo.local_path = body.local_path
    db.commit()
    db.refresh(repo)
    return repo


@router.get("/{repo_id}/branches", response_model=list[BranchItem])
def list_branches(repo_id: str, db: Session = Depends(get_db)):
    """获取本地 clone 中可用于审查的分支。"""
    repo = db.query(Repo).filter(Repo.id == repo_id).first()
    if not repo:
        raise HTTPException(status_code=404, detail="仓库不存在")

    if not os.path.isdir(repo.local_path):
        raise HTTPException(status_code=400, detail=f"本地路径不存在: {repo.local_path}")

    fetch_error: str | None = None
    try:
        fetch_result = subprocess.run(
            ["git", "-C", repo.local_path, "fetch", "--all", "--prune"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
        )
        if fetch_result.returncode != 0:
            fetch_error = (fetch_result.stderr or "").strip()
    except subprocess.TimeoutExpired:
        fetch_error = "git fetch 执行超时"

    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                repo.local_path,
                "for-each-ref",
                "--format=%(refname:short)",
                "refs/heads",
                "refs/remotes/origin",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=500, detail="读取分支列表超时")

    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        raise HTTPException(status_code=500, detail=f"读取分支列表失败: {stderr}")

    branches: list[str] = []
    for raw_name in result.stdout.splitlines():
        name = raw_name.strip()
        if not name or name.endswith("/HEAD"):
            continue
        if name.startswith("origin/"):
            name = name.removeprefix("origin/")
        if name not in branches:
            branches.append(name)

    if not branches and fetch_error:
        raise HTTPException(status_code=502, detail=f"无法同步仓库分支: {fetch_error}")

    return [BranchItem(name=name) for name in sorted(branches)]


@router.get("/{repo_id}/prs", response_model=list[PRItem])
def list_prs(repo_id: str, db: Session = Depends(get_db)):
    """获取仓库的 Open PR 列表（通过 GitHub 或 Gitee API）。"""
    repo = db.query(Repo).filter(Repo.id == repo_id).first()
    if not repo:
        raise HTTPException(status_code=404, detail="仓库不存在")

    try:
        pulls = get_open_pulls(repo.git_url)

        return [
            PRItem(
                number=p["number"],
                title=p["title"],
                author=(p.get("user") or {}).get("login") or (p.get("user") or {}).get("name") or "unknown",
                branch=((p.get("head") or {}).get("ref") or (p.get("head") or {}).get("label") or "unknown"),
                created_at=p["created_at"],
            )
            for p in pulls
        ]
    except GitHostError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/{repo_id}/commits", response_model=list[CommitItem])
def list_commits(
    repo_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    branch: str | None = Query(default=None, max_length=200),
    db: Session = Depends(get_db),
):
    """获取仓库本地最近 N 条 commit（通过 git log）。"""
    repo = db.query(Repo).filter(Repo.id == repo_id).first()
    if not repo:
        raise HTTPException(status_code=404, detail="仓库不存在")

    local_path = repo.local_path
    if not local_path:
        raise HTTPException(status_code=400, detail="仓库未配置本地路径")

    if not os.path.isdir(local_path):
        raise HTTPException(status_code=400, detail=f"本地路径不存在: {local_path}")

    try:
        ref = _resolve_branch_ref(local_path, branch) if branch else "HEAD"
        result = subprocess.run(
            [
                "git",
                "-C",
                local_path,
                "log",
                ref,
                f"-{limit}",
                "--format=%H%x00%s%x00%an%x00%aI",
                "--",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
        )
        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            if branch:
                raise HTTPException(status_code=400, detail=f"分支不存在或不可用: {branch}")
            raise HTTPException(status_code=500, detail=f"git log 执行失败: {stderr}")

        commits: list[CommitItem] = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split("\0")
            if len(parts) < 4:
                continue
            full_hash, message, author, date_str = parts[0], parts[1], parts[2], parts[3]
            commits.append(CommitItem(
                hash=full_hash,
                short_hash=full_hash[:7],
                message=message,
                author=author,
                date=date_str,
            ))

        return commits
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=500, detail="git log 执行超时")


def _resolve_branch_ref(local_path: str, branch: str) -> str:
    """将 UI 展示的分支名解析为本地或 origin 远端 ref。"""
    candidates = [branch] if branch.startswith("origin/") else [branch, f"origin/{branch}"]
    for candidate in candidates:
        result = subprocess.run(
            ["git", "-C", local_path, "rev-parse", "--verify", f"{candidate}^{{commit}}"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
        )
        if result.returncode == 0:
            return candidate
    raise HTTPException(status_code=400, detail=f"分支不存在或不可用: {branch}")
