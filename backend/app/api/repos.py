from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.models.base import get_db
from app.models.repo import Repo
from app.models.schemas import RepoCreate, RepoResponse

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
