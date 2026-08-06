"""Node: 生成最终 Review Report 并写回 ReviewState。

报告聚合逻辑位于 app.engine.reporting，本节点只负责结果落位。
"""

from __future__ import annotations

from app.engine.state import ReviewState
from app.engine.reporting import build_report


def generate_report_node(state: ReviewState) -> ReviewState:
    if hook := state.get("_log_hook"):
        hook(step="generate_report", level="info", message="正在生成审查报告...")

    report = build_report(state)
    state["summary"] = report["summary"]
    state["risk_level"] = report["risk_level"]
    state["review_status"] = report["review_status"]
    state["report"] = report
    return state
