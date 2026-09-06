"""Reviewer 上下文选择与预算。

把“哪些文件进入哪个 Reviewer 的 prompt”集中在一个模块中，避免每个
Reviewer 自己截断上下文，也避免把完整缓存重复发送给所有 Reviewer。
"""

from __future__ import annotations

from dataclasses import dataclass
import re

from app.config import settings
from app.engine.paths import PathSecurityError, normalize_relative_path


@dataclass(frozen=True)
class ContextBudget:
    max_files: int
    max_chars: int

    def __post_init__(self) -> None:
        if self.max_chars <= 0:
            raise ValueError("max_chars 必须大于 0")


@dataclass(frozen=True)
class ContextSelection:
    """Reviewer 实际收到的文件上下文及预算截断信息。"""

    files: dict[str, str]
    truncated_inputs: int = 0
    omitted_files: tuple[str, ...] = ()
    truncation_events: tuple[str, ...] = ()


REVIEWER_CONTEXT_BUDGETS = {
    "security_reviewer": ContextBudget(max_files=500, max_chars=2000000),
    "performance_reviewer": ContextBudget(max_files=500, max_chars=2000000),
    "style_reviewer": ContextBudget(max_files=500, max_chars=2000000),
}
DEFAULT_CONTEXT_BUDGET = ContextBudget(max_files=500, max_chars=2000000)
REVIEW_DIFF_BATCH_CHARS = 12000


def _reviewer_context_budget(reviewer_name: str) -> ContextBudget:
    """返回任务配置覆盖后的 Reviewer 上下文预算。"""
    default = REVIEWER_CONTEXT_BUDGETS.get(reviewer_name, DEFAULT_CONTEXT_BUDGET)
    return ContextBudget(
        max_files=max(1, settings.review_context_max_files or default.max_files),
        max_chars=max(1, settings.review_context_max_chars or default.max_chars),
    )


def build_stable_file_context(
    file_context: dict[str, str],
    primary_file: str,
    reviewer_name: str,
) -> dict[str, str]:
    """兼容旧调用方，构造只包含主文件的稳定上下文包。"""
    return build_stable_context_pack(
        file_context,
        [primary_file],
        reviewer_name,
    )


def build_stable_context_pack(
    file_context: dict[str, str],
    preferred_files: list[str],
    reviewer_name: str,
) -> dict[str, str]:
    """构造同一 Reviewer 所有 ReviewUnit 共享的稳定上下文包。

    共享包只保留固定顺序的文件前缀，并使用 Reviewer 的完整上下文预算。
    已进入共享包的文件不需要在每个 ReviewUnit 的动态后缀中重复发送；未进入
    共享包的关联文件仍由 ``select_reviewer_unit_context`` 提供。
    """
    normalised_context: dict[str, str] = {}
    for path, content in file_context.items():
        try:
            normalised_path = normalize_relative_path(path)
        except PathSecurityError:
            continue
        if isinstance(content, str):
            normalised_context[normalised_path] = content

    if not normalised_context:
        return {}

    preferred: set[str] = set()
    for path in preferred_files:
        try:
            normalised = normalize_relative_path(path)
        except PathSecurityError:
            continue
        if normalised in normalised_context:
            preferred.add(normalised)
    ordered_paths = [
        *sorted(preferred),
        *sorted(set(normalised_context) - preferred),
    ]

    budget = _reviewer_context_budget(reviewer_name)
    max_chars = max(1, budget.max_chars)
    selected: dict[str, str] = {}
    total_chars = 0
    for path in ordered_paths[:budget.max_files]:
        if total_chars >= max_chars:
            break
        remaining = max_chars - total_chars
        original = normalised_context[path]
        content = original[:remaining]
        if len(original) > remaining:
            marker = (
                f"\n[共享上下文截断：{path} 仅展示前 {remaining} 个字符，"
                f"原始长度 {len(original)}；请以快照 Tool 查询为准]"
            )
            content = (
                original[: max(0, remaining - len(marker))] + marker
            )[:remaining]
        selected[path] = content
        total_chars += len(content)
    return selected


