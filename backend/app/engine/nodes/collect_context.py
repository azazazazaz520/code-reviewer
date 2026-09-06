"""Node: 收集变更文件内容到上下文缓存。

先建立候选文件集合，再按轮次增量读取，避免 Reflection 重复读取同一批文件。
CRG 的结构性影响在上下文收集完成后才可用，作为硬触发器补入审查计划。
"""

from __future__ import annotations

from app.config import settings
from app.engine.coverage import update_coverage
from app.engine.paths import normalize_relative_path
from app.engine.state import ReviewState
from app.engine.crg import try_crg_context
from app.engine.tools.context import TaskToolCache, TaskToolContext, build_changed_file_refs
from app.engine.tools.read_file import FileReadPage, read_file_page_in_context
from app.engine.execution import ReviewBudgetExceeded, ReviewCancelled
from app.engine.review_units import parse_diff_hunks


def read_file(
    context: TaskToolContext,
    file_path: str,
    start_line: int = 1,
    max_lines: int = 200,
    *,
    with_metadata: bool = False,
) -> str | FileReadPage:
    """通过任务上下文读取文件，保留节点级测试的替换接缝。"""
    page = read_file_page_in_context(context, file_path, start_line, max_lines)
    return page if with_metadata else page.render()


def _normalise_candidate(path: str) -> str:
    return normalize_relative_path(path)


def _required_ranges(tool_context: TaskToolContext, file_path: str) -> list[tuple[int, int]]:
    return [
        (ref.start_line, ref.end_line)
        for ref in tool_context.refs_for(file_path)
        if ref.start_line >= 1 and ref.end_line >= ref.start_line
    ]


def _next_unread_range(
    required_ranges: list[tuple[int, int]],
    read_ranges: list[list[int]],
) -> tuple[int, int] | None:
    """返回授权范围内第一个尚未读取的页。"""
    covered = sorted(
        (int(item[0]), int(item[1]))
        for item in read_ranges
        if len(item) == 2
    )
    for required_start, required_end in sorted(required_ranges):
        cursor = required_start
        for covered_start, covered_end in covered:
            if covered_end < cursor:
                continue
            if covered_start > cursor:
                return cursor, min(required_end, cursor + 199)
            cursor = max(cursor, covered_end + 1)
            if cursor > required_end:
                break
        if cursor <= required_end:
            return cursor, min(required_end, cursor + 199)
    return None


