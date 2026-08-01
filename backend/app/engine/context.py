"""Reviewer 上下文选择与预算。

把“哪些文件进入哪个 Reviewer 的 prompt”集中在一个模块中，避免每个
Reviewer 自己截断上下文，也避免把完整缓存重复发送给所有 Reviewer。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ContextBudget:
    max_files: int
    max_chars: int


REVIEWER_CONTEXT_BUDGETS = {
    "security_reviewer": ContextBudget(max_files=12, max_chars=16000),
    "performance_reviewer": ContextBudget(max_files=12, max_chars=14000),
    "style_reviewer": ContextBudget(max_files=10, max_chars=12000),
}
DEFAULT_CONTEXT_BUDGET = ContextBudget(max_files=10, max_chars=12000)


def select_reviewer_context(
    file_context: dict[str, str],
    changed_files: list[str],
    reviewer_name: str,
) -> dict[str, str]:
    """按优先级和总字符预算选择一个 Reviewer 的文件上下文。

    变更文件优先，随后才使用 CRG 找到的关联文件。返回新字典，调用方
    可以安全地交给 Reviewer，不会修改共享缓存。
    """
    budget = REVIEWER_CONTEXT_BUDGETS.get(reviewer_name, DEFAULT_CONTEXT_BUDGET)
    ordered_paths = list(dict.fromkeys(
        [path for path in changed_files if path in file_context]
        + [path for path in file_context if path not in changed_files]
    ))

    selected: dict[str, str] = {}
    total_chars = 0
    for path in ordered_paths:
        if len(selected) >= budget.max_files or total_chars >= budget.max_chars:
            break
        remaining = budget.max_chars - total_chars
        content = file_context[path][:remaining]
        selected[path] = content
        total_chars += len(content)
    return selected