def select_reviewer_context(
    file_context: dict[str, str],
    changed_files: list[str],
    reviewer_name: str,
) -> dict[str, str]:
    """按优先级和总字符预算选择一个 Reviewer 的文件上下文。

    变更文件优先，随后才使用 CRG 找到的关联文件。返回新字典，调用方
    可以安全地交给 Reviewer，不会修改共享缓存。
    """
    return select_reviewer_context_with_metadata(
        file_context,
        changed_files,
        reviewer_name,
    ).files


def select_reviewer_context_with_metadata(
    file_context: dict[str, str],
    changed_files: list[str],
    reviewer_name: str,
) -> ContextSelection:
    """选择 Reviewer 上下文，同时记录文件数和字符预算造成的截断。"""
    budget = _reviewer_context_budget(reviewer_name)

    def normalise(path: str) -> str:
        return normalize_relative_path(path)

    normalised_context = {
        normalise(path): content for path, content in file_context.items()
    }
    normalised_changed = [normalise(path) for path in changed_files]
    ordered_paths = list(dict.fromkeys(
        [path for path in normalised_changed if path in normalised_context]
        + [path for path in normalised_context if path not in normalised_changed]
    ))

    selected: dict[str, str] = {}
    omitted_files: list[str] = []
    truncation_events: list[str] = []
    total_chars = 0
    for index, path in enumerate(ordered_paths):
        if len(selected) >= budget.max_files or total_chars >= budget.max_chars:
            omitted_files.extend(ordered_paths[index:])
            break
        remaining = budget.max_chars - total_chars
        original = normalised_context[path]
        content = original[:remaining]
        if len(original) > remaining:
            marker = (
                f"\n[上下文截断：{path} 仅展示前 {remaining} 个字符，"
                f"原始长度 {len(original)}]"
            )
            content = (original[: max(0, remaining - len(marker))] + marker)[:remaining]
            truncation_events.append(f"file:{path}:character_budget")
        selected[path] = content
        total_chars += len(content)
    if omitted_files:
        truncation_events.append(
            "selection:omitted:" + ",".join(omitted_files)
        )
    return ContextSelection(
        files=selected,
        truncated_inputs=len(truncation_events),
        omitted_files=tuple(omitted_files),
        truncation_events=tuple(truncation_events),
    )


def _split_text(text: str, max_chars: int) -> list[str]:
    """按字符预算拆分文本，并尽量保持完整行。"""
    if max_chars <= 0:
        raise ValueError("max_chars 必须大于 0")
    if not text:
        return [""]

    chunks: list[str] = []
    current: list[str] = []
    current_chars = 0
    for line in text.splitlines(keepends=True):
        remaining = line
        while remaining:
            capacity = max_chars - current_chars
            if capacity == 0:
                chunks.append("".join(current))
                current = []
                current_chars = 0
                capacity = max_chars
            part = remaining[:capacity]
            current.append(part)
            current_chars += len(part)
            remaining = remaining[len(part):]
            if current_chars == max_chars:
                chunks.append("".join(current))
                current = []
                current_chars = 0
    if current:
        chunks.append("".join(current))
    return chunks or [text[:max_chars]]


def select_reviewer_context_batches(
    file_context: dict[str, str],
    changed_files: list[str],
    reviewer_name: str,
    *,
    max_chars: int | None = None,
) -> list[ContextSelection]:
    """按 Reviewer 预算拆分完整上下文，避免将省略内容静默丢给 Reviewer。"""
    default_budget = _reviewer_context_budget(reviewer_name)
    budget = ContextBudget(
        max_files=default_budget.max_files,
        max_chars=max_chars or default_budget.max_chars,
    )

    def normalise(path: str) -> str:
        return normalize_relative_path(path)

    normalised_context = {
        normalise(path): content for path, content in file_context.items()
    }
    normalised_changed = [normalise(path) for path in changed_files]
    ordered_paths = list(dict.fromkeys(
        [path for path in normalised_changed if path in normalised_context]
        + [path for path in normalised_context if path not in normalised_changed]
    ))

    batches: list[ContextSelection] = []
    current: dict[str, str] = {}
    current_chars = 0
    current_paths: set[str] = set()

    def flush() -> None:
        nonlocal current, current_chars, current_paths
        if current:
            batches.append(ContextSelection(files=current))
        current = {}
        current_chars = 0
        current_paths = set()

    for path in ordered_paths:
        for chunk in _split_text(normalised_context[path], budget.max_chars):
            needs_new_batch = bool(current) and (
                current_chars + len(chunk) > budget.max_chars
                or (
                    path not in current_paths
                    and len(current_paths) >= budget.max_files
                )
            )
            if needs_new_batch:
                flush()
            current[path] = current.get(path, "") + chunk
            current_chars += len(chunk)
            current_paths.add(path)
    flush()
    return batches or [ContextSelection(files={})]


