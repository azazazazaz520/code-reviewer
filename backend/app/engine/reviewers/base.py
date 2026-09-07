"""Reviewer 基类。

Reviewer = System Prompt + 有界批次上下文 + LLM 调用 → Finding[]。
"""

from __future__ import annotations

import json
import hashlib
import re
from dataclasses import dataclass, field
from typing import Callable

from app.config import settings
from app.engine.tools.registry import READ_FILE_MAX_LINES
from app.engine.llm import (
    LLM_USAGE_METRIC_FIELDS,
    get_llm,
    LLMProvider,
)
from app.engine.paths import PathSecurityError, relative_snapshot_path
from app.engine.tools.context import TaskToolCache, TaskToolContext


COMMON_REVIEW_SYSTEM_PROMPT = """你负责对当前代码变更执行可验证的代码审查。

只基于当前请求中的 Diff、代码上下文和 Tool 结果判断问题；每个 Finding 都必须有明确证据、现实影响、变更范围内的定位和可执行建议。无法验证的外部事实不生成 Finding。
审查范围以“审查范围（严格）”和“当前审查单元”中的快照为准。代码上下文和 Tool 仅用于理解当前变更，不能把其他提交、未提交改动或未出现在当前 Diff 中的代码作为 Finding 依据。每条 Finding 必须定位到当前 Diff 的变更文件及其新增或修改行。

优先使用消息中已经提供的批次 Diff 和文件上下文。只有判断所需的关键行未提供时，才在 context_requests 中一次性声明需要读取的文件和行段。证据尚未取得时不要提前生成依赖该证据的 Finding；关联文件缺失不影响当前变更判断时直接完成审查。

最终只返回 JSON 对象，根节点必须包含 findings 和 context_requests 数组，例如 {"findings":[],"context_requests":[]}。每个 context_requests 元素包含 file、start_line、end_line 和 reason。没有达到证据门槛的问题才可以返回空 findings。不要输出 Markdown、解释文字或代码围栏。

输出必须保持精简并优先保证 JSON 完整：每个审查批次最多返回 5 条最重要的 Finding，按严重性和影响排序；同一问题只保留一条。title 不超过 80 个字符，reason 和 suggestion 各不超过 400 个字符，evidence 不超过 300 个字符。禁止复述完整 Diff、输出分析过程、重复同一结论或扩写背景；如果候选问题过多，只保留最重要的条目，不能为了容纳更多条目而省略 JSON 的闭合结构。"""


class ReviewerOutputError(ValueError):
    """Reviewer 返回结果无法按约定解析时使用的可观察错误。"""


def _record_truncation(
    context: ReviewerContext,
    event: str,
    *,
    critical: bool = True,
) -> None:
    """记录输入边界事件，并区分关键截断与关联上下文收敛。"""
    field = "truncation_events" if critical else "context_limit_events"
    events = list(context.input_coverage.get(field, []))
    if event not in events:
        events.append(event)
    context.input_coverage[field] = events
    if critical:
        context.input_coverage["truncated_inputs"] = len(events)
        context.input_coverage["critical_truncated_inputs"] = len(events)
    else:
        context.input_coverage["context_limited_inputs"] = len(events)


