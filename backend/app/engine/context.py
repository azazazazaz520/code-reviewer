"""为 Reviewer 批次构造有界且可复现的源码上下文。"""

from __future__ import annotations

from dataclasses import dataclass
import re

from app.config import (
    REVIEW_CONTEXT_HARD_MAX_CHARS,
    REVIEW_CONTEXT_HARD_MAX_FILES,
    settings,
)
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
    """Reviewer 实际收到的源码上下文及收敛诊断。"""

    files: dict[str, str]
    truncated_inputs: int = 0
    omitted_files: tuple[str, ...] = ()
    truncation_events: tuple[str, ...] = ()
    context_limit_events: tuple[str, ...] = ()


_LINE_PREFIX = re.compile(r"^(\d+)\|(.*)$", re.DOTALL)
REVIEW_DIFF_BATCH_CHARS = 12000


def _reviewer_context_budget() -> ContextBudget:
    """将运行时配置限制在模型上下文的安全上限内。"""
    return ContextBudget(
        max_files=min(
            REVIEW_CONTEXT_HARD_MAX_FILES,
            max(1, settings.review_context_max_files),
        ),
        max_chars=min(
            REVIEW_CONTEXT_HARD_MAX_CHARS,
            max(1, settings.review_context_max_chars),
        ),
    )


def _normalise_context(file_context: dict[str, str]) -> dict[str, str]:
    normalised: dict[str, str] = {}
    for path, content in file_context.items():
        if not isinstance(content, str):
            continue
        try:
            normalised[normalize_relative_path(path)] = content
        except PathSecurityError:
            continue
    return normalised


def _select_context(
    file_context: dict[str, str],
    primary_files: list[str],
) -> ContextSelection:
    """按主文件优先顺序应用统一的文件数和字符预算。"""
    normalised = _normalise_context(file_context)
    primary_set = set(primary_files)
    ordered_paths = sorted(
        normalised,
        key=lambda path: (path not in primary_set, path),
    )
    budget = _reviewer_context_budget()
    selected: dict[str, str] = {}
    omitted: list[str] = []
    limit_events: list[str] = []
    used_chars = 0
    for index, path in enumerate(ordered_paths):
        if len(selected) >= budget.max_files or used_chars >= budget.max_chars:
            omitted.extend(ordered_paths[index:])
            break
        remaining = budget.max_chars - used_chars
        content = normalised[path]
        displayed = content[:remaining]
        selected[path] = displayed
        used_chars += len(displayed)
        if len(displayed) < len(content):
            limit_events.append(f"file:{path}:context_budget")
    if omitted:
        limit_events.append("selection:omitted:" + ",".join(omitted))
    return ContextSelection(
        files=selected,
        omitted_files=tuple(omitted),
        context_limit_events=tuple(limit_events),
    )


def _focus_file_context(content: str, start_line: int, end_line: int) -> str:
    """保留变更行附近的固定窗口，输入行号由 Prepare 阶段提供。"""
    numbered: list[tuple[int, str]] = []
    for fallback_line, line in enumerate(content.splitlines(), start=1):
        match = _LINE_PREFIX.match(line)
        line_number = int(match.group(1)) if match else fallback_line
        numbered.append((line_number, line))
    if not numbered:
        return content
    padding = max(0, settings.review_context_padding_lines)
    lower = max(1, start_line - padding)
    upper = max(lower, end_line + padding)
    focused = [line for line_number, line in numbered if lower <= line_number <= upper]
    return "\n".join(focused) if focused else content


def select_reviewer_context_with_metadata(
    file_context: dict[str, str],
    changed_files: list[str],
    reviewer_name: str,
) -> ContextSelection:
    """兼容旧调用方；正式流程使用批次范围选择上下文。"""
    del reviewer_name
    primary_files = []
    for path in changed_files:
        try:
            primary_files.append(normalize_relative_path(path))
        except PathSecurityError:
            continue
    return _select_context(file_context, primary_files)


