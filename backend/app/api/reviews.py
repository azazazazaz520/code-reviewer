import json
from datetime import datetime, UTC

from fastapi import APIRouter, Depends, HTTPException, Query
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
from app.engine.errors import format_user_error

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

    if body.review_type.value == "pr" and not body.pr_number:
        raise HTTPException(status_code=400, detail="PR 审查需要 PR 编号")
    if body.review_type.value == "local" and not body.branch and not body.commit_hash:
        raise HTTPException(status_code=400, detail="Local 审查请选择分支或输入 Commit Hash")

    task = ReviewTask(
        repo_id=repo_id,
        review_type=body.review_type.value,
        pr_number=body.pr_number,
        commit_hash=body.commit_hash,
        branch=body.branch,
        base_branch=body.base_branch,
        status="pending",
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    return task


@router.get("/repos/{repo_id}/reviews", response_model=list[ReviewTaskResponse])
def list_reviews(
    repo_id: str,
    include_archived: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    """获取仓库的审查历史列表，默认隐藏已归档记录。"""
    return list_reviews_with_archive(repo_id, include_archived, db)


def list_reviews_with_archive(
    repo_id: str,
    include_archived: bool,
    db: Session,
):
    """获取仓库的审查历史列表。"""
    repo = db.query(Repo).filter(Repo.id == repo_id).first()
    if not repo:
        raise HTTPException(status_code=404, detail="仓库不存在")

    query = db.query(ReviewTask).filter(ReviewTask.repo_id == repo_id)
    if not include_archived:
        query = query.filter(ReviewTask.archived_at.is_(None))
    return query.order_by(ReviewTask.created_at.desc()).all()


def _get_review_task(task_id: str, db: Session) -> ReviewTask:
    task = db.query(ReviewTask).filter(ReviewTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="审查任务不存在")
    return task


def _require_terminal(task: ReviewTask) -> None:
    if task.status in {"pending", "running"}:
        raise HTTPException(status_code=409, detail="审查仍在进行中，完成后才能管理该记录")


@router.post("/reviews/{task_id}/archive", response_model=ReviewTaskResponse)
def archive_review(task_id: str, db: Session = Depends(get_db)):
    """归档一条已结束的审查记录。"""
    task = _get_review_task(task_id, db)
    _require_terminal(task)
    if task.archived_at is None:
        task.archived_at = datetime.now(UTC)
        db.commit()
        db.refresh(task)
    return task


@router.post("/reviews/{task_id}/restore", response_model=ReviewTaskResponse)
def restore_review(task_id: str, db: Session = Depends(get_db)):
    """恢复一条已归档的审查记录。"""
    task = _get_review_task(task_id, db)
    if task.archived_at is not None:
        task.archived_at = None
        db.commit()
        db.refresh(task)
    return task


@router.delete("/reviews/{task_id}", status_code=204)
def delete_review(task_id: str, db: Session = Depends(get_db)):
    """永久删除一条已结束的审查记录及其报告、日志。"""
    task = _get_review_task(task_id, db)
    _require_terminal(task)
    db.query(ReviewLog).filter(ReviewLog.task_id == task.id).delete(synchronize_session=False)
    db.delete(task)
    db.commit()


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

    stats = json.loads(report.stats_json)
    checks = stats.pop("checks", [])
    quality = stats.pop("quality", {})
    reviewer_outputs = stats.pop("reviewer_outputs", {})
    changes = stats.pop("changes", {})
    review_status = stats.pop("review_status", None)
    if not review_status:
        review_status = (
            "degraded"
            if any(check.get("status") in {"error", "fail"} for check in checks)
            else "complete"
        )

    summary = report.summary
    if review_status == "degraded" and "未完整覆盖" not in summary:
        summary += "；审查未完整覆盖，请查看校验摘要"

    return ReviewReportResponse(
        review_id=task.id,
        status=task.status,
        report=ReportContent(
            summary=summary,
            risk_level=report.risk_level,
            review_status=review_status,
            findings=json.loads(report.findings_json),
            stats=stats,
            checks=checks,
            quality=quality,
            reviewer_outputs=reviewer_outputs,
            changes=changes,
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
            branch=task.branch,
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
            stats_json=json.dumps(
                {
                    **result["stats"],
                    "checks": result.get("checks", []),
                    "quality": result.get("quality", {}),
                    "reviewer_outputs": result.get("reviewer_outputs", {}),
                    "changes": result.get("changes", {}),
                    "review_status": result.get("review_status", "complete"),
                },
                ensure_ascii=False,
            ),
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
            task.error_message = format_user_error(e)
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