_LINE_PREFIX = re.compile(r"^(\d+)\|(.*)$", re.DOTALL)


def _focus_file_context(content: str, start_line: int, end_line: int) -> str:
    """从带行号的上下文中优先保留变更区域及其前后文。"""
    lines = content.splitlines(keepends=True)
    numbered = []
    for index, line in enumerate(lines, start=1):
        match = _LINE_PREFIX.match(line.rstrip("\r\n"))
        line_number = int(match.group(1)) if match else index
        numbered.append((line_number, line))
    if not numbered:
        return content

    padding = max(0, settings.review_context_padding_lines)
    lower = max(1, start_line - padding)
    upper = max(lower, end_line + padding)
    focused = [line for line_number, line in numbered if lower <= line_number <= upper]
    return "".join(focused) if focused else content


def select_reviewer_unit_context(
    file_context: dict[str, str],
    unit_files: list[str],
    primary_file: str,
    start_line: int,
    end_line: int,
    reviewer_name: str,
) -> ContextSelection:
    """为单个 ReviewUnit 构造上下文，优先变更区域和同单元关联文件。"""
    normalised_context = {
        normalize_relative_path(path): content for path, content in file_context.items()
    }
    ordered_paths = list(dict.fromkeys(
        [normalize_relative_path(primary_file)]
        + [normalize_relative_path(path) for path in unit_files]
    ))
    focused = {
        path: _focus_file_context(
            normalised_context[path], start_line, end_line
        ) if path == normalize_relative_path(primary_file) else normalised_context[path]
        for path in ordered_paths
        if path in normalised_context
    }
    selection = select_reviewer_context_with_metadata(
        focused,
        [normalize_relative_path(primary_file)],
        reviewer_name,
    )
    missing = [path for path in ordered_paths if path not in normalised_context]
    if not missing:
        return selection
    events = list(selection.truncation_events)
    events.append("selection:missing:" + ",".join(missing))
    return ContextSelection(
        files=selection.files,
        truncated_inputs=len(events),
        omitted_files=tuple(dict.fromkeys([*selection.omitted_files, *missing])),
        truncation_events=tuple(dict.fromkeys(events)),
    )


def split_diff_batches(
    diff: str,
    max_chars: int = REVIEW_DIFF_BATCH_CHARS,
) -> list[str]:
    """将完整 Diff 拆成不超过预算的输入批次。"""
    if max_chars <= 0:
        raise ValueError("max_chars 必须大于 0")
    if not diff:
        return [""]
    return _split_text(diff, max_chars)


def pair_reviewer_batches(
    diff_batches: list[str],
    context_batches: list[ContextSelection],
) -> list[tuple[str, ContextSelection]]:
    """将 Diff 与上下文按序配对，避免两类批次形成笛卡尔积。

    两侧长度不一致时循环使用较短的一侧，确保每个 Diff 批次和每个
    上下文批次至少进入一次 Reviewer；上下文工具仍可读取授权范围内的
    其他文件和行段。
    """
    diffs = diff_batches or [""]
    contexts = context_batches or [ContextSelection(files={})]
    batch_count = max(len(diffs), len(contexts))
    return [
        (diffs[index % len(diffs)], contexts[index % len(contexts)])
        for index in range(batch_count)
    ]
