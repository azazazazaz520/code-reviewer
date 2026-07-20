import re
import subprocess
import os

import requests
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.models.base import get_db
from app.models.repo import Repo
from app.models.schemas import PRItem, CommitItem, RepoCreate, RepoResponse

router = APIRouter(prefix="/api/repos", tags=["repos"])


@router.get("", response_model=list[RepoResponse])
def list_repos(db: Session = Depends(get_db)):
    return db.query(Repo).order_by(Repo.created_at.desc()).all()


@router.post("", response_model=RepoResponse, status_code=201)
def create_repo(body: RepoCreate, db: Session = Depends(get_db)):
    repo = Repo(
        name=body.name,
        git_url=body.git_url,
        local_path=body.local_path,
        default_branch=body.default_branch,
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
    repo.local_path = body.local_path
    repo.default_branch = body.default_branch
    db.commit()
    db.refresh(repo)
    return repo


@router.get("/{repo_id}/prs", response_model=list[PRItem])
def list_prs(repo_id: str, db: Session = Depends(get_db)):
    """获取仓库的 Open PR 列表（通过 GitHub API）。"""
    repo = db.query(Repo).filter(Repo.id == repo_id).first()
    if not repo:
        raise HTTPException(status_code=404, detail="仓库不存在")

    if not settings.github_token:
        raise HTTPException(status_code=400, detail="未配置 GitHub Token，无法获取 PR 列表")

    # 从 git_url 解析 owner/repo
    # 支持格式: https://github.com/owner/repo.git 或 git@github.com:owner/repo.git
    match = re.search(r"github\.com[/:](.+?)/(.+?)(?:\.git)?$", repo.git_url)
    if not match:
        raise HTTPException(status_code=400, detail="无法从 git_url 解析 GitHub owner/repo")

    owner, repo_name = match.group(1), match.group(2)

    try:
        resp = requests.get(
            f"https://api.github.com/repos/{owner}/{repo_name}/pulls",
            params={"state": "open", "per_page": 20, "sort": "updated", "direction": "desc"},
            headers={
                "Authorization": f"Bearer {settings.github_token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=15,
        )

        if resp.status_code == 403 and "rate limit" in resp.text.lower():
            raise HTTPException(status_code=429, detail="GitHub API 限流，请稍后重试或手动输入 PR 号")

        if resp.status_code == 401:
            raise HTTPException(status_code=400, detail="GitHub Token 无效")

        resp.raise_for_status()
        pulls = resp.json()

        return [
            PRItem(
                number=p["number"],
                title=p["title"],
                author=p["user"]["login"] if p.get("user") else "unknown",
                branch=p["head"]["ref"],
                created_at=p["created_at"],
            )
            for p in pulls
        ]
    except (requests.RequestException, ValueError) as e:
        raise HTTPException(status_code=502, detail=f"GitHub API 请求失败: {str(e)}")


@router.get("/{repo_id}/commits", response_model=list[CommitItem])
def list_commits(repo_id: str, limit: int = 20, db: Session = Depends(get_db)):
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
        result = subprocess.run(
            ["git", "-C", local_path, "log", f"-{limit}", "--format=%H%x00%s%x00%an%x00%aI"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
        )
        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            raise HTTPException(status_code=500, detail=f"git log 执行失败: {stderr}")

        if not result.stdout:
            return []

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
