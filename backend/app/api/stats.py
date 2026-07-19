from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.base import get_db
from app.models.repo import Repo, ReviewTask, ReviewReport
from app.models.schemas import (
    ReviewTaskResponse,
    OverviewStats,
    RepoStats,
    HotspotItem,
)
from app.api.reviews import ReviewTaskResponse

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("/overview", response_model=OverviewStats)
def get_overview(db: Session = Depends(get_db)):
    """全局统计总览：总审查次数、本月审查次数、风险分布等。"""
    total = db.query(func.count(ReviewTask.id)).scalar() or 0
    active_repos = db.query(func.count(Repo.id)).scalar() or 0

    # 本月审查次数
    from datetime import datetime, UTC

    now = datetime.now(UTC)
    this_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    monthly = (
        db.query(func.count(ReviewTask.id))
        .filter(ReviewTask.created_at >= this_month_start)
        .scalar()
        or 0
    )

    # 风险分布
    reports = db.query(ReviewReport).all()
    risk_dist = {"low": 0, "medium": 0, "high": 0, "critical": 0}
    for r in reports:
        risk_dist[r.risk_level] = risk_dist.get(r.risk_level, 0) + 1

    avg_risk = "low"
    if risk_dist.get("critical", 0) > 0:
        avg_risk = "critical"
    elif risk_dist.get("high", 0) > 0:
        avg_risk = "high"
    elif risk_dist.get("medium", 0) > 0:
        avg_risk = "medium"

    # 最近审查
    recent = (
        db.query(ReviewTask, Repo.name)
        .join(Repo, ReviewTask.repo_id == Repo.id)
        .order_by(ReviewTask.created_at.desc())
        .limit(10)
        .all()
    )

    recent_with_names = []
    for task, repo_name in recent:
        item = ReviewTaskResponse.model_validate(task)
        item.repo_name = repo_name
        recent_with_names.append(item)

    return OverviewStats(
        total_reviews=total,
        reviews_this_month=monthly,
        avg_risk_level=avg_risk,
        active_repos=active_repos,
        risk_distribution=risk_dist,
        recent_reviews=recent_with_names,
    )


@router.get("/repos/{repo_id}", response_model=RepoStats)
def get_repo_stats(repo_id: str, db: Session = Depends(get_db)):
    """单仓库统计。"""
    total = (
        db.query(func.count(ReviewTask.id))
        .filter(ReviewTask.repo_id == repo_id)
        .scalar()
        or 0
    )

    reports = (
        db.query(ReviewReport)
        .join(ReviewTask)
        .filter(ReviewTask.repo_id == repo_id)
        .all()
    )

    risk_dist = {"low": 0, "medium": 0, "high": 0, "critical": 0}
    for r in reports:
        risk_dist[r.risk_level] = risk_dist.get(r.risk_level, 0) + 1

    # 热点文件（TODO: 等 Review Report 有文件级统计后补充）
    hotspots: list[HotspotItem] = []

    recent = (
        db.query(ReviewTask)
        .filter(ReviewTask.repo_id == repo_id)
        .order_by(ReviewTask.created_at.desc())
        .limit(10)
        .all()
    )

    return RepoStats(
        total_reviews=total,
        risk_distribution=risk_dist,
        hotspots=hotspots,
        recent_reviews=[ReviewTaskResponse.model_validate(r) for r in recent],
    )
