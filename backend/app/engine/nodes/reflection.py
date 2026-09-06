"""Node: 评估 Findings，决定是否需要更多上下文。

判断标准：
  - 硬限制: reflection_round >= max_reflection_rounds → 停止
  - 只要仍有未覆盖文件或 Diff Hunk，就继续处理下一批
  - Finding 数量和行号不能单独证明审查已经完成
"""

from __future__ import annotations

from typing import Literal

from app.config import settings
from app.engine.state import ReviewState


def reflection_node(state: ReviewState) -> ReviewState:
    if hook := state.get("_log_hook"):
        hook(step="reflection", level="info",
             message=f"反思中 (第 {state.get('reflection_round', 0) + 1}/{settings.max_reflection_rounds} 轮)...")

    state["reflection_round"] = state.get("reflection_round", 0) + 1
    max_rounds = min(
        settings.max_reflection_rounds,
        1 + settings.max_incremental_reflection_rounds,
    )

    if state.get("cancel_requested") or state.get("review_budget", {}).get("budget_exhausted"):
        state["need_more_context"] = False
        return state

    coverage = state.get("coverage")
    if coverage is None:
        # 保留节点独立调用的旧契约；完整 Workflow 始终由覆盖模块提供状态。
        findings = state.get("findings", [])
        has_line_refs = any(f.get("line", 0) > 0 and f.get("file") for f in findings)
        candidates = state.get("context_candidates", [])
        loaded = state.get("file_context_cache", {})
        has_uncovered_scope = bool(
            findings and not has_line_refs and any(path not in loaded for path in candidates)
        )
    else:
        has_uncovered_scope = bool(
            coverage.get("uncovered_files") or coverage.get("uncovered_hunks")
        )

    if state["reflection_round"] >= max_rounds:
        state["need_more_context"] = False
    else:
        state["need_more_context"] = has_uncovered_scope

    return state


def should_retry(state: ReviewState) -> Literal["collect", "report"]:
    """条件边：是否需要回退到 Collect Context。"""
    return "collect" if state.get("need_more_context") else "report"
