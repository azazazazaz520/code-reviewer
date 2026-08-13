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
from app.engine.snapshot import SnapshotError, validate_workspace_path
from app.services.repo_sync import (
    RepoSyncError,
    persist_sync_result,
    resolve_parent,
    resolve_remote_branch,
    resolve_revision,
    sync_repository,
)
from app.services.review_log import ReviewLogBuffer

router = APIRouter(prefix="/api", tags=["reviews"])


def _normalise_report_checks(checks: list[dict], quality: dict) -> list[dict]:
    """将历史报告中的内部校验术语转换成面向用户的提示。"""
    normalised = []
    for check in checks:
        item = dict(check)
        if item.get("name") == "finding_context":
            count = quality.get("reviewer_context_findings", 0)
            item["message"] = (
                f"{count} 个问题出现在修改文件的相邻代码中，请确认是否由本次提交引起。"
            )
        elif item.get("name") == "finding_gate":
            count = quality.get("filtered_findings", 0)
            item["message"] = f"{count} 条候选意见未达到证据要求，未计入最终结果。"
        normalised.append(item)
    return normalised


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

    source_type = body.source_type.value if body.source_type else None
    if source_type is None:
        if body.review_type is None:
            raise HTTPException(status_code=400, detail="请选择审查来源")
        source_type = "pr" if body.review_type.value == "pr" else (
            "remote_commit" if body.commit_hash else "remote_latest"
        )

    if source_type == "pr" and not body.pr_number:
        raise HTTPException(status_code=400, detail="PR 审查需要 PR 编号")
    if source_type == "remote_latest" and not body.branch:
        raise HTTPException(status_code=400, detail="远程最新提交审查需要选择分支")
    if source_type == "remote_commit" and not body.commit_hash:
        raise HTTPException(status_code=400, detail="远程 Commit 审查需要 Commit SHA")
    workspace_root = None
    if source_type == "workspace" and not body.workspace_path:
        raise HTTPException(status_code=400, detail="本地工作区审查需要工作区路径")
    if source_type == "workspace":
        try:
            workspace_root = validate_workspace_path(body.workspace_path or "")
        except SnapshotError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    if source_type == "workspace" and (body.workspace_target or "working_tree") not in {
        "working_tree",
        "head_commit",
        "commit",
    }:
        raise HTTPException(status_code=400, detail="本地工作区审查目标无效")

    review_type = "pr" if source_type == "pr" else "local"

    task = ReviewTask(
        repo_id=repo_id,
        review_type=review_type,
        source_type=source_type,
        pr_number=body.pr_number,
        commit_hash=body.commit_hash,
        branch=body.branch,
        base_branch=body.base_branch,
        source_path=workspace_root,
        workspace_target=body.workspace_target or ("working_tree" if source_type == "workspace" else None),
        status="pending",
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    return _to_review_task_response(task)


@router.get("/repos/{repo_id}/reviews", response_model=list[ReviewTaskResponse])
def list_reviews(
    repo_id: str,
    include_archived: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    """获取仓库的审查历史列表，默认隐藏已归档记录。"""
    return [_to_review_task_response(task) for task in list_reviews_with_archive(repo_id, include_archived, db)]


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


def _to_review_task_response(task: ReviewTask) -> ReviewTaskResponse:
    """统一补齐任务上下文，避免状态接口返回空的仓库名称和风险等级。"""
    response = ReviewTaskResponse.model_validate(task)
    response.repo_name = task.repo.name if task.repo else None
    response.risk_level = task.report.risk_level if task.report else None
    return response


def _require_terminal(task: ReviewTask) -> None:
    if task.status in {"pending", "preparing", "running"}:
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
    return _to_review_task_response(task)


@router.post("/reviews/{task_id}/restore", response_model=ReviewTaskResponse)
def restore_review(task_id: str, db: Session = Depends(get_db)):
    """恢复一条已归档的审查记录。"""
    task = _get_review_task(task_id, db)
    if task.archived_at is not None:
        task.archived_at = None
        db.commit()
        db.refresh(task)
    return _to_review_task_response(task)


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
    return _to_review_task_response(task)


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
    checks = _normalise_report_checks(checks, quality)
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
    legacy_suffix = "；审查未完整覆盖，请查看校验摘要"
    if summary.endswith(legacy_suffix):
        summary = summary[: -len(legacy_suffix)]

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
    log_buffer: ReviewLogBuffer | None = None
    try:
        task = db.query(ReviewTask).filter(ReviewTask.id == task_id).first()
        if not task:
            return

        log_buffer = ReviewLogBuffer(task_id)

        task.status = "running"
        task.error_message = None
        db.commit()

        repo = db.query(Repo).filter(Repo.id == task.repo_id).first()
        if not repo:
            raise ValueError("仓库不存在")

        # 注入日志 hook
        def log_hook(step: str, level: str, message: str,
                     tool_name: str | None = None, tool_args: str | None = None):
            log_buffer.append(
                step=step,
                level=level,
                message=message,
                tool_name=tool_name,
                tool_args=tool_args,
            )

        source_type = task.source_type or (
            "pr" if task.review_type == "pr" else (
                "remote_commit" if task.commit_hash else "remote_latest"
            )
        )
        task.source_type = source_type

        if source_type in {"remote_latest", "remote_commit"}:
            _lock_remote_review_revision(task, repo, db, log_hook)

        # 写入开始日志
        log_hook(step="load_pr", level="info",
                 message=f"开始审查 (source={source_type})")

        # 运行审查引擎
        result = run_workflow(
            repo_path=task.source_path or repo.local_path,
            git_url=repo.git_url,
            review_type=task.review_type,
            source_type=source_type,
            pr_number=task.pr_number,
            commit_hash=task.commit_hash,
            branch=task.branch,
            base_branch=task.base_branch,
            head_revision=task.head_revision,
            base_revision=task.base_revision,
            workspace_path=task.source_path,
            workspace_target=task.workspace_target,
            log_hook=log_hook,
        )

        # 完成日志
        log_hook(step="generate_report", level="info", message="审查完成")
        log_buffer.flush()

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
        changes = result.get("changes", {})
        task.workspace_fingerprint = changes.get("workspace_fingerprint")
        if changes.get("workspace_stats") is not None:
            task.workspace_stats_json = json.dumps(
                changes["workspace_stats"], ensure_ascii=False
            )
        task.completed_at = datetime.now(UTC)
        db.commit()

    except Exception as e:
        if log_buffer is not None:
            log_buffer.flush()
        db.rollback()
        task = db.query(ReviewTask).filter(ReviewTask.id == task_id).first()
        if task:
            task.status = "failed"
            task.error_message = format_user_error(e)
            task.completed_at = datetime.now(UTC)
            db.commit()
    finally:
        if log_buffer is not None:
            log_buffer.flush()
        db.close()


def _lock_remote_review_revision(task: ReviewTask, repo: Repo, db: Session, log_hook) -> None:
    """同步远程来源并将目标与基准 SHA 固化到任务。"""
    checked_at = datetime.now(UTC)
    log_hook(step="prepare_source", level="info", message="正在同步远程分支并锁定审查版本...")
    try:
        sync_result = sync_repository(repo.local_path)
        persist_sync_result(db, repo, sync_result, checked_at)
        if task.source_type == "remote_latest":
            if not task.branch:
                raise RepoSyncError("远程最新提交审查缺少分支")
            head_revision = resolve_remote_branch(repo.local_path, task.branch)
        else:
            if not task.commit_hash:
                raise RepoSyncError("远程 Commit 审查缺少 Commit SHA")
            head_revision = resolve_revision(repo.local_path, task.commit_hash)

        if task.base_branch:
            base_revision = resolve_remote_branch(repo.local_path, task.base_branch)
            if base_revision == head_revision:
                base_revision = resolve_parent(repo.local_path, head_revision)
        else:
            base_revision = resolve_parent(repo.local_path, head_revision)

        task.head_revision = head_revision
        task.base_revision = base_revision
        task.commit_hash = head_revision if task.source_type == "remote_commit" else task.commit_hash
        db.commit()
        log_hook(
            step="prepare_source",
            level="info",
            message=(
                f"已锁定审查版本 head={head_revision[:12]} "
                f"base={base_revision[:12]}"
            ),
        )
    except RepoSyncError:
        db.rollback()
        raise


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
