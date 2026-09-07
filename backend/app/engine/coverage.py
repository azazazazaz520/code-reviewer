"""审查输入覆盖范围计算。"""

from __future__ import annotations

import re

from app.engine.paths import PathSecurityError, normalize_diff_path, normalize_relative_path


HUNK_PATTERN = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @")


def diff_hunks(diff: str) -> list[dict]:
    """提取 Diff Hunk 的文件和新文件行范围。"""
    hunks: list[dict] = []
    current_file = ""
    for raw_line in diff.splitlines():
        if raw_line.startswith("+++ "):
            try:
                current_file = normalize_diff_path(raw_line[4:])
            except PathSecurityError:
                current_file = ""
            continue
        match = HUNK_PATTERN.match(raw_line)
        if not match or not current_file:
            continue
        start = int(match.group(1))
        count = int(match.group(2) or "1")
        hunks.append(
            {
                "id": f"{current_file}#{sum(h['file'] == current_file for h in hunks) + 1}",
                "file": current_file,
                "start_line": start,
                "end_line": max(start, start + count - 1),
            }
        )
    return hunks


def initial_coverage(
    changed_files: list[str],
    diff: str,
    candidates: list[str] | None = None,
    *,
    database_status: str | None = None,
    extraction_status: str | None = None,
) -> dict:
    planned = _normalise_candidates(changed_files if candidates is None else candidates)
    hunks = diff_hunks(diff)
    coverage = {
        "planned_files": len(planned),
        "covered_files": 0,
        "uncovered_files": planned,
        "planned_hunks": len(hunks),
        "covered_hunks": 0,
        "uncovered_hunks": [hunk["id"] for hunk in hunks],
        "truncated_inputs": 0,
        "truncation_events": [],
        "critical_truncated_inputs": 0,
        "critical_truncation_events": [],
        "context_limited_inputs": 0,
        "context_limit_events": [],
        "context_progress": {},
        "database_status": database_status,
        "extraction_status": extraction_status,
    }
    coverage["coverage_status"] = "complete" if not planned and not hunks else "incomplete"
    if database_status and database_status != "ready":
        coverage["coverage_status"] = "incomplete"
    if extraction_status and extraction_status != "complete":
        coverage["coverage_status"] = "incomplete"
    return coverage


def _normalise_candidate(path: str) -> str:
    return normalize_relative_path(path)


def _normalise_candidates(paths: list[str]) -> list[str]:
    """统一规范化候选路径；任一非法路径都让当前覆盖计算失败。"""
    return list(dict.fromkeys(_normalise_candidate(path) for path in paths))


def _range_is_covered(progress: dict, start_line: int, end_line: int) -> bool:
    if progress.get("error"):
        return False
    for covered_start, covered_end in progress.get("read_ranges", []):
        if start_line >= covered_start and end_line <= covered_end:
            return True
    return False


def update_coverage(
    coverage: dict,
    candidates: list[str],
    file_context_cache: dict[str, str],
    diff: str,
    *,
    database_status: str | None = None,
    extraction_status: str | None = None,
    context_progress: dict[str, dict] | None = None,
    truncated_inputs: int | None = None,
) -> dict:
    """根据成功读取的文件和 Diff Hunk 更新覆盖状态。"""
    planned = _normalise_candidates(candidates)
    progress = (
        context_progress
        if context_progress is not None
        else coverage.get("context_progress") or None
    )
    failed_files = {
        _normalise_candidate(path) for path, content in file_context_cache.items()
        if isinstance(content, str) and content.startswith("Error:")
    }
    if progress is None:
        covered_files = [
            path for path in planned
            if path in file_context_cache and path not in failed_files
        ]
    else:
        hunks_by_file: dict[str, list[dict]] = {}
        for hunk in diff_hunks(diff):
            hunks_by_file.setdefault(hunk["file"], []).append(hunk)
        covered_files = []
        for path in planned:
            if path in failed_files:
                continue
            file_progress = progress.get(path, {})
            relevant_hunks = hunks_by_file.get(path, [])
            if relevant_hunks:
                if all(
                    _range_is_covered(
                        file_progress,
                        hunk["start_line"],
                        hunk["end_line"],
                    )
                    for hunk in relevant_hunks
                ):
                    covered_files.append(path)
            elif file_progress.get("complete"):
                covered_files.append(path)
    hunks = diff_hunks(diff)
    covered_hunks = [
        hunk for hunk in hunks
        if hunk["file"] in covered_files
        and (
            progress is None
            or _range_is_covered(
                progress.get(hunk["file"], {}),
                hunk["start_line"],
                hunk["end_line"],
            )
        )
    ]
    next_coverage = dict(coverage)
    next_coverage.update(
        {
            "planned_files": len(planned),
            "covered_files": len(covered_files),
            "uncovered_files": [path for path in planned if path not in covered_files],
            "planned_hunks": len(hunks),
            "covered_hunks": len(covered_hunks),
            "uncovered_hunks": [
                hunk["id"] for hunk in hunks if hunk not in covered_hunks
            ],
            "database_status": database_status or next_coverage.get("database_status"),
            "extraction_status": extraction_status or next_coverage.get("extraction_status"),
            "context_progress": progress if progress is not None else next_coverage.get("context_progress", {}),
        }
    )
    if truncated_inputs is not None:
        next_coverage["truncated_inputs"] = truncated_inputs
    complete = not next_coverage["uncovered_files"] and not next_coverage["uncovered_hunks"]
    if database_status and database_status != "ready":
        complete = False
    if extraction_status and extraction_status != "complete":
        complete = False
    if next_coverage.get("truncated_inputs", 0):
        complete = False
    next_coverage["coverage_status"] = "complete" if complete else "incomplete"
    return next_coverage
