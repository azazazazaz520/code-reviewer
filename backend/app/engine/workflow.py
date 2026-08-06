"""Review Workflow — 基于 LangGraph 的审查流程编排。

节点实现位于 app.engine.nodes，本模块只负责图构建与运行入口。
流程拓扑：

Load PR → Planning → Validate Changes → Collect Context → Run Reviews → Reflection
                                        ↑                              │
                                        └──── need_more_context ────────┘
                                        Reflection → Generate Report → END
"""

from __future__ import annotations

from typing import Callable

from langgraph.graph import StateGraph, END

from app.engine.state import ReviewState
from app.engine.nodes import (
    load_pr_node,
    planning_node,
    validate_changes_node,
    collect_context_node,
    run_reviews_node,
    reflection_node,
    should_retry,
    generate_report_node,
)
from app.engine.snapshot import create_review_snapshot


# ─── 构建 Graph ───────────────────────────────────────


def _build_graph() -> StateGraph:
    builder = StateGraph(ReviewState)

    builder.add_node("load_pr", load_pr_node)
    builder.add_node("planning", planning_node)
    builder.add_node("validate_changes", validate_changes_node)
    builder.add_node("collect_context", collect_context_node)
    builder.add_node("run_reviews", run_reviews_node)
    builder.add_node("reflection", reflection_node)
    builder.add_node("generate_report", generate_report_node)

    builder.set_entry_point("load_pr")
    builder.add_edge("load_pr", "planning")
    builder.add_edge("planning", "validate_changes")
    builder.add_edge("validate_changes", "collect_context")
    builder.add_edge("collect_context", "run_reviews")
    builder.add_edge("run_reviews", "reflection")

    builder.add_conditional_edges(
        "reflection",
        should_retry,
        {"collect": "collect_context", "report": "generate_report"},
    )
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
        initial_state: ReviewState = {
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
            "review_plan": [],
            "context_candidates": [],
            "context_round": 0,
            "context_initialized": False,
            "validator_findings": [],
            "checks": [],
            "workflow_errors": [],
            "quality_metrics": {},
            "reviewer_outputs": {},
            "change_scopes": {},
            "file_context_cache": {},
            "findings": [],
            "reflection_round": 0,
            "need_more_context": False,
            "summary": "",
            "risk_level": "low",
            "review_status": "complete",
            "crg_enabled": True,
            "impact_radius": None,
            "_log_hook": log_hook,
        }

        final_state = _graph.invoke(initial_state)
        return final_state.get("report", {})
    finally:
        snapshot.cleanup()
