"""Node: 规划审查、执行确定性校验并准备 Reviewer 批次上下文。"""

from __future__ import annotations

from app.config import settings
from app.engine.coverage import initial_coverage
from app.engine.crg import try_crg_context
from app.engine.nodes.build_database import build_database_node
from app.engine.nodes.planning import planning_node
from app.engine.nodes.validate_changes import validate_changes_node
from app.engine.review_units import build_review_units, parse_diff_hunks
from app.engine.state import ReviewState
from app.engine.tools.context import TaskToolCache, TaskToolContext, build_changed_file_refs
from app.engine.tools.read_file import FileReadPage, read_file_page_in_context


def _merge_page(cache: dict[str, str], page: FileReadPage) -> None:
    """按行号合并同一文件的聚焦上下文，避免重叠窗口重复发送。"""
    existing = cache.get(page.file_path, "")
    lines: dict[int, str] = {}
    for raw_line in [*existing.splitlines(), *page.content.splitlines()]:
        prefix, separator, _ = raw_line.partition("|")
        if separator and prefix.isdigit():
            lines[int(prefix)] = raw_line
    cache[page.file_path] = "\n".join(
        line for _, line in sorted(lines.items())
    )


def _record_range(progress: dict, start_line: int, end_line: int) -> None:
    ranges = [
        [int(item[0]), int(item[1])]
        for item in progress.get("read_ranges", [])
        if isinstance(item, (list, tuple)) and len(item) == 2
    ]
    ranges.append([start_line, end_line])
    ranges.sort()
    merged: list[list[int]] = []
    for current_start, current_end in ranges:
        if merged and current_start <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], current_end)
        else:
            merged.append([current_start, current_end])
    progress["read_ranges"] = merged


def _load_page(
    state: ReviewState,
    tool_context: TaskToolContext,
    tool_cache: TaskToolCache,
    file_path: str,
    start_line: int,
    max_lines: int,
) -> FileReadPage:
    arguments = {
        "file_path": file_path,
        "start_line": start_line,
        "max_lines": max_lines,
    }
    result, _ = tool_cache.get_or_load(
        state.get("snapshot_revision", ""),
        "ReadFile",
        arguments,
        lambda: read_file_page_in_context(tool_context, **arguments),
    )
    if isinstance(result, FileReadPage):
        return result
    return FileReadPage(
        file_path=file_path,
        start_line=0,
        end_line=0,
        total_lines=0,
        error="Error: 上下文读取返回了无效结果",
    )


def _prepare_file_context(state: ReviewState) -> None:
    """读取小文件全文或每个 Hunk 附近的固定窗口。"""
    tool_context = state.get("tool_context")
    if not isinstance(tool_context, TaskToolContext):
        return
    tool_cache = state.get("tool_cache")
    if not isinstance(tool_cache, TaskToolCache):
        tool_cache = TaskToolCache()
        state["tool_cache"] = tool_cache

    refs_by_file = {
        ref.file_path: ref for ref in tool_context.approved_context_refs
        if ref.source == "changed_file"
    }
    hunks_by_file: dict[str, list] = {}
    for hunk in parse_diff_hunks(state.get("raw_diff", "")):
        hunks_by_file.setdefault(hunk.file_path, []).append(hunk)

    cache: dict[str, str] = {}
    progress_map: dict[str, dict] = {}
    context_errors: dict[str, str] = {}
    padding = max(0, settings.review_context_padding_lines)
    for file_path in state.get("changed_files", []):
        ref = refs_by_file.get(file_path)
        if ref is None:
            # 删除文件和二进制文件没有快照源码，Diff 仍然保留完整审查证据。
            continue
        if ref.end_line <= 200:
            requested_ranges = [(1, ref.end_line)]
        else:
            requested_ranges = [
                (
                    max(1, hunk.start_line - padding),
                    min(ref.end_line, hunk.end_line + padding),
                )
                for hunk in hunks_by_file.get(file_path, [])
            ]
            if not requested_ranges:
                requested_ranges = [(1, min(200, ref.end_line))]

        progress: dict = {"read_ranges": []}
        for range_start, range_end in requested_ranges:
            cursor = range_start
            while cursor <= range_end:
                page = _load_page(
                    state,
                    tool_context,
                    tool_cache,
                    file_path,
                    cursor,
                    min(200, range_end - cursor + 1),
                )
                if page.error:
                    context_errors[file_path] = page.error
                    progress["error"] = page.error
                    break
                _merge_page(cache, page)
                _record_range(progress, page.start_line, page.end_line)
                cursor = page.end_line + 1
        progress["complete"] = not progress.get("error")
        progress_map[file_path] = progress

    state["file_context_cache"] = cache
    state["context_progress"] = progress_map
    state["context_errors"] = context_errors


def prepare_review_node(state: ReviewState) -> ReviewState:
    """将默认审查准备工作收口为一次确定性执行。"""
    planning_node(state)
    validate_changes_node(state)

    repo_path = state.get("repo_id", ".")
    changed_files = list(state.get("changed_files", []))
    refs = build_changed_file_refs(
        repo_path,
        changed_files,
        revision=state.get("snapshot_revision", ""),
    )
    state["tool_context"] = TaskToolContext(
        repo_root=repo_path,
        revision=state.get("snapshot_revision", ""),
        approved_context_refs=tuple(refs),
    )
    state["approved_context_refs"] = [ref.as_dict() for ref in refs]
    state["context_candidates"] = changed_files
    state["database_status"] = "skipped"
    state["extraction_status"] = "skipped"

    if settings.crg_enabled:
        build_database_node(state)
        state["crg_enabled"] = try_crg_context(state, repo_path, changed_files)
    else:
        state["crg_enabled"] = False

    _prepare_file_context(state)
    state["review_units"] = build_review_units(
        state.get("raw_diff", ""),
        changed_files,
        state.get("snapshot_revision", ""),
        context_candidates=state.get("context_candidates", []),
        file_context=state.get("file_context_cache", {}),
    )

    coverage = initial_coverage(
        changed_files,
        state.get("raw_diff", ""),
        database_status=(
            state.get("database_status") if settings.crg_enabled else None
        ),
        extraction_status=(
            state.get("extraction_status") if settings.crg_enabled else None
        ),
    )
    coverage.update({
        "covered_files": coverage["planned_files"],
        "uncovered_files": [],
        "covered_hunks": coverage["planned_hunks"],
        "uncovered_hunks": [],
        "coverage_status": "complete",
        "context_progress": state.get("context_progress", {}),
        "context_request_failures": len(state.get("context_errors", {})),
        "context_request_failure_events": [
            {
                "file": file_path,
                "message": message,
            }
            for file_path, message in state.get("context_errors", {}).items()
        ],
    })
    state["coverage"] = coverage
    state["context_initialized"] = True
    state["context_round"] = 1

    if hook := state.get("_log_hook"):
        hook(
            step="prepare_review",
            level="info",
            message=(
                f"审查准备完成：{len(changed_files)} 个变更文件，"
                f"{len(state['review_units'])} 个 ReviewUnit"
            ),
        )
    return state
