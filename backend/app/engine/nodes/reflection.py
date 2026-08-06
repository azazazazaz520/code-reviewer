"""Node: 评估 Findings，决定是否需要更多上下文。

判断标准（ADR 0001）:
  - 硬限制: reflection_round >= max_reflection_rounds → 停止
  - 软判断: 至少一个 finding 引用了具体行号 → 认为覆盖充分
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
    max_rounds = settings.max_reflection_rounds

    findings = state.get("findings", [])
    has_line_refs = any(f.get("line", 0) > 0 and f.get("file") for f in findings)
    candidates = state.get("context_candidates", [])
    loaded = state.get("file_context_cache", {})
    has_unread_candidates = any(path not in loaded for path in candidates)

    if not findings:
        state["need_more_context"] = False
    elif state["reflection_round"] >= max_rounds:
        state["need_more_context"] = False
    elif (
        not has_line_refs
        and has_unread_candidates
        and state["reflection_round"] < max_rounds
    ):
        state["need_more_context"] = True
    else:
        state["need_more_context"] = False

    return state


def should_retry(state: ReviewState) -> Literal["collect", "report"]:
    """条件边：是否需要回退到 Collect Context。"""
    return "collect" if state.get("need_more_context") else "report"
