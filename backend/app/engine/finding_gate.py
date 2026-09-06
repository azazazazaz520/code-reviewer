"""Finding 统一质量门槛。

Reviewer 产生候选意见，FindingGate 负责将其收敛为可以进入最终报告的问题。
"""

from __future__ import annotations

import re
from collections import defaultdict
from difflib import SequenceMatcher

from app.engine.paths import (
    PathSecurityError,
    file_line_count,
    normalize_diff_path,
    normalize_relative_path,
    resolve_snapshot_path,
)


VALID_SEVERITIES = {"critical", "high", "medium", "low"}
UNCERTAIN_MARKERS = (
    "无法确认",
    "无法验证",
    "未能验证",
    "无法判断",
    "建议检查",
    "cannot confirm",
    "unable to verify",
    "could not verify",
    "external_unverified",
)
HUNK_PATTERN = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
TITLE_NORMALISE_PATTERN = re.compile(r"[\s\u3000,，。.、;；:：!！?？()（）\[\]【】/\\\-_]+")
# 同位置标题相似度达到该阈值视为同一问题的不同措辞。
TITLE_SIMILARITY_THRESHOLD = 0.7
VALID_IMPACTS = {"behavior", "security", "compatibility", "build", "maintainability"}
GENERIC_EVIDENCE_PREFIXES = (
    "审查快照定位到",
    "确定性校验器定位到",
)


def _normalise_title(title: str) -> str:
    """标题规范化：小写并去除空白与常见分隔标点，用于识别措辞差异的重复。"""
    return TITLE_NORMALISE_PATTERN.sub("", str(title or "")).lower()


def _title_similarity(a: str, b: str) -> float:
    """基于最长公共子序列的比例判断两条标题是否语义重复。"""
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _is_duplicate_of_accepted(
    accepted_titles: list[str],
    title: str,
) -> bool:
    """同位置已有标题中，是否存在与当前标题语义重复的条目。"""
    normalised = _normalise_title(title)
    return any(
        _title_similarity(normalised, _normalise_title(existing))
        >= TITLE_SIMILARITY_THRESHOLD
        for existing in accepted_titles
    )


def _normalise_path(path: str, *, diff_path: bool = False) -> str:
    try:
        return normalize_diff_path(path) if diff_path else normalize_relative_path(path)
    except PathSecurityError:
        return ""


def changed_line_map(diff: str) -> dict[str, set[int]]:
    """解析 unified diff 中新增或修改行。"""
    result: dict[str, set[int]] = defaultdict(set)
    current_file = ""
    new_line = 0

    for raw_line in diff.splitlines():
        if raw_line.startswith("+++ "):
            current_file = _normalise_path(raw_line[4:], diff_path=True)
            continue

        match = HUNK_PATTERN.match(raw_line)
        if match:
            new_line = int(match.group(1))
            continue

        if not current_file or new_line <= 0:
            continue

        if raw_line.startswith("+") and not raw_line.startswith("+++"):
            result[current_file].add(new_line)
            new_line += 1
        elif raw_line.startswith("-"):
            continue
        else:
            new_line += 1

    return dict(result)


def _has_uncertain_language(finding: dict) -> bool:
    text = " ".join(
        str(finding.get(field, ""))
        for field in ("title", "reason", "suggestion", "evidence", "evidence_type")
    ).lower()
    return any(marker.lower() in text for marker in UNCERTAIN_MARKERS)


def _is_valid_shape(finding: dict) -> bool:
    required = ("severity", "file", "line", "title", "reason", "suggestion", "impact")
    return (
        isinstance(finding, dict)
        and all(finding.get(field) not in (None, "") for field in required)
        and finding.get("severity") in VALID_SEVERITIES
        and isinstance(finding.get("line"), int)
        and not isinstance(finding.get("line"), bool)
        and str(finding.get("impact", "")).strip().lower() in VALID_IMPACTS
    )


def _has_concrete_evidence(finding: dict) -> bool:
    """确认 Finding 带有可复核证据，避免把自动定位信息当作证明。"""
    evidence = finding.get("evidence")
    if not isinstance(evidence, str):
        return False
    value = evidence.strip()
    if len(value) < 3:
        return False
    return not value.startswith(GENERIC_EVIDENCE_PREFIXES)