def _record_llm_usage(
    context: ReviewerContext,
    usage: object,
    stage: str | None = None,
    metadata: dict | None = None,
) -> None:
    """按实际 Provider 响应累计模型 token 与 Prompt Cache 指标。"""
    if not isinstance(usage, dict):
        return

    coverage = context.input_coverage
    request_index = coverage.get("provider_requests", 0) + 1
    coverage["provider_requests"] = request_index
    group_usage = context.llm_usage_state
    group_request_index = group_usage.get("provider_requests", 0) + 1
    group_usage["provider_requests"] = group_request_index
    event = {
        "task_id": context.task_id or None,
        "reviewer": context.reviewer_name or None,
        "unit_id": coverage.get("unit_id") or None,
        "stage": stage or "unknown",
        "model": (metadata or {}).get("model"),
        "base_url": (metadata or {}).get("base_url"),
        "max_tokens": (metadata or {}).get("max_tokens"),
        "thinking": (metadata or {}).get("thinking"),
        "provider_request_index": group_request_index,
        "first_provider_request": group_request_index == 1,
        "stable_prefix_hash": coverage.get("stable_prefix_hash"),
        "dynamic_suffix_hash": coverage.get("dynamic_suffix_hash"),
        "stable_prefix_chars": coverage.get("stable_prefix_chars", 0),
        "dynamic_suffix_chars": coverage.get("dynamic_suffix_chars", 0),
        "cache_session_reused": bool(coverage.get("cache_session_reused")),
        "session_scope": coverage.get("session_scope", "review_unit"),
        "session_rebuilt": bool(coverage.get("session_rebuilt")),
        "session_history_messages": coverage.get("session_history_messages", 0),
    }
    for response_key, metric_key in LLM_USAGE_METRIC_FIELDS.items():
        value = usage.get(response_key)
        if isinstance(value, int) and not isinstance(value, bool):
            coverage[metric_key] = coverage.get(metric_key, 0) + value
            event[response_key] = value
    coverage.setdefault("llm_usage_events", []).append(event)
    if context.log_hook:
        context.log_hook(
            step="run_reviews",
            level="info",
            message=(
                "LLM Prompt Cache："
                f"task={event['task_id'] or '-'} "
                f"reviewer={event['reviewer'] or '-'} "
                f"unit={event['unit_id'] or '-'} "
                f"stage={event['stage']} "
                f"model={event['model'] or '-'} "
                f"first={event['first_provider_request']} "
                f"prompt_tokens={event.get('prompt_tokens', 0)} "
                f"hit={event.get('prompt_cache_hit_tokens', 0)} "
                f"miss={event.get('prompt_cache_miss_tokens', 0)} "
                f"stable_prefix_chars={event['stable_prefix_chars']} "
                f"dynamic_suffix_chars={event['dynamic_suffix_chars']} "
                f"stable_prefix_hash={event['stable_prefix_hash'] or '-'} "
                f"dynamic_suffix_hash={event['dynamic_suffix_hash'] or '-'}"
            ),
        )


@dataclass
class ReviewerContext:
    """传入 Reviewer 的审查上下文。"""
    diff: str = ""
    changed_files: list[str] = field(default_factory=list)
    file_context: dict[str, str] = field(default_factory=dict)  # file_path → content
    repo_root: str = ""
    revision: str = ""
    tool_context: TaskToolContext | None = None
    tool_cache: TaskToolCache | None = None
    input_coverage: dict = field(default_factory=dict)
    log_hook: Callable | None = None
    output_hook: Callable[[str, str], None] | None = None
    output_metadata_hook: Callable[[str, dict], None] | None = None
    cancel_check: Callable[[], bool] | None = None
    last_output_metadata: dict = field(default_factory=dict)
    task_changed_files: list[str] = field(default_factory=list)
    shared_file_context: dict[str, str] = field(default_factory=dict)
    task_id: str = ""
    reviewer_name: str = ""
    review_scope: dict = field(default_factory=dict)
    llm_usage_state: dict = field(default_factory=dict)
    supplemental_context: str = ""
    # 保留字段以兼容旧调用方；审查流程不会读取或写入跨 ReviewUnit 历史。
    llm_history: list[dict] | None = None


