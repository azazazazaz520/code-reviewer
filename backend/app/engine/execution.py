"""审查任务的时间边界和取消状态。"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Callable


class ReviewCancelled(RuntimeError):
    """审查任务被用户取消或外部控制器要求停止。"""


class ReviewBudgetExceeded(RuntimeError):
    """审查任务达到最大持续时间。"""


@dataclass
class ReviewExecutionBudget:
    """跨 Workflow 节点共享的任务级执行预算。"""

    max_duration_seconds: float
    started_at: float = field(default_factory=time.monotonic)
    primary_calls: int = 0
    completed_units: int = 0
    completed_assignments: int = 0
    attempted_units: int = 0
    context_read_requests: int = 0
    context_cache_hits: int = 0
    context_cache_misses: int = 0
    exhausted_reason: str | None = None
    _lock: Lock = field(default_factory=Lock, repr=False)

    def check(
        self,
        cancel_check: Callable[[], bool] | None = None,
    ) -> None:
        """在开始新的耗时操作前检查取消和任务预算。"""
        if cancel_check and cancel_check():
            raise ReviewCancelled("审查任务已取消")
        if self.max_duration_seconds > 0 and self.elapsed_seconds() >= self.max_duration_seconds:
            self.exhausted_reason = "duration"
            raise ReviewBudgetExceeded("审查任务达到最大执行时间")

    def reserve_primary_call(self, cancel_check: Callable[[], bool] | None = None) -> None:
        with self._lock:
            self.check(cancel_check)
            self.primary_calls += 1
            self.attempted_units += 1

    def elapsed_seconds(self) -> float:
        return max(0.0, time.monotonic() - self.started_at)

    def as_dict(
        self,
        planned_units: int = 0,
        pending_units: int = 0,
        planned_assignments: int = 0,
        pending_assignments: int = 0,
        pending_unit_ids: list[str] | None = None,
    ) -> dict:
        return {
            "planned_units": planned_units,
            "completed_units": self.completed_units,
            "attempted_units": self.attempted_units,
            "pending_units": pending_units,
            "planned_assignments": planned_assignments,
            "completed_assignments": self.completed_assignments,
            "pending_assignments": pending_assignments,
            "pending_unit_ids": list(pending_unit_ids or []),
            "primary_llm_calls": self.primary_calls,
            "context_read_requests": self.context_read_requests,
            "context_cache_hits": self.context_cache_hits,
            "context_cache_misses": self.context_cache_misses,
            "elapsed_seconds": round(self.elapsed_seconds(), 3),
            "budget_exhausted": bool(self.exhausted_reason),
            "budget_exhausted_reason": self.exhausted_reason,
        }


def get_or_create_budget(state: dict, *, max_duration_seconds: float) -> ReviewExecutionBudget:
    """从状态复用预算对象，兼容旧状态中的普通字典。"""
    existing = state.get("_review_budget_object")
    if isinstance(existing, ReviewExecutionBudget):
        return existing

    raw = state.get("review_budget") or {}
    budget = ReviewExecutionBudget(
        max_duration_seconds=float(raw.get("max_review_duration_seconds", max_duration_seconds)),
        started_at=float(raw.get("started_at", time.monotonic())),
        primary_calls=int(raw.get("primary_llm_calls", 0)),
        completed_units=int(raw.get("completed_units", 0)),
        completed_assignments=int(raw.get("completed_assignments", 0)),
        attempted_units=int(raw.get("attempted_units", 0)),
        context_read_requests=int(
            raw.get("context_read_requests", raw.get("tool_calls", 0))
        ),
        context_cache_hits=int(
            raw.get("context_cache_hits", raw.get("cache_hits", 0))
        ),
        context_cache_misses=int(
            raw.get("context_cache_misses", raw.get("cache_misses", 0))
        ),
        exhausted_reason=raw.get("budget_exhausted_reason"),
    )
    state["_review_budget_object"] = budget
    return budget
