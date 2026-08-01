import json
from datetime import datetime, UTC

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.models.base import get_db
from app.models.repo import Repo, ReviewTask, ReviewReport, ReviewLog
from app.models.schemas import (
    ReviewCreate,
    ReviewTaskResponse,
    ReviewReportResponse,
    ReportContent,
    ReviewLogResponse,
)

router = APIRouter(prefix="/api", tags=["reviews"])


@router.post(
    "/repos/{repo_id}/reviews", response_model=ReviewTaskResponse, status_code=201
)
def submit_review(
    repo_id: str,
    body: ReviewCreate,
    db: Session = Depends(get_db),
):
    """提交审查任务。立即返回 review_id，由持久化 worker 异步执行。"""
    repo = db.query(Repo).filter(Repo.id == repo_id).first()
    if not repo:
        raise HTTPException(status_code=404, detail="仓库不存在")

    task = ReviewTask(
        repo_id=repo_id,
        review_type=body.review_type.value,
        pr_number=body.pr_number,
        commit_hash=body.commit_hash,
        base_branch=body.base_branch,
        status="pending",
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    return task


@router.get("/repos/{repo_id}/reviews", response_model=list[ReviewTaskResponse])
def list_reviews(repo_id: str, db: Session = Depends(get_db)):
    """获取仓库的审查历史列表。"""
    repo = db.query(Repo).filter(Repo.id == repo_id).first()
    if not repo:
        raise HTTPException(status_code=404, detail="仓库不存在")

    return (
        db.query(ReviewTask)
        .filter(ReviewTask.repo_id == repo_id)
        .order_by(ReviewTask.created_at.desc())
        .all()
    )


@router.get("/reviews/{task_id}", response_model=ReviewTaskResponse)
def get_review_status(task_id: str, db: Session = Depends(get_db)):
    """轮询审查状态。返回当前 status（pending/running/done/failed）。"""
    task = db.query(ReviewTask).filter(ReviewTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="审查任务不存在")
    return task


@router.get("/reviews/{task_id}/report", response_model=ReviewReportResponse)
def get_review_report(task_id: str, db: Session = Depends(get_db)):
    """获取审查报告。仅在 status=done 时返回完整报告。"""
    task = db.query(ReviewTask).filter(ReviewTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="审查任务不存在")

    if task.status != "done":
        return ReviewReportResponse(review_id=task.id, status=task.status, report=None)

    report = db.query(ReviewReport).filter(ReviewReport.task_id == task_id).first()
    if not report:
        return ReviewReportResponse(
            review_id=task.id, status=task.status, report=None
        )

    return ReviewReportResponse(
        review_id=task.id,
        status=task.status,
        report=ReportContent(
            summary=report.summary,
            risk_level=report.risk_level,
            findings=json.loads(report.findings_json),
            stats=json.loads(report.stats_json),
        ),
    )


# ─── 审查引擎 ───────────────────────────────────────


def _run_review_workflow(task_id: str):
    """后台运行审查 Workflow。"""
    from app.models.base import SessionLocal
    from app.engine.workflow import run_workflow

    db = SessionLocal()
    try:
        task = db.query(ReviewTask).filter(ReviewTask.id == task_id).first()
        if not task:
            return

        task.status = "running"
        task.error_message = None
        db.commit()

        repo = db.query(Repo).filter(Repo.id == task.repo_id).first()
        if not repo:
            raise ValueError("仓库不存在")

        # 注入日志 hook
        def log_hook(step: str, level: str, message: str,
                     tool_name: str | None = None, tool_args: str | None = None):
            try:
                log_entry = ReviewLog(
                    task_id=task_id,
                    step=step,
                    level=level,
                    message=message,
                    tool_name=tool_name,
                    tool_args=tool_args,
                )
                db.add(log_entry)
                db.commit()
            except Exception:
                db.rollback()
                pass  # 日志写入失败不影响审查流程

        # 写入开始日志
        log_hook(step="load_pr", level="info",
                 message=f"开始审查 (type={task.review_type})")

        # 运行审查引擎
        result = run_workflow(
            repo_path=repo.local_path,
            git_url=repo.git_url,
            review_type=task.review_type,
            pr_number=task.pr_number,
            commit_hash=task.commit_hash,
            base_branch=task.base_branch,
            log_hook=log_hook,
        )

        # 完成日志
        log_hook(step="generate_report", level="info", message="审查完成")

        report = ReviewReport(
            task_id=task.id,
            summary=result["summary"],
            risk_level=result["risk_level"],
            findings_json=json.dumps(result["findings"], ensure_ascii=False),
            stats_json=json.dumps(result["stats"], ensure_ascii=False),
        )
        db.add(report)
        task.status = "done"
        task.completed_at = datetime.now(UTC)
        db.commit()

    except Exception as e:
        db.rollback()
        task = db.query(ReviewTask).filter(ReviewTask.id == task_id).first()
        if task:
            task.status = "failed"
            task.error_message = str(e)
            task.completed_at = datetime.now(UTC)
            db.commit()
    finally:
        db.close()


@router.get("/reviews/{task_id}/logs", response_model=list[ReviewLogResponse])
def get_review_logs(task_id: str, db: Session = Depends(get_db)):
    """获取审查任务的实时日志。"""
    task = db.query(ReviewTask).filter(ReviewTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="审查任务不存在")

    return (
        db.query(ReviewLog)
        .filter(ReviewLog.task_id == task_id)
        .order_by(ReviewLog.created_at.asc())
        .all()
    )
