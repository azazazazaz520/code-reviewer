"""Review Workflow — 基于 LangGraph 的审查流程编排。

节点实现位于 app.engine.nodes，本模块只负责图构建与运行入口。
流程拓扑：

Load PR → Prepare Review → Run Reviews → Generate Report → END
"""

from __future__ import annotations

from typing import Callable

from langgraph.graph import StateGraph, END

from app.config import settings
from app.engine.state import ReviewState
from app.engine.execution import ReviewExecutionBudget
from app.engine.tools.context import TaskToolCache
from app.engine.nodes import (
    load_pr_node,
    prepare_review_node,
    run_reviews_node,
    generate_report_node,
)
from app.engine.snapshot import create_review_snapshot


# ─── 构建 Graph ───────────────────────────────────────


def _build_graph() -> StateGraph:
    builder = StateGraph(ReviewState)

    builder.add_node("load_pr", load_pr_node)
    builder.add_node("prepare_review", prepare_review_node)
    builder.add_node("run_reviews", run_reviews_node)
    builder.add_node("generate_report", generate_report_node)

    builder.set_entry_point("load_pr")
    builder.add_edge("load_pr", "prepare_review")
    builder.add_edge("prepare_review", "run_reviews")
    builder.add_edge("run_reviews", "generate_report")
    builder.add_edge("generate_report", END)

    return builder.compile()


_graph = _build_graph()


# ─── 公开入口 ─────────────────────────────────────────


def run_workflow(
    repo_path: str,
    git_url: str = "",
    review_type: str = "pr",
    source_type: str | None = None,
    pr_number: int | None = None,
    commit_hash: str | None = None,
    branch: str | None = None,
    base_branch: str | None = None,
    head_revision: str | None = None,
    base_revision: str | None = None,
    workspace_path: str | None = None,
    workspace_target: str | None = None,
    log_hook: Callable | None = None,
    cancel_check: Callable[[], bool] | None = None,
    task_id: str | None = None,
) -> dict:
    """运行审查 Workflow，返回报告 dict。"""
    snapshot = create_review_snapshot(
        repo_path,
        git_url=git_url,
        review_type=review_type,
        source_type=source_type,
        pr_number=pr_number,
        commit_hash=commit_hash,
        branch=branch,
        base_branch=base_branch,
        head_revision=head_revision,
        base_revision=base_revision,
        workspace_path=workspace_path,
        workspace_target=workspace_target,
    )
    try:
        effective_source_type = source_type or ("pr" if review_type == "pr" else "commit")
        scope_target = {
            "workspace": (
                f"工作区提交 {snapshot.revision} 的当前改动"
                if workspace_target in {"head_commit", "commit"}
                else "当前工作区未提交改动"
            ),
            "commit": f"提交 {snapshot.revision} 的当前改动",
            "remote_commit": f"远程提交 {snapshot.revision} 的当前改动",
            "pr": f"Pull Request {pr_number or ''} 的当前改动".strip(),
            "remote_latest": "远程分支最新提交的当前改动",
        }.get(effective_source_type, "当前审查快照中的变更")
        review_scope = {
            "source_type": effective_source_type,
            "target": scope_target,
            "revision": snapshot.revision,
            "base_revision": snapshot.base_revision,
            "changed_files": list(snapshot.changed_files),
        }
        initial_state: ReviewState = {
            "task_id": task_id or "",
            "repo_id": snapshot.repo_root,
            "git_url": git_url,
            "review_type": review_type,
            "source_type": source_type,
            "pr_number": pr_number,
            "commit_hash": commit_hash,
            "branch": branch,
            "base_branch": base_branch,
            "raw_diff": snapshot.raw_diff,
            "changed_files": snapshot.changed_files,
            "snapshot_revision": snapshot.revision,
            "snapshot_base_revision": snapshot.base_revision,
            "workspace_fingerprint": snapshot.workspace_fingerprint,
            "workspace_stats": snapshot.workspace_stats,
            "review_scope": review_scope,
            "database_id": "",
            "database_status": "failed",
            "extraction_status": "failed",
            "extraction_errors": [],
            "database_stats": {},
            "code_database_info": {},
            "code_database": None,
            "tool_context": None,
            "approved_context_refs": [],
            "analysis_results": [],
            "coverage": {},
            "review_plan": [],
            "context_candidates": [],
            "context_round": 0,
            "context_initialized": False,
            "context_errors": {},
            "context_progress": {},
            "candidate_findings": [],
            "validator_findings": [],
            "checks": [],
            "workflow_errors": [],
            "quality_metrics": {},
            "reviewer_outputs": {},
            "reviewed_batch_keys": {},
            "review_units": [],
            "review_batches": {},
            "reviewed_unit_keys": {},
            "completed_batch_keys": {},
            "completed_unit_ids": [],
            "pending_unit_ids": [],
            "review_budget": {},
            "tool_cache": TaskToolCache(),
            "cancel_requested": False,
            "change_scopes": {},
            "file_context_cache": {},
            "findings": [],
            "summary": "",
            "risk_level": "low",
            "review_status": "complete",
            "crg_enabled": settings.crg_enabled,
            "impact_radius": None,
            "_log_hook": log_hook,
            "_cancel_check": cancel_check,
            "_review_budget_object": ReviewExecutionBudget(
                max_duration_seconds=settings.max_review_duration_seconds,
            ),
        }

        final_state = _graph.invoke(initial_state)
        return final_state.get("report", {})
    finally:
        snapshot.cleanup()
