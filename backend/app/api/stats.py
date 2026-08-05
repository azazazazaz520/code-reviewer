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
    HeatmapResponse,
    HeatmapRepoRow,
    HeatmapCell,
)
from app.api.reviews import ReviewTaskResponse

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("/overview", response_model=OverviewStats)
def get_overview(db: Session = Depends(get_db)):
    """全局统计总览：总审查次数、本月审查次数、风险分布等。"""
    active_filter = ReviewTask.archived_at.is_(None)
    total = db.query(func.count(ReviewTask.id)).filter(active_filter).scalar() or 0
    active_repos = db.query(func.count(Repo.id)).scalar() or 0

    # 本月审查次数
    from datetime import datetime, UTC

    now = datetime.now(UTC)
    this_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    monthly = (
        db.query(func.count(ReviewTask.id))
        .filter(ReviewTask.created_at >= this_month_start, active_filter)
        .scalar()
        or 0
    )

    # 风险分布
    reports = (
        db.query(ReviewReport)
        .join(ReviewTask)
        .filter(active_filter)
        .all()
    )
    risk_dist = {"low": 0, "medium": 0, "high": 0, "critical": 0}
    for r in reports:
        risk_dist[r.risk_level] = risk_dist.get(r.risk_level, 0) + 1

    # 最近审查（JOIN repo 获取 repo_name，LEFT JOIN report 获取 risk_level）
    recent_rows = (
        db.query(ReviewTask, Repo.name, ReviewReport.risk_level)
        .join(Repo, ReviewTask.repo_id == Repo.id)
        .outerjoin(ReviewReport, ReviewReport.task_id == ReviewTask.id)
        .filter(active_filter)
        .order_by(ReviewTask.created_at.desc())
        .limit(10)
        .all()
    )

    recent_with_names = []
    for task, repo_name, risk_level in recent_rows:
        item = ReviewTaskResponse.model_validate(task)
        item.repo_name = repo_name
        item.risk_level = risk_level
        recent_with_names.append(item)

    return OverviewStats(
        total_reviews=total,
        reviews_this_month=monthly,
        active_repos=active_repos,
        risk_distribution=risk_dist,
        recent_reviews=recent_with_names,
    )


@router.get("/repos/{repo_id}", response_model=RepoStats)
def get_repo_stats(repo_id: str, db: Session = Depends(get_db)):
    """单仓库统计。"""
    total = (
        db.query(func.count(ReviewTask.id))
        .filter(ReviewTask.repo_id == repo_id, ReviewTask.archived_at.is_(None))
        .scalar()
        or 0
    )

    reports = (
        db.query(ReviewReport)
        .join(ReviewTask)
        .filter(ReviewTask.repo_id == repo_id, ReviewTask.archived_at.is_(None))
        .all()
    )

    risk_dist = {"low": 0, "medium": 0, "high": 0, "critical": 0}
    for r in reports:
        risk_dist[r.risk_level] = risk_dist.get(r.risk_level, 0) + 1

    # 热点文件（TODO: 等 Review Report 有文件级统计后补充）
    hotspots: list[HotspotItem] = []

    recent = (
        db.query(ReviewTask)
        .filter(ReviewTask.repo_id == repo_id, ReviewTask.archived_at.is_(None))
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


@router.get("/heatmap", response_model=HeatmapResponse)
def get_heatmap(db: Session = Depends(get_db)):
    """仓库×月份 风险热力图数据。"""
    from collections import defaultdict

    # 获取所有 repos
    repos = db.query(Repo).order_by(Repo.name).all()

    # Get all completed reviews with their risk_level (one row per review, no GROUP BY)
    rows = (
        db.query(
            ReviewTask.repo_id,
            Repo.name,
            ReviewTask.completed_at,
            ReviewReport.risk_level,
        )
        .join(Repo, ReviewTask.repo_id == Repo.id)
        .join(ReviewReport, ReviewReport.task_id == ReviewTask.id)
        .filter(ReviewTask.status == "done", ReviewTask.archived_at.is_(None))
        .order_by(ReviewTask.repo_id, func.strftime("%Y-%m", ReviewTask.completed_at))
        .all()
    )

    # 构建 repo → month → (count, worst_risk) 映射
    # severity 权重：critical=4, high=3, medium=2, low=1
    severity_order = {"low": 1, "medium": 2, "high": 3, "critical": 4}

    # repo_key -> {month: (count, worst_risk)}
    data: dict[str, dict[str, tuple[int, str | None]]] = defaultdict(dict)
    all_months_set: set[str] = set()

    for repo_id, repo_name, completed_at, risk_level in rows:
        month = completed_at.strftime("%Y-%m")
        all_months_set.add(month)
        key = repo_id
        existing = data[key].get(month)
        if existing:
            prev_cnt, prev_worst = existing
            new_cnt = prev_cnt + 1
            # Keep the more severe risk_level
            if prev_worst is None or severity_order.get(risk_level, 0) > severity_order.get(prev_worst, 0):
                new_worst = risk_level
            else:
                new_worst = prev_worst
            data[key][month] = (new_cnt, new_worst)
        else:
            data[key][month] = (1, risk_level)

    # 生成月份列表（最近 12 个月，包含有数据的月份）
    from datetime import datetime, UTC
    now = datetime.now(UTC)
    months = []
    for i in range(11, -1, -1):
        m = now.month - i
        y = now.year
        if m <= 0:
            m += 12
            y -= 1
        months.append(f"{y}-{m:02d}")
    # 确保有数据的月份都在列表中
    for m in sorted(all_months_set):
        if m not in months:
            months.append(m)
    months.sort()

    # 构建响应
    repo_rows: list[HeatmapRepoRow] = []
    for repo in repos:
        cells: list[HeatmapCell] = []
        repo_data = data.get(repo.id, {})
        for month in months:
            entry = repo_data.get(month)
            if entry:
                cnt, worst = entry
                cells.append(HeatmapCell(month=month, review_count=cnt, worst_risk=worst))
            else:
                cells.append(HeatmapCell(month=month, review_count=0, worst_risk=None))
        repo_rows.append(HeatmapRepoRow(repo_id=repo.id, repo_name=repo.name, cells=cells))

    return HeatmapResponse(months=months, repos=repo_rows)
