"""按变更语义构造稳定的 Reviewer 审查单元。"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from app.config import settings
from app.engine.paths import PathSecurityError, normalize_diff_path, normalize_relative_path
from app.engine.scope import classify_file


HUNK_HEADER = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @")
NUMBERED_SOURCE_LINE = re.compile(r"^(\d+)\|(.*)$")
SYMBOL_DECLARATION = re.compile(
    r"^(?P<indent>\s*)(?:(?:export|public|private|protected|static|async)\s+)*"
    r"(?P<kind>class|function|def)\s+(?P<name>[A-Za-z_$][\w$]*)"
)


@dataclass(frozen=True)
class DiffHunk:
    """包含完整 unified diff 文本和新文件行范围的变更片段。"""

    hunk_id: str
    file_path: str
    start_line: int
    end_line: int
    text: str


def _normalise_file_header(value: str) -> str:
    value = value.strip().split("\t", 1)[0]
    if value == "/dev/null":
        return ""
    try:
        return normalize_diff_path(value)
    except PathSecurityError:
        return ""


def parse_diff_hunks(diff: str) -> list[DiffHunk]:
    """解析 unified diff，保留每个 Hunk 的完整文本。"""
    lines = diff.splitlines(keepends=True)
    current_file = ""
    pending_old_file = ""
    current: dict | None = None
    counters: dict[str, int] = {}
    result: list[DiffHunk] = []

    def flush() -> None:
        nonlocal current
        if not current or not current["file_path"]:
            current = None
            return
        result.append(DiffHunk(**current))
        current = None

    for line in lines:
        if line.startswith("--- "):
            pending_old_file = _normalise_file_header(line[4:])
            continue
        if line.startswith("+++ "):
            current_file = _normalise_file_header(line[4:]) or pending_old_file
            continue
        if line.startswith("diff --git "):
            flush()
            current_file = ""
            pending_old_file = ""
            continue
        match = HUNK_HEADER.match(line)
        if match:
            flush()
            if not current_file:
                continue
            start = int(match.group(1))
            count = int(match.group(2) or "1")
            counters[current_file] = counters.get(current_file, 0) + 1
            current = {
                "hunk_id": f"{current_file}#{counters[current_file]}",
                "file_path": current_file,
                "start_line": start,
                "end_line": max(start, start + count - 1),
                "text": line,
            }
            continue
        if current is not None:
            current["text"] += line
    flush()
    return result


def _unit_id(revision: str, hunk_ids: list[str], suffix: str = "") -> str:
    payload = "\0".join([revision, *hunk_ids, suffix])
    return "unit-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]


def _split_large_hunk(hunk: DiffHunk, revision: str) -> list[dict]:
    max_chars = max(1, settings.review_unit_max_chars)
    if len(hunk.text) <= max_chars:
        return [{
            "unit_id": _unit_id(revision, [hunk.hunk_id]),
            "primary_file": hunk.file_path,
            "files": [hunk.file_path],
            "diff": hunk.text,
            "hunk_ids": [hunk.hunk_id],
            "start_line": hunk.start_line,
            "end_line": hunk.end_line,
        }]

    lines = hunk.text.splitlines(keepends=True)
    units: list[dict] = []
    current: list[str] = []
    current_chars = 0
    part = 0
    for line in lines:
        if current and current_chars + len(line) > max_chars:
            part += 1
            units.append({
                "unit_id": _unit_id(revision, [hunk.hunk_id], str(part)),
                "primary_file": hunk.file_path,
                "files": [hunk.file_path],
                "diff": "".join(current),
                "hunk_ids": [f"{hunk.hunk_id}:part-{part}"],
                "start_line": hunk.start_line,
                "end_line": hunk.end_line,
            })
            current = []
            current_chars = 0
        current.append(line)
        current_chars += len(line)
    if current:
        part += 1
        units.append({
            "unit_id": _unit_id(revision, [hunk.hunk_id], str(part)),
            "primary_file": hunk.file_path,
            "files": [hunk.file_path],
            "diff": "".join(current),
            "hunk_ids": [f"{hunk.hunk_id}:part-{part}"],
            "start_line": hunk.start_line,
            "end_line": hunk.end_line,
        })
    return units


def build_review_units(
    diff: str,
    changed_files: list[str],
    revision: str = "",
    *,
    context_candidates: list[str] | None = None,
    file_context: dict[str, str] | None = None,
) -> list[dict]:
    """按文件和相邻 Hunk 合并变更，生成稳定的 ReviewUnit。"""
    hunks = parse_diff_hunks(diff)
    if not hunks:
        fallback_files = []
        for path in changed_files:
            try:
                normalised = normalize_relative_path(path)
            except PathSecurityError:
                continue
            if normalised not in fallback_files:
                fallback_files.append(normalised)
        if not fallback_files:
            fallback_files = ["(unknown)"]
        # 无结构 Diff 也沿用 V4 Flash 的单元预算，避免旧的 12K 兼容上限
        # 在无法解析 Hunk 时提前丢弃审查输入。
        legacy_budget = max(1, settings.review_unit_max_chars)
        chunks = [diff[i:i + legacy_budget]
                  for i in range(0, len(diff), legacy_budget)]
        chunks = chunks or [""]
        return [
            {
                "unit_id": _unit_id(revision, [], str(index)),
                "primary_file": fallback_files[index % len(fallback_files)],
                "files": [fallback_files[index % len(fallback_files)]],
                "diff": chunk,
                "hunk_ids": [],
                "start_line": 1,
                "end_line": 1,
                "legacy_fallback": True,
            }
            for index, chunk in enumerate(chunks)
        ]

    units: list[dict] = []
    current: list[DiffHunk] = []
    current_chars = 0
    previous: DiffHunk | None = None
    max_chars = max(1, settings.review_unit_max_chars)
    for hunk in hunks:
        adjacent = (
            previous is not None
            and previous.file_path == hunk.file_path
            and hunk.start_line - previous.end_line <= settings.review_context_padding_lines
        )
        if current and (not adjacent or current_chars + len(hunk.text) > max_chars):
            units.append(_merge_hunks(revision, current))
            current = []
            current_chars = 0
        if len(hunk.text) > max_chars:
            if current:
                units.append(_merge_hunks(revision, current))
                current = []
                current_chars = 0
            units.extend(_split_large_hunk(hunk, revision))
        else:
            current.append(hunk)
            current_chars += len(hunk.text)
        previous = hunk
    if current:
        units.append(_merge_hunks(revision, current))

    changed = []
    for path in changed_files:
        try:
            normalised = normalize_relative_path(path)
        except PathSecurityError:
            continue
        if normalised not in changed:
            changed.append(normalised)
    related = []
    for path in context_candidates or []:
        try:
            normalised = normalize_relative_path(path)
        except PathSecurityError:
            continue
        if normalised not in changed and normalised not in related:
            related.append(normalised)
    for index, unit in enumerate(units):
        symbol_context = _find_symbol_context(
            unit["primary_file"],
            unit["start_line"],
            unit["end_line"],
            file_context or {},
        )
        if symbol_context:
            unit.update(symbol_context)
        peers = [
            path for path in changed
            if path != unit["primary_file"]
            and path.rsplit("/", 1)[0] == unit["primary_file"].rsplit("/", 1)[0]
        ]
        assigned_related = related[
            index * max(1, settings.max_related_files_per_unit):
            (index + 1) * max(1, settings.max_related_files_per_unit)
        ]
        unit["files"] = list(dict.fromkeys([
            unit["primary_file"],
            *peers[:max(1, settings.max_related_files_per_unit)],
            *assigned_related,
        ]))
    return units


def reviewer_handles_file(reviewer_name: str, file_path: str) -> bool:
    """判断 Reviewer 是否负责一个变更文件的主审查。"""
    if file_path.startswith("("):
        return True
    kind = classify_file(file_path).kind
    if reviewer_name == "style_reviewer":
        return kind == "source_code"
    if reviewer_name == "performance_reviewer":
        return kind == "source_code" and file_path.lower().endswith(".py")
    if reviewer_name == "security_reviewer":
        return kind in {"source_code", "configuration", "ci_workflow"}
    return True


def _merge_hunks(revision: str, hunks: list[DiffHunk]) -> dict:
    return {
        "unit_id": _unit_id(revision, [hunk.hunk_id for hunk in hunks]),
        "primary_file": hunks[0].file_path,
        "files": [hunks[0].file_path],
        "diff": "".join(hunk.text for hunk in hunks),
        "hunk_ids": [hunk.hunk_id for hunk in hunks],
        "start_line": min(hunk.start_line for hunk in hunks),
        "end_line": max(hunk.end_line for hunk in hunks),
    }


def _find_symbol_context(
    file_path: str,
    start_line: int,
    end_line: int,
    file_context: dict[str, str],
) -> dict:
    """在已收集源码中定位变更所属的函数或类，返回可解释的行范围。"""
    content = file_context.get(file_path)
    if not content:
        return {}

    declarations: list[tuple[int, int, str, str]] = []
    max_line = 0
    for fallback_line, raw_line in enumerate(content.splitlines(), start=1):
        match = NUMBERED_SOURCE_LINE.match(raw_line)
        if match:
            line_number = int(match.group(1))
            source_line = match.group(2)
        else:
            line_number = fallback_line
            source_line = raw_line
        max_line = max(max_line, line_number)
        declaration = SYMBOL_DECLARATION.match(source_line)
        if declaration:
            declarations.append(
                (
                    line_number,
                    len(declaration.group("indent")),
                    declaration.group("kind"),
                    declaration.group("name"),
                )
            )
    if not declarations:
        return {}

    containing = [item for item in declarations if item[0] <= start_line]
    if not containing:
        return {}
    symbol = max(containing, key=lambda item: item[0])
    symbol_start, symbol_indent, symbol_kind, symbol_name = symbol
    following = [
        item for item in declarations
        if item[0] > symbol_start and item[1] <= symbol_indent
    ]
    symbol_end = min((item[0] - 1 for item in following), default=max_line)
    symbol_end = max(symbol_start, symbol_end)
    if start_line < symbol_start or end_line > symbol_end:
        return {}
    return {
        "context_start_line": symbol_start,
        "context_end_line": symbol_end,
        "symbol_context": {
            "kind": symbol_kind,
            "name": symbol_name,
            "file": file_path,
            "start_line": symbol_start,
            "end_line": symbol_end,
        },
    }
