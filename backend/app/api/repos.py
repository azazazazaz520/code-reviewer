import shutil
import subprocess
import uuid as uuid_mod
import os
from datetime import datetime, UTC
from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.config import settings
from app.models.base import get_db
from app.models.repo import Repo, RepositoryRef
from app.models.schemas import (
    BranchItem,
    CommitItem,
    PRItem,
    RepoCreate,
    RepoResponse,
    SyncResponse,
    WorkspaceRepoCreate,
)
from app.engine.snapshot import SnapshotError, validate_workspace_path
from app.services.git_host import GitHostError, get_open_pulls, parse_git_repository
from app.services.repo_sync import (
    RepoSyncError,
    persist_sync_result,
    resolve_remote_branch,
    sync_repository,
)

router = APIRouter(prefix="/api/repos", tags=["repos"])


def _validate_clone_url(git_url: str) -> str:
    """仅允许远程 Git 地址，避免将用户输入解释为 git 选项。"""
    value = git_url.strip()
    if (
        not value
        or value.startswith("-")
        or any(character.isspace() or ord(character) < 32 for character in value)
    ):
        raise HTTPException(status_code=400, detail="Git 仓库地址格式无效")

    if value.startswith(("http://", "https://")):
        try:
            parsed = urlparse(value)
            hostname = parsed.hostname
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Git 仓库地址格式无效") from exc
        if not parsed.netloc or not hostname:
            raise HTTPException(status_code=400, detail="Git 仓库地址格式无效")
    elif value.startswith("git@"):  # SCP 风格 SSH 地址，例如 git@host:owner/repo.git
        host_and_path = value[4:]
        if ":" not in host_and_path or not all(host_and_path.split(":", 1)):
            raise HTTPException(status_code=400, detail="Git 仓库地址格式无效")
    else:
        raise HTTPException(status_code=400, detail="Git 仓库地址格式无效")

    return value


@router.get("", response_model=list[RepoResponse])
def list_repos(db: Session = Depends(get_db)):
    return db.query(Repo).order_by(Repo.created_at.desc()).all()


@router.post("", response_model=RepoResponse, status_code=201)
def create_repo(body: RepoCreate, db: Session = Depends(get_db)):
    git_url = _validate_clone_url(body.git_url)

    # 确定 clone 目标目录
    repo_uuid = str(uuid_mod.uuid4())
    clone_dir = Path(settings.repos_dir) / repo_uuid
    clone_dir.mkdir(parents=True, exist_ok=True)

    # 构造 clone URL（私有 GitHub/Gitee 仓库注入对应 token）
    clone_url = git_url
    try:
        clone_url = parse_git_repository(git_url).clone_url(git_url)
    except GitHostError:
        # 保持本地/其他 Git 远程地址的原有 clone 能力；仅 PR API 需要受支持的平台。
        pass

    # 执行 clone
    result = subprocess.run(
        ["git", "clone", "--", clone_url, str(clone_dir)],
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


@router.post("/workspace", response_model=RepoResponse, status_code=201)
def register_workspace_repo(
    body: WorkspaceRepoCreate,
    db: Session = Depends(get_db),
):
    """登记用户选择的本地 Git 工作区，避免将其当作远程仓库重新 clone。"""
    try:
        workspace_root = Path(validate_workspace_path(body.path)).resolve()
    except SnapshotError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    existing = db.query(Repo).filter(Repo.local_path == str(workspace_root)).first()
    if existing:
        return existing

    repo = Repo(
        id=str(uuid_mod.uuid4()),
        name=(body.name or workspace_root.name or "本地工作区").strip(),
        git_url="",
        local_path=str(workspace_root),
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


@router.put("/{repo_id}/workspace", response_model=RepoResponse)
def update_workspace_repo(
    repo_id: str,
    body: WorkspaceRepoCreate,
    db: Session = Depends(get_db),
):
    """更新已登记本地仓库的名称或工作区路径。"""
    repo = db.query(Repo).filter(Repo.id == repo_id).first()
    if not repo:
        raise HTTPException(status_code=404, detail="仓库不存在")

    try:
        workspace_root = Path(validate_workspace_path(body.path)).resolve()
    except SnapshotError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    existing = (
        db.query(Repo)
        .filter(Repo.local_path == str(workspace_root), Repo.id != repo_id)
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="该本地工作区已经添加")

    repo.name = (body.name or workspace_root.name or "本地工作区").strip()
    repo.git_url = ""
    repo.local_path = str(workspace_root)
    db.commit()
    db.refresh(repo)
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


@router.post("/{repo_id}/sync", response_model=SyncResponse)
def sync_repo(repo_id: str, db: Session = Depends(get_db)):
    """同步远程仓库并保存远程分支头快照。"""
    repo = db.query(Repo).filter(Repo.id == repo_id).first()
    if not repo:
        raise HTTPException(status_code=404, detail="仓库不存在")

    checked_at = datetime.now(UTC)
    repo.sync_status = "syncing"
    repo.sync_error = None
    db.commit()
    try:
        result = sync_repository(repo.local_path)
    except RepoSyncError as exc:
        repo.sync_status = "failed"
        repo.sync_error = str(exc)
        db.commit()
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    previous = persist_sync_result(db, repo, result, checked_at)
    branch_items: list[BranchItem] = []
    for branch in result.branches:
        old_revision = previous.get(branch.name)
        branch_items.append(
            BranchItem(
                name=branch.name,
                head_revision=branch.head_revision,
                previous_revision=old_revision,
                has_new_commits=bool(old_revision and old_revision != branch.head_revision),
            )
        )

    db.commit()
    return SyncResponse(
        status="ready",
        checked_at=checked_at,
        default_branch=result.default_branch,
        branches=sorted(branch_items, key=lambda item: item.name),
    )


@router.get("/{repo_id}/branches", response_model=list[BranchItem])
def list_branches(repo_id: str, db: Session = Depends(get_db)):
    """读取最近一次同步得到的远程分支，不触发网络操作。"""
    repo = db.query(Repo).filter(Repo.id == repo_id).first()
    if not repo:
        raise HTTPException(status_code=404, detail="仓库不存在")
    refs = (
        db.query(RepositoryRef)
        .filter(RepositoryRef.repo_id == repo.id)
        .order_by(RepositoryRef.name.asc())
        .all()
    )
    return [BranchItem(name=ref.name, head_revision=ref.head_revision) for ref in refs]


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
    """将 UI 分支名解析为 origin 远程跟踪引用。"""
    try:
        resolve_remote_branch(local_path, branch)
    except RepoSyncError as exc:
        raise HTTPException(status_code=400, detail=f"分支不存在或不可用: {branch}") from exc
    return f"refs/remotes/origin/{branch.removeprefix('origin/').strip()}"
