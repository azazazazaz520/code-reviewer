"""Finding 统一质量门槛。

Reviewer 产生候选意见，FindingGate 负责将其收敛为可以进入最终报告的问题。
"""

from __future__ import annotations

import re
from collections import defaultdict
from difflib import SequenceMatcher


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


def _normalise_path(path: str) -> str:
    value = str(path or "").replace("\\", "/").strip()
    if value.startswith("a/") or value.startswith("b/"):
        value = value[2:]
    return value.lstrip("./")


def changed_line_map(diff: str) -> dict[str, set[int]]:
    """解析 unified diff 中新增或修改行。"""
    result: dict[str, set[int]] = defaultdict(set)
    current_file = ""
    new_line = 0

    for raw_line in diff.splitlines():
        if raw_line.startswith("+++ "):
            current_file = _normalise_path(raw_line[4:])
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
        for field in ("title", "reason", "suggestion", "evidence_type")
    ).lower()
    return any(marker.lower() in text for marker in UNCERTAIN_MARKERS)


def _is_valid_shape(finding: dict) -> bool:
    required = ("severity", "file", "line", "title", "reason", "suggestion")
    return (
        isinstance(finding, dict)
        and all(finding.get(field) not in (None, "") for field in required)
        and finding.get("severity") in VALID_SEVERITIES
        and isinstance(finding.get("line"), int)
    )


def filter_findings(
    findings: list[dict],
    changed_files: list[str],
    diff: str,
) -> list[dict]:
    """过滤越界、无证据、不确定和重复的候选 Finding。"""
    changed = {_normalise_path(path) for path in changed_files}
    changed_lines = changed_line_map(diff)
    accepted: list[dict] = []
    seen: set[tuple[str, int, str]] = set()
    # 同位置（file + line）已接受标题列表，用于识别措辞差异的语义重复。
    accepted_titles_at_location: dict[tuple[str, int], list[str]] = defaultdict(list)

    for finding in findings:
        if not _is_valid_shape(finding):
            continue

        file_path = _normalise_path(finding["file"])
        if file_path not in changed:
            continue

        evidence_type = finding.get("evidence_type", "reviewer")
        if evidence_type == "external_unverified" or _has_uncertain_language(finding):
            continue

        line = finding["line"]
        if line <= 0:
            # 确定性校验器可以对整个已变更文件给出契约问题；LLM Reviewer
            # 必须定位到具体变更行，避免报告无法复核的主观意见。
            if evidence_type != "static_check":
                continue
            context_line = False
        elif evidence_type != "static_check":
            file_lines = changed_lines.get(file_path)
            context_line = bool(file_lines and line not in file_lines)
            # Finding 仍定位在当前修改文件，只是落在具体修改行附近。
            # 保留它并明确标记，交给报告使用者复核，避免静默丢失。
        else:
            context_line = False

        key = (file_path, line, str(finding["title"]).strip())
        if key in seen:
            continue
        seen.add(key)

        if line > 0:
            location = (file_path, line)
            if _is_duplicate_of_accepted(accepted_titles_at_location[location], finding["title"]):
                continue
            accepted_titles_at_location[location].append(finding["title"])

        accepted_finding = dict(finding)
        accepted_finding["file"] = file_path
        if context_line:
            accepted_finding["evidence_type"] = "reviewer_context"
        accepted.append(accepted_finding)

    return accepted