class BaseReviewer:
    """Reviewer 抽象基类。

    子类必须定义审查器名称和系统提示词。
    """

    name: str = "base"
    system_prompt: str = ""

    def __init__(self):
        self._llm: LLMProvider | None = None

    @property
    def llm(self) -> LLMProvider:
        if self._llm is None:
            self._llm = get_llm()
        return self._llm

    def _build_messages(self, context: ReviewerContext) -> list[dict]:
        """构建发送给 LLM 的消息列表。"""
        stable_parts = [
            "## 审查任务\n"
            "prompt_schema: review-cache-v1"
        ]

        task_changed_files = context.task_changed_files or context.changed_files
        if context.revision:
            stable_parts.append(
                "## 审查快照\n"
                f"revision: {context.revision}"
            )

        scope = context.review_scope if isinstance(context.review_scope, dict) else {}
        scope_lines = [
            "## 审查范围（严格）",
            str(scope.get("target") or "当前审查快照中的变更"),
        ]
        if scope.get("base_revision"):
            scope_lines.append(f"base_revision: {scope['base_revision']}")
        if scope.get("revision") or context.revision:
            scope_lines.append(f"revision: {scope.get('revision') or context.revision}")
        scope_lines.append(
            "仅审查上述快照的当前 Diff；上下文和 Tool 只用于理解，Finding 必须落在当前 Diff 的变更文件与新增/修改行。"
        )
        stable_parts.append("\n".join(scope_lines))

        if task_changed_files:
            displayed_task_files = sorted(
                {
                    self._display_path(context, file_path)
                    for file_path in task_changed_files
                }
            )
            stable_parts.append(
                "## 变更文件清单\n"
                + "\n".join(
                    f"- {file_path}" for file_path in displayed_task_files
                )
            )

        if context.tool_context:
            related_refs = sorted(
                (
                    ref for ref in context.tool_context.approved_context_refs
                    if ref.source != "changed_file"
                ),
                key=lambda ref: (ref.file_path, ref.start_line, ref.end_line),
            )
            if related_refs:
                stable_parts.append(
                    "## 可申请的关联上下文\n"
                    + "\n".join(
                        f"- {self._display_path(context, ref.file_path)}:"
                        f"{ref.start_line}-{ref.end_line}"
                        for ref in related_refs
                    )
                )

        if context.shared_file_context:
            shared_parts = []
            for fp in sorted(context.shared_file_context):
                display_path = self._display_path(context, fp)
                shared_parts.append(
                    f"### {display_path}\n```\n"
                    f"{context.shared_file_context[fp]}\n```"
                )
            stable_parts.append(
                "## 稳定文件上下文\n" + "\n".join(shared_parts)
            )

        dynamic_parts = []

        if context.changed_files:
            dynamic_parts.append(
                "## 当前审查单元\n"
                + "\n".join(
                    f"- {self._display_path(context, file_path)}"
                    for file_path in context.changed_files
                )
            )

        if context.diff and context.diff != "(no changes)":
            # 批次构造保证完整 Hunk 不跨批次拆分；超大 Hunk 也必须完整发送。
            diff = context.diff
            dynamic_parts.append(f"## 代码变更 (diff)\n```diff\n{diff}\n```")

        if context.file_context:
            ctx_parts = []
            shared_paths = {
                self._display_path(context, file_path)
                for file_path in context.shared_file_context
            }
            primary_paths = {
                self._display_path(context, path)
                for path in context.changed_files
            }
            inline_limit = max(0, settings.review_context_max_chars)
            inline_chars = 0
            ordered_file_paths = sorted(
                context.file_context,
                key=lambda path: (
                    self._display_path(context, path) not in primary_paths,
                    self._display_path(context, path),
                ),
            )
            for fp in ordered_file_paths:
                # 稳定包中的主文件可能只是前缀片段，当前 Hunk 的窄窗口仍需
                # 放入动态后缀，避免模型只看到文件开头而遗漏变更位置。
                if (
                    self._display_path(context, fp) in shared_paths
                    and self._display_path(context, fp) not in primary_paths
                ):
                    continue
                content = context.file_context[fp]
                display_path = self._display_path(context, fp)
                if inline_limit <= inline_chars:
                    _record_truncation(
                        context,
                        f"file:{display_path}:inline_context_budget",
                        critical=False,
                    )
                    continue
                file_limit = inline_limit - inline_chars
                displayed = content[:file_limit]
                if len(content) > file_limit:
                    displayed += (
                        f"\n[动态上下文收敛：{display_path} 仅展示前 {file_limit} 个字符，"
                        f"原始长度 {len(content)}；请以快照 Tool 查询为准]"
                    )
                    _record_truncation(
                        context,
                        f"file:{display_path}:character_budget",
                        critical=False,
                    )
                ctx_parts.append(f"### {display_path}\n```\n{displayed}\n```")
                inline_chars += len(displayed)
            if ctx_parts:
                dynamic_parts.append("## 当前文件上下文\n" + "\n".join(ctx_parts))

        if context.supplemental_context:
            dynamic_parts.append(
                "## 补充上下文\n"
                + context.supplemental_context
                + "\n\n补充上下文仅用于理解当前 Diff。现在必须完成审查，"
                "context_requests 必须返回空数组。"
            )

        system_content = f"{COMMON_REVIEW_SYSTEM_PROMPT}\n\n{self.system_prompt}"
        stable_content = "\n\n".join(stable_parts)
        dynamic_content = "\n\n".join(dynamic_parts)
        context.input_coverage.update(
            {
                # 每个 ReviewUnit 都从相同稳定前缀重新创建本地 Session；
                # DeepSeek 服务端仍可根据该前缀命中 KV Cache。
                "cache_session_reused": False,
                "session_scope": "review_batch",
                "session_rebuilt": True,
                "session_rebuilds": 1,
                "session_history_messages": 0,
                "stable_prefix_hash": hashlib.sha256(
                    json.dumps(
                        [
                            {"role": "system", "content": system_content},
                            {"role": "user", "content": stable_content},
                        ],
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ).encode("utf-8")
                ).hexdigest()[:16],
                "dynamic_suffix_hash": hashlib.sha256(
                    dynamic_content.encode("utf-8")
                ).hexdigest()[:16],
                "stable_prefix_chars": len(system_content) + len(stable_content),
                "dynamic_suffix_chars": len(dynamic_content),
            }
        )
        user_content = "\n\n".join(
            part for part in (stable_content, dynamic_content) if part
        )

        return [
            {
                "role": "system",
                "content": system_content,
            },
            {"role": "user", "content": user_content},
        ]

    @staticmethod
    def _display_path(context: ReviewerContext, file_path: str) -> str:
        """将模型可见的路径统一为快照根目录内的相对路径。"""
        snapshot_root = (
            context.tool_context.repo_root
            if context.tool_context
            else context.repo_root
        )
        if snapshot_root:
            try:
                return relative_snapshot_path(
                    snapshot_root,
                    file_path,
                )
            except PathSecurityError:
                return "<invalid-path>"
        return str(file_path).replace("\\", "/")

    def _call_llm(self, context: ReviewerContext) -> str:
        """执行一次结构化审查请求，不开放自由 Tool 循环。"""
        messages = self._build_messages(context)
        output_metadata: dict = {}

        def capture_metadata(metadata: dict) -> None:
            if isinstance(metadata, dict):
                output_metadata.update(metadata)
                _record_llm_usage(
                    context,
                    metadata.get("usage"),
                    metadata.get("stage"),
                    metadata,
                )

        if context.cancel_check and context.cancel_check():
            from app.engine.execution import ReviewCancelled

            raise ReviewCancelled("审查任务已取消")
        stage = "supplement" if context.supplemental_context else "review"
        max_tokens = (
            settings.llm_supplement_max_tokens
            if context.supplemental_context
            else settings.llm_review_max_tokens
        )
        # DeepSeek V4 默认启用思考模式，推理 Token 会与 JSON 输出共同消耗
        # max_tokens；结构化审查需要将预算留给可解析的 Finding JSON。
        thinking = "disabled"
        result = self.llm.chat(
            messages,
            response_format={"type": "json_object"},
            timeout_seconds=settings.reviewer_timeout_seconds,
            max_tokens=max_tokens,
            thinking=thinking,
        )
        if isinstance(result, dict):
            output = result.get("content", "")
            metadata = {
                "stage": stage,
                "model": getattr(self.llm, "model", None),
                "base_url": getattr(self.llm, "base_url", None),
                "max_tokens": max_tokens,
                "thinking": thinking,
            }
            metadata.update(
                {
                    key: result[key]
                    for key in ("finish_reason", "usage")
                    if result.get(key) is not None
                }
            )
            capture_metadata(metadata)
        else:
            output = ""

        context.last_output_metadata = output_metadata
        if context.output_hook:
            context.output_hook(stage, output if isinstance(output, str) else "")
        if context.output_metadata_hook:
            context.output_metadata_hook(stage, output_metadata)
        return output if isinstance(output, str) else ""

    def _parse_findings(
        self,
        llm_output: str,
        fallback_file: str = "",
        log_hook: Callable | None = None,
    ) -> list[dict]:
        """从 LLM 输出中解析 Finding 列表。

        期望 LLM 返回 JSON 数组，容错处理非 JSON 输出。
        """
        text = (llm_output or "").strip()
        if not text:
            raise ReviewerOutputError(f"{self.name} 输出为空，无法解析为 Finding JSON")

        def normalise(findings: list) -> list[dict]:
            normalised = []
            for finding in findings:
                if not isinstance(finding, dict):
                    continue
                item = dict(finding)
                if isinstance(item.get("severity"), str):
                    item["severity"] = item["severity"].strip().lower()
                if isinstance(item.get("line"), str):
                    line = item["line"].strip()
                    if re.fullmatch(r"-?\d+", line):
                        item["line"] = int(line)
                item["evidence_type"] = item.get("evidence_type", "reviewer")
                normalised.append(item)
            return normalised

        def parse_candidate(candidate: str) -> list[dict] | None:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                if "findings" not in parsed:
                    return None
                parsed = parsed["findings"]
            if isinstance(parsed, list):
                if not all(isinstance(finding, dict) for finding in parsed):
                    return None
                return normalise(parsed)
            return None

        candidates = [
            match.group(1)
            for match in re.finditer(r"```(?:json)?\s*(.*?)```", text, re.IGNORECASE | re.DOTALL)
        ]
        candidates.append(text)

        decoder = json.JSONDecoder()
        for candidate in candidates:
            try:
                findings = parse_candidate(candidate.strip())
                if findings is not None:
                    return findings
            except json.JSONDecodeError:
                pass

            # 兼容模型在 JSON 前后附带说明文字的情况。
            for marker in ("[", "{"):
                start = candidate.find(marker)
                while start != -1:
                    try:
                        parsed, _ = decoder.raw_decode(candidate[start:])
                        findings_wrapper = False
                        if isinstance(parsed, dict) and "findings" in parsed:
                            parsed = parsed["findings"]
                            findings_wrapper = True
                        if isinstance(parsed, list):
                            if not findings_wrapper and not parsed:
                                start = candidate.find(marker, start + 1)
                                continue
                            if not all(isinstance(finding, dict) for finding in parsed):
                                start = candidate.find(marker, start + 1)
                                continue
                            return normalise(parsed)
                    except json.JSONDecodeError:
                        pass
                    start = candidate.find(marker, start + 1)

        raise ReviewerOutputError(
            f"{self.name} 输出无法解析为 Finding JSON（响应长度={len(text)}）"
        )

    @staticmethod
    def _decode_review_output(llm_output: str) -> object:
        """从纯 JSON 或代码围栏中提取一次审查响应。"""
        text = (llm_output or "").strip()
        if not text:
            raise ReviewerOutputError("Reviewer 输出为空")
        candidates = [
            match.group(1).strip()
            for match in re.finditer(
                r"```(?:json)?\s*(.*?)```",
                text,
                re.IGNORECASE | re.DOTALL,
            )
        ]
        candidates.append(text)
        decoder = json.JSONDecoder()
        for candidate in candidates:
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass
            for marker in ("{", "["):
                start = candidate.find(marker)
                while start != -1:
                    try:
                        value, _ = decoder.raw_decode(candidate[start:])
                        return value
                    except json.JSONDecodeError:
                        start = candidate.find(marker, start + 1)
        raise ReviewerOutputError(
            f"Reviewer 输出无法解析为 JSON（响应长度={len(text)}）"
        )

    def _parse_review_payload(self, llm_output: str) -> tuple[list[dict], list[dict]]:
        """解析 Findings 和一次性上下文请求。"""
        parsed = self._decode_review_output(llm_output)
        if isinstance(parsed, list):
            findings_raw = parsed
            requests_raw = []
        elif isinstance(parsed, dict) and isinstance(parsed.get("findings"), list):
            findings_raw = parsed["findings"]
            requests_raw = parsed.get("context_requests", [])
        else:
            raise ReviewerOutputError(
                f"{self.name} 输出缺少 findings 数组"
            )
        if not isinstance(requests_raw, list):
            raise ReviewerOutputError(
                f"{self.name} 输出的 context_requests 不是数组"
            )

        findings = self._parse_findings(
            json.dumps({"findings": findings_raw}, ensure_ascii=False)
        )
        requests: list[dict] = []
        for request in requests_raw:
            if not isinstance(request, dict):
                raise ReviewerOutputError(
                    f"{self.name} 输出包含无效 context_requests 元素"
                )
            file_path = request.get("file") or request.get("file_path")
            start_line = request.get("start_line", 1)
            end_line = request.get("end_line", start_line)
            if isinstance(start_line, str) and start_line.strip().isdigit():
                start_line = int(start_line.strip())
            if isinstance(end_line, str) and end_line.strip().isdigit():
                end_line = int(end_line.strip())
            if (
                not isinstance(file_path, str)
                or not file_path.strip()
                or isinstance(start_line, bool)
                or isinstance(end_line, bool)
                or not isinstance(start_line, int)
                or not isinstance(end_line, int)
                or start_line < 1
                or end_line < start_line
            ):
                raise ReviewerOutputError(
                    f"{self.name} 输出包含无效上下文行段"
                )
            requests.append({
                "file": file_path.strip(),
                "start_line": start_line,
                "end_line": end_line,
                "reason": str(request.get("reason") or "需要补充判断证据"),
            })
        return findings, requests

    @staticmethod
    def _merge_context_requests(context: ReviewerContext, requests: list[dict]) -> list[dict]:
        """规范化并合并同一文件中相邻或重叠的行段。"""
        grouped: dict[str, list[tuple[int, int, str]]] = {}
        for request in requests:
            try:
                file_path = relative_snapshot_path(
                    context.tool_context.repo_root if context.tool_context else context.repo_root,
                    request["file"],
                )
            except PathSecurityError:
                file_path = "<invalid-path>"
            grouped.setdefault(file_path, []).append((
                request["start_line"],
                request["end_line"],
                request["reason"],
            ))

        merged: list[dict] = []
        for file_path in sorted(grouped):
            for start_line, end_line, reason in sorted(grouped[file_path]):
                if (
                    merged
                    and merged[-1]["file"] == file_path
                    and start_line <= merged[-1]["end_line"] + 1
                ):
                    merged[-1]["end_line"] = max(merged[-1]["end_line"], end_line)
                    continue
                merged.append({
                    "file": file_path,
                    "start_line": start_line,
                    "end_line": end_line,
                    "reason": reason,
                })
        return merged

    def _read_requested_context(
        self,
        context: ReviewerContext,
        requests: list[dict],
    ) -> str:
        """批量执行一次上下文补充，并将失败保留为可观察诊断。"""
        from app.engine.tools.read_file import FileReadPage, read_file_page_in_context

        context.input_coverage["context_requests"] = len(requests)
        failures = list(context.input_coverage.get("context_request_failure_events", []))
        if not context.tool_context:
            failures.append({
                "file": "",
                "start_line": 0,
                "end_line": 0,
                "message": "审查快照没有可用的上下文读取范围",
            })
            context.input_coverage["context_request_failure_events"] = failures
            context.input_coverage["context_request_failures"] = len(failures)
            return ""

        merged = self._merge_context_requests(context, requests)
        limit = max(1, settings.supplement_context_max_chars)
        rendered_parts: list[str] = []
        used_chars = 0
        reads = 0
        cache_hits = 0

        def record_failure(request: dict, message: str) -> None:
            event = {
                "file": request["file"],
                "start_line": request["start_line"],
                "end_line": request["end_line"],
                "message": message,
            }
            if event not in failures:
                failures.append(event)

        for request in merged:
            start_line = request["start_line"]
            while start_line <= request["end_line"]:
                max_lines = min(
                    READ_FILE_MAX_LINES,
                    request["end_line"] - start_line + 1,
                )
                arguments = {
                    "file_path": request["file"],
                    "start_line": start_line,
                    "max_lines": max_lines,
                }

                def load() -> FileReadPage:
                    return read_file_page_in_context(
                        context.tool_context,
                        **arguments,
                    )

                if context.tool_cache:
                    page, cache_hit = context.tool_cache.get_or_load(
                        context.revision or context.tool_context.revision,
                        "ReadFile",
                        arguments,
                        load,
                    )
                    cache_hits += int(cache_hit)
                else:
                    page = load()
                reads += 1
                if not isinstance(page, FileReadPage):
                    record_failure(request, "上下文读取返回了无效结果")
                    break
                if page.error:
                    record_failure(request, page.error)
                    break

                part = (
                    f"### {page.file_path} lines {page.start_line}-{page.end_line}\n"
                    f"```\n{page.content}\n```"
                )
                remaining = limit - used_chars
                if remaining <= 0 or len(part) > remaining:
                    record_failure(request, "补充上下文达到字符预算")
                    if remaining > 0:
                        rendered_parts.append(part[:remaining])
                        used_chars += remaining
                    start_line = request["end_line"] + 1
                    break
                rendered_parts.append(part)
                used_chars += len(part)
                if page.complete or page.end_line >= request["end_line"]:
                    break
                start_line = page.end_line + 1

        context.input_coverage["context_reads"] = reads
        context.input_coverage["context_cache_hits"] = cache_hits
        context.input_coverage["context_request_failure_events"] = failures
        context.input_coverage["context_request_failures"] = len(failures)
        return "\n\n".join(rendered_parts)

    def _repair_review_output(
        self,
        llm_output: str,
        context: ReviewerContext,
    ) -> str:
        """只修复已有审查输出的 JSON 结构，不重新分析代码。"""
        if not isinstance(llm_output, str) or not llm_output.strip():
            raise ReviewerOutputError(f"{self.name} 输出为空，无法执行 JSON 修复")
        if context.log_hook:
            context.log_hook(
                step="run_reviews",
                level="info",
                message=f"{self.name} 输出格式异常，正在请求 JSON 修复...",
            )
        repair_messages = [
            {
                "role": "system",
                "content": (
                    "你是审查结果 JSON 格式修复器。不要重新分析代码，也不要添加新的审查结论。"
                    "只整理为合法 JSON 对象，根节点包含 findings 和 context_requests 数组。"
                    "只保留原始输出中已经完整的 Finding；丢弃截断的最后一条。"
                ),
            },
            {
                "role": "user",
                "content": (
                    "修复下面的审查结果。保留已有 Finding 和上下文请求字段；"
                    "只返回 {\"findings\":[...],\"context_requests\":[...]}，"
                    "最多保留 5 条 Finding；不要复述、扩写或补充原始结果中不存在的内容；"
                    "若字段过长，只截取原始文本的前部以满足 title 80、reason/suggestion 400、evidence 300 字符限制；"
                    "不要输出 Markdown、解释文字或代码围栏。\n\n"
                    f"原始审查结果：\n{llm_output}"
                ),
            },
        ]
        if context.cancel_check and context.cancel_check():
            from app.engine.execution import ReviewCancelled

            raise ReviewCancelled("审查任务已取消")
        repaired = self.llm.chat(
            repair_messages,
            response_format={"type": "json_object"},
            timeout_seconds=settings.reviewer_timeout_seconds,
            max_tokens=settings.llm_json_repair_max_tokens,
            thinking="disabled",
        )
        metadata = {
            "stage": "format_repair",
            "model": getattr(self.llm, "model", None),
            "base_url": getattr(self.llm, "base_url", None),
            "max_tokens": settings.llm_json_repair_max_tokens,
            "thinking": "disabled",
        }
        if isinstance(repaired, dict):
            metadata.update({
                key: repaired[key]
                for key in ("finish_reason", "usage")
                if repaired.get(key) is not None
            })
            _record_llm_usage(
                context,
                repaired.get("usage"),
                "format_repair",
                metadata,
            )
        repaired_output = repaired.get("content") if isinstance(repaired, dict) else ""
        if context.output_hook:
            context.output_hook(
                "format_repair",
                repaired_output if isinstance(repaired_output, str) else "",
            )
        if context.output_metadata_hook:
            context.output_metadata_hook("format_repair", metadata)
        return repaired_output if isinstance(repaired_output, str) else ""

    def _parse_review_payload_with_repair(
        self,
        llm_output: str,
        context: ReviewerContext,
    ) -> tuple[list[dict], list[dict]]:
        """解析审查响应；格式损坏时最多执行一次 JSON 修复。"""
        try:
            # Provider 的 length 只表示达到生成上限，不能单独证明 JSON 不完整。
            # 先解析实际 content；只有解析失败时才进入一次性修复，避免完整结果被
            # 误判为截断并额外消耗一个模型请求。
            parsed = self._parse_review_payload(llm_output)
            if (
                context.last_output_metadata.get("finish_reason") == "length"
                and context.output_metadata_hook
            ):
                # 只有 JSON 已经通过解析，才撤销调用边界上的暂定截断标记。
                context.output_metadata_hook(
                    context.last_output_metadata.get("stage", "review"),
                    {"truncated": False},
                )
            return parsed
        except ReviewerOutputError as parse_error:
            if context.last_output_metadata.get("finish_reason") == "length":
                parse_error = ReviewerOutputError(
                    f"{self.name} output was truncated before complete review JSON"
                )
            try:
                repaired_output = self._repair_review_output(llm_output, context)
                findings, requests = self._parse_review_payload(repaired_output)
            except Exception as exc:
                from app.engine.execution import ReviewCancelled

                if isinstance(exc, ReviewCancelled):
                    raise
                context.input_coverage["output_repair_failures"] = (
                    context.input_coverage.get("output_repair_failures", 0) + 1
                )
                raise parse_error
            if not findings and not requests:
                context.input_coverage["output_repair_failures"] = (
                    context.input_coverage.get("output_repair_failures", 0) + 1
                )
                raise ReviewerOutputError(
                    f"{parse_error}；一次性 JSON 修复后仍无法确认审查结论，"
                    "已拒绝按 0 个问题处理"
                )
            return findings, requests

    def _parse_findings_with_repair(
        self,
        llm_output: str,
        context: ReviewerContext,
    ) -> list[dict]:
        """兼容旧调用方，只返回修复后的 Finding 列表。"""
        findings, _ = self._parse_review_payload_with_repair(llm_output, context)
        return findings

    def review(self, context: ReviewerContext) -> list[dict]:
        """执行一次批次审查，并在模型明确请求时补充一次上下文。"""
        llm_output = self._call_llm(context)
        findings, requests = self._parse_review_payload_with_repair(
            llm_output,
            context,
        )
        if not requests:
            return findings

        supplemental_context = self._read_requested_context(context, requests)
        if not supplemental_context:
            raise ReviewerOutputError(
                f"{self.name} 请求的必要上下文无法读取"
            )

        context.supplemental_context = supplemental_context
        final_output = self._call_llm(context)
        final_findings, further_requests = self._parse_review_payload_with_repair(
            final_output,
            context,
        )
        if further_requests:
            context.input_coverage["context_request_failures"] = (
                context.input_coverage.get("context_request_failures", 0)
                + len(further_requests)
            )
            context.input_coverage.setdefault(
                "context_request_failure_events",
                [],
            ).append({
                "file": "",
                "start_line": 0,
                "end_line": 0,
                "message": "补充审查仍然请求新的上下文",
            })
            raise ReviewerOutputError(
                f"{self.name} 补充审查仍然请求新的上下文"
            )
        return final_findings