def filter_findings(
    findings: list[dict],
    changed_files: list[str],
    diff: str,
    *,
    repo_root: str | None = None,
    approved_context_refs: list[dict] | None = None,
    rejection_reasons: dict[str, int] | None = None,
) -> list[dict]:
    """过滤越界、无证据、不确定和重复的候选 Finding。"""

    def reject(reason: str) -> None:
        if rejection_reasons is not None:
            rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1

    changed = {_normalise_path(path) for path in changed_files}
    changed.discard("")
    approved_refs = approved_context_refs or []

    def related_range(file_path: str, line: int) -> dict | None:
        for ref in approved_refs:
            try:
                start_line = int(ref.get("start_line", 0))
                end_line = int(ref.get("end_line", 0))
            except (TypeError, ValueError):
                continue
            if (
                _normalise_path(str(ref.get("file", ""))) == file_path
                and ref.get("source") == "query_result"
                and ref.get("result_id")
                and ref.get("database_id")
                and start_line >= 1
                and end_line >= start_line
                and line >= start_line
                and line <= end_line
            ):
                return ref
        return None

    changed_lines = changed_line_map(diff)
    accepted: list[dict] = []
    seen: set[tuple[str, int, str]] = set()
    line_count_cache = {}
    # 同位置（file + line）已接受标题列表，用于识别措辞差异的语义重复。
    accepted_titles_at_location: dict[tuple[str, int], list[str]] = defaultdict(list)

    for finding in findings:
        if not _is_valid_shape(finding):
            reject("invalid_shape")
            continue

        file_path = _normalise_path(finding["file"])
        if not file_path:
            reject("invalid_file_path")
            continue

        related_ref = None if file_path in changed else related_range(file_path, finding["line"])
        if file_path not in changed and related_ref is None:
            reject("unrelated_file")
            continue

        evidence_source = finding.get("_evidence_source", "reviewer")
        requested_evidence_type = finding.get("evidence_type", "reviewer")
        if requested_evidence_type == "external_unverified" or _has_uncertain_language(finding):
            reject("uncertain_claim")
            continue
        if not _has_concrete_evidence(finding):
            reject("untrusted_evidence")
            continue
        if evidence_source == "validator":
            evidence_type = "static_check"
        elif evidence_source == "tool":
            evidence_type = "tool_verified"
        else:
            # 模型不能通过输出 static_check 或 tool_call_id 提高证据等级。
            evidence_type = "reviewer"

        line = finding["line"]
        if repo_root:
            try:
                resolved = resolve_snapshot_path(repo_root, file_path)
                if not resolved.is_file():
                    reject("file_not_found")
                    continue
                line_count = line_count_cache.get(resolved)
                if line_count is None:
                    line_count = file_line_count(resolved)
                    line_count_cache[resolved] = line_count
            except (OSError, PathSecurityError):
                reject("file_not_found")
                continue
        else:
            line_count = None

        if line < 0 or (line_count is not None and line > line_count):
            reject("line_out_of_range")
            continue
        if line <= 0:
            # 确定性校验器可以对整个已变更文件给出契约问题；LLM Reviewer
            # 必须定位到具体变更行，避免报告无法复核的主观意见。
            if evidence_type != "static_check" or file_path not in changed:
                reject("line_out_of_range")
                continue
            context_line = False
        elif evidence_type != "static_check":
            file_lines = changed_lines.get(file_path)
            context_line = bool(file_lines and line not in file_lines)
            # Finding 仍定位在当前修改文件，只是落在具体修改行附近。
            # 保留它并明确标记，交给报告使用者复核，避免静默丢失。
        else:
            context_line = False

        if related_ref is not None:
            context_line = True

        key = (file_path, line, str(finding["title"]).strip())
        if key in seen:
            reject("duplicate_finding")
            continue
        seen.add(key)

        if line > 0:
            location = (file_path, line)
            if _is_duplicate_of_accepted(accepted_titles_at_location[location], finding["title"]):
                reject("duplicate_finding")
                continue
            accepted_titles_at_location[location].append(finding["title"])

        accepted_finding = dict(finding)
        accepted_finding["file"] = file_path
        accepted_finding.pop("_evidence_source", None)
        accepted_finding["impact"] = str(accepted_finding["impact"]).strip().lower()
        accepted_finding["evidence_type"] = evidence_type
        if evidence_type == "static_check":
            accepted_finding.setdefault("confidence", 1.0)
        accepted_finding["evidence_refs"] = [
            {
                "source": "query_result" if related_ref else "diff",
                "file": file_path,
                "line_start": line or 1,
                "line_end": line or 1,
                **(
                    {
                        "result_id": related_ref.get("result_id"),
                        "database_id": related_ref.get("database_id"),
                    }
                    if related_ref
                    else {}
                ),
            }
        ]
        if context_line:
            accepted_finding["evidence_type"] = "reviewer_context"
        accepted.append(accepted_finding)

    return accepted