def select_reviewer_context(
    file_context: dict[str, str],
    changed_files: list[str],
    reviewer_name: str,
) -> dict[str, str]:
    return select_reviewer_context_with_metadata(
        file_context,
        changed_files,
        reviewer_name,
    ).files


def select_reviewer_batch_context(
    file_context: dict[str, str],
    batch: dict,
    reviewer_name: str,
) -> ContextSelection:
    """聚合一个 Reviewer 批次中所有变更范围附近的确定性上下文。"""
    del reviewer_name
    normalised_context = _normalise_context(file_context)
    focused_lines: dict[str, dict[int, str]] = {}
    missing: list[str] = []
    for item in batch.get("ranges", []):
        try:
            file_path = normalize_relative_path(item.get("file", ""))
        except PathSecurityError:
            continue
        content = normalised_context.get(file_path)
        if content is None:
            missing.append(file_path)
            continue
        line_map = focused_lines.setdefault(file_path, {})
        for fallback_number, line in enumerate(
            _focus_file_context(
                content,
                int(item.get("start_line", 1)),
                int(item.get("end_line", 1)),
            ).splitlines(),
            start=1,
        ):
            match = _LINE_PREFIX.match(line)
            line_number = int(match.group(1)) if match else fallback_number
            line_map[line_number] = line

    focused_context = {
        path: "\n".join(line for _, line in sorted(lines.items()))
        for path, lines in focused_lines.items()
    }
    primary_files = []
    for path in batch.get("primary_files", []):
        try:
            primary_files.append(normalize_relative_path(path))
        except PathSecurityError:
            continue
    selection = _select_context(focused_context, primary_files)
    limit_events = list(selection.context_limit_events)
    if missing:
        limit_events.append(
            "selection:missing:" + ",".join(dict.fromkeys(missing))
        )
    return ContextSelection(
        files=selection.files,
        omitted_files=tuple(dict.fromkeys([*selection.omitted_files, *missing])),
        context_limit_events=tuple(dict.fromkeys(limit_events)),
    )


def build_stable_context_pack(
    file_context: dict[str, str],
    preferred_files: list[str],
    reviewer_name: str,
) -> dict[str, str]:
    """保留历史调用方接口；稳定前缀不再承担批次切分职责。"""
    return select_reviewer_context(file_context, preferred_files, reviewer_name)


def build_stable_file_context(
    file_context: dict[str, str],
    primary_file: str,
    reviewer_name: str,
) -> dict[str, str]:
    return build_stable_context_pack(file_context, [primary_file], reviewer_name)


def _split_text(text: str, max_chars: int) -> list[str]:
    if max_chars <= 0:
        raise ValueError("max_chars 必须大于 0")
    return [text[index:index + max_chars] for index in range(0, len(text), max_chars)] or [""]


def split_diff_batches(
    diff: str,
    max_chars: int = REVIEW_DIFF_BATCH_CHARS,
) -> list[str]:
    """兼容旧调用方；正式流程按完整 Hunk 构造 Reviewer 批次。"""
    return _split_text(diff, max_chars)


def select_reviewer_context_batches(
    file_context: dict[str, str],
    changed_files: list[str],
    reviewer_name: str,
    *,
    max_chars: int | None = None,
) -> list[ContextSelection]:
    """兼容旧调用方，返回一次有界选择，避免隐式跨乘积。"""
    del max_chars
    return [select_reviewer_context_with_metadata(file_context, changed_files, reviewer_name)]


def pair_reviewer_batches(
    diff_batches: list[str],
    context_batches: list[ContextSelection],
) -> list[tuple[str, ContextSelection]]:
    """兼容旧调用方，按序配对批次，不生成笛卡尔积。"""
    diffs = diff_batches or [""]
    contexts = context_batches or [ContextSelection(files={})]
    count = max(len(diffs), len(contexts))
    return [
        (diffs[index % len(diffs)], contexts[index % len(contexts)])
        for index in range(count)
    ]