def _mark_range(progress: dict, start_line: int, end_line: int) -> None:
    ranges = [
        [int(item[0]), int(item[1])]
        for item in progress.get("read_ranges", [])
        if len(item) == 2
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


def _is_complete(progress: dict, required_ranges: list[tuple[int, int]]) -> bool:
    if progress.get("error") or not required_ranges:
        return False
    return _next_unread_range(required_ranges, progress.get("read_ranges", [])) is None


def _append_page(cache: dict[str, str], file_path: str, rendered: str) -> None:
    previous = cache.get(file_path, "")
    cache[file_path] = f"{previous}\n{rendered}" if previous else rendered


def _read_context_page(
    tool_context: TaskToolContext,
    file_path: str,
    required_range: tuple[int, int],
    progress: dict,
    cache: dict[str, str],
    context_errors: dict[str, str],
    tool_cache: TaskToolCache | None = None,
) -> bool:
    """读取指定范围的一个页面，并将成功或失败结果写入任务状态。"""
    effective_required_end = min(
        required_range[1],
        int(progress.get("total_lines", required_range[1])),
    )
    if effective_required_end < required_range[0]:
        return False
    next_range = _next_unread_range(
        [(required_range[0], effective_required_end)],
        progress.get("read_ranges", []),
    )
    if next_range is None:
        return False
    read_arguments = {
        "file_path": file_path,
        "start_line": next_range[0],
        "max_lines": next_range[1] - next_range[0] + 1,
    }

    def load_page():
        return read_file(
            tool_context,
            file_path,
            start_line=next_range[0],
            max_lines=next_range[1] - next_range[0] + 1,
            with_metadata=True,
        )

    if tool_cache:
        page_or_content, _ = tool_cache.get_or_load(
            tool_context.revision,
            "ReadFile",
            read_arguments,
            load_page,
        )
    else:
        page_or_content = load_page()
    if isinstance(page_or_content, FileReadPage):
        if page_or_content.error:
            progress["error"] = page_or_content.error
            progress["complete"] = False
            cache[file_path] = page_or_content.error
            context_errors[file_path] = page_or_content.error
            return True
        _mark_range(progress, page_or_content.start_line, page_or_content.end_line)
        progress["total_lines"] = page_or_content.total_lines
        _append_page(cache, file_path, page_or_content.render())
        return True

    # 节点测试和第三方扩展可能替换旧的字符串接口；这类替换无法提供
    # 分页元数据，只能将其作为一个完整的兼容性结果记录。
    content = str(page_or_content)
    cache[file_path] = content
    progress["complete"] = not content.startswith("Error:")
    progress["read_ranges"] = [[next_range[0], next_range[1]]]
    if content.startswith("Error:"):
        progress["error"] = content
        context_errors[file_path] = content
    return True


def _priority_ranges(state: ReviewState, tool_context: TaskToolContext) -> dict[str, list[tuple[int, int]]]:
    """优先生成变更 Hunk 和查询结果引用的局部上下文范围。"""
    padding = max(0, settings.review_context_padding_lines)
    ranges: dict[str, list[tuple[int, int]]] = {}
    for hunk in parse_diff_hunks(state.get("raw_diff", "")):
        ranges.setdefault(hunk.file_path, []).append(
            (max(1, hunk.start_line - padding), hunk.end_line + padding)
        )
    for ref in tool_context.approved_context_refs:
        if ref.source != "query_result":
            continue
        ranges.setdefault(ref.file_path, []).append((ref.start_line, ref.end_line))
    return {
        path: sorted(set(file_ranges))
        for path, file_ranges in ranges.items()
    }


def _stop_context_collection(state: ReviewState) -> bool:
    callback = state.get("_cancel_check")
    if callable(callback) and callback():
        state["cancel_requested"] = True
        return True
    budget = state.get("_review_budget_object")
    if budget is not None:
        try:
            budget.check(callback if callable(callback) else None)
        except ReviewCancelled:
            state["cancel_requested"] = True
            return True
        except ReviewBudgetExceeded:
            return True
    return False


def collect_context_node(state: ReviewState) -> ReviewState:
    repo_path = state.get("repo_id", ".")
    changed_files = state.get("changed_files", [])

    if not state.get("review_plan"):
        state["context_initialized"] = True
        state["context_candidates"] = []
        state["coverage"] = update_coverage(
            state.get("coverage", {}),
            [],
            state.get("file_context_cache", {}),
            "",
            database_status=state.get("database_status"),
            extraction_status=state.get("extraction_status"),
            context_progress=state.get("context_progress", {}),
        )
        if hook := state.get("_log_hook"):
            hook(
                step="collect_context",
                level="info",
                message="当前变更由确定性校验器覆盖，无需收集 LLM 上下文",
            )
        return state

    if _stop_context_collection(state):
        return state

    if hook := state.get("_log_hook"):
        hook(step="collect_context", level="info",
             message=f"正在收集文件上下文 ({len(state.get('changed_files', []))} 个文件)...")

    # 只在第一轮建立候选文件集合；后续 Reflection 只读取下一页。
    if not state.get("context_initialized"):
        state["context_initialized"] = True
        if settings.crg_enabled and try_crg_context(state, repo_path, changed_files):
            state["crg_enabled"] = True
        else:
            state["crg_enabled"] = False
            state["context_candidates"] = list(dict.fromkeys(
                _normalise_candidate(path) for path in changed_files
            ))

    tool_context = state.get("tool_context")
    if not isinstance(tool_context, TaskToolContext):
        refs = build_changed_file_refs(
            repo_path,
            changed_files,
            revision=state.get("snapshot_revision", ""),
        )
        tool_context = TaskToolContext(
            repo_root=repo_path,
            revision=state.get("snapshot_revision", ""),
            database_id=state.get("database_id", ""),
            approved_context_refs=tuple(refs),
        )
        state["tool_context"] = tool_context
        state["approved_context_refs"] = [ref.as_dict() for ref in refs]

    candidates = list(dict.fromkeys(
        _normalise_candidate(path)
        for path in state.get("context_candidates", changed_files)
    ))
    state["context_candidates"] = candidates
    cache = dict(state.get("file_context_cache", {}))
    progress_map = dict(state.get("context_progress", {}))
    tool_cache = state.get("tool_cache")
    if not isinstance(tool_cache, TaskToolCache):
        tool_cache = TaskToolCache()
        state["tool_cache"] = tool_cache
    batch_size = max(1, settings.context_files_per_round)

    # 优先处理尚未开始的文件，再继续读取已经打开但尚未完成的文件，
    # 保证大文件分页不会长期占用整个批次。
    pending = []
    for file_path in candidates:
        progress = progress_map.get(file_path, {})
        if not progress.get("complete") and not progress.get("error"):
            pending.append(file_path)
    batch = sorted(
        pending,
        key=lambda path: bool(progress_map.get(path, {}).get("read_ranges")),
    )[:batch_size]

    new_count = 0
    priority_ranges = _priority_ranges(state, tool_context)
    for file_path, ranges in priority_ranges.items():
        if file_path not in candidates:
            continue
        progress = dict(progress_map.get(file_path, {}))
        for required_range in ranges:
            while not progress.get("error"):
                if _stop_context_collection(state):
                    break
                did_read = _read_context_page(
                    tool_context,
                    file_path,
                    required_range,
                    progress,
                    cache,
                    state.setdefault("context_errors", {}),
                    tool_cache,
                )
                if not did_read:
                    break
                new_count += 1
                if _next_unread_range([required_range], progress.get("read_ranges", [])) is None:
                    break
            if state.get("cancel_requested"):
                break
        if not progress.get("error"):
            progress["complete"] = _is_complete(
                progress,
                _required_ranges(tool_context, file_path),
            )
        progress_map[file_path] = progress
        if state.get("cancel_requested"):
            break

    if state.get("cancel_requested"):
        state["context_round"] = state.get("context_round", 0) + 1
        state["file_context_cache"] = cache
        state["context_progress"] = progress_map
        state["coverage"] = update_coverage(
            state.get("coverage", {}),
            candidates,
            cache,
            state.get("raw_diff", ""),
            database_status=state.get("database_status"),
            extraction_status=state.get("extraction_status"),
            context_progress=progress_map,
            truncated_inputs=state.get("coverage", {}).get("truncated_inputs", 0),
        )
        return state

    for file_path in batch:
        progress = dict(progress_map.get(file_path, {}))
        required_ranges = _required_ranges(tool_context, file_path)
        if not required_ranges:
            progress.update({"complete": False, "error": "Error: file context is not approved"})
            progress_map[file_path] = progress
            cache[file_path] = progress["error"]
            state.setdefault("context_errors", {})[file_path] = progress["error"]
            continue

        if _stop_context_collection(state):
            break
        next_range = _next_unread_range(required_ranges, progress.get("read_ranges", []))
        if next_range is None:
            progress["complete"] = True
            progress_map[file_path] = progress
            continue

        _read_context_page(
            tool_context,
            file_path,
            next_range,
            progress,
            cache,
            state.setdefault("context_errors", {}),
            tool_cache,
        )
        progress["complete"] = _is_complete(progress, required_ranges)
        progress_map[file_path] = progress
        new_count += 1

    state["context_round"] = state.get("context_round", 0) + 1
    state["file_context_cache"] = cache
    state["context_progress"] = progress_map
    state["coverage"] = update_coverage(
        state.get("coverage", {}),
        candidates,
        cache,
        state.get("raw_diff", ""),
        database_status=state.get("database_status"),
        extraction_status=state.get("extraction_status"),
        context_progress=progress_map,
        truncated_inputs=state.get("coverage", {}).get("truncated_inputs", 0),
    )

    # CRG 的结构性影响在上下文收集完成后才可用，作为硬触发器补入计划。
    impact = state.get("impact_radius")
    if impact and (
        impact.get("impacted_nodes", 0) > 20
        or impact.get("changed_nodes", 0) > 5
    ):
        if "security_reviewer" not in state.get("review_plan", []):
            state.setdefault("review_plan", []).append("security_reviewer")

    source = "CRG" if state.get("crg_enabled") else "Normal"
    if hook := state.get("_log_hook"):
        hook(
            step="collect_context",
            level="info",
            message=(
                f"已收集 {len(cache)} 个文件 ({source})，"
                f"本轮新增 {new_count} 页"
            ),
        )

    return state
