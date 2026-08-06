"""Node: 根据变更范围决定审查计划。"""

from __future__ import annotations

from app.engine.state import ReviewState
from app.engine.scope import build_review_plan, classify_files


def planning_node(state: ReviewState) -> ReviewState:
    changed = state.get("changed_files", [])
    diff = state.get("raw_diff", "")

    if hook := state.get("_log_hook"):
        hook(step="planning", level="info", message="正在规划审查策略...")

    state["review_plan"] = build_review_plan(changed, diff)
    state["change_scopes"] = {
        path: scope.kind for path, scope in classify_files(changed).items()
    }

    if hook := state.get("_log_hook"):
        plan_str = ", ".join(state["review_plan"]) if state["review_plan"] else "(无需通用 Reviewer)"
        hook(step="planning", level="info",
             message=f"审查策略: {plan_str}")

    return state
