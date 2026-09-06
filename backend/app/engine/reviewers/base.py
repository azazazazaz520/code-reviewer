"""Reviewer 基类。

Reviewer = System Prompt + Tool 列表 + LLM 调用 → Finding[]。
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable

from app.config import settings
from app.engine.tools.registry import (
    READ_FILE_MAX_LINES,
    TOOL_REGISTRY,
    ToolArgumentError,
    coerce_tool_arguments,
    get_tools_for_reviewer,
)
from app.engine.llm import get_llm, LLMProvider
from app.engine.context import REVIEW_DIFF_BATCH_CHARS
from app.engine.paths import PathSecurityError, relative_snapshot_path
from app.engine.tools.context import TaskToolCache, TaskToolContext, ToolCallBudget


class ReviewerOutputError(ValueError):
    """Reviewer 返回结果无法按约定解析时使用的可观察错误。"""


def _record_truncation(context: ReviewerContext, event: str) -> None:
    """记录唯一的输入截断事件，避免跨轮次重复累计。"""
    events = list(context.input_coverage.get("truncation_events", []))
    if event not in events:
        events.append(event)
    context.input_coverage["truncation_events"] = events
    context.input_coverage["truncated_inputs"] = len(events)


def _record_tool_error(
    context: ReviewerContext,
    tool_name: str,
    arguments: dict,
    result: object,
) -> None:
    """保存可去重的实际 Tool 执行错误。"""
    events = list(context.input_coverage.get("tool_error_events", []))
    event_key = json.dumps(
        {
            "tool": tool_name,
            "arguments": arguments,
            "result": str(result),
        },
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    if not any(item.get("key") == event_key for item in events):
        events.append(
            {
                "key": event_key,
                "tool": tool_name,
                "arguments": dict(arguments),
                "message": str(result),
            }
        )
    context.input_coverage["tool_error_events"] = events
    context.input_coverage["tool_errors"] = len(events)


def _record_model_decision_error(
    context: ReviewerContext,
    tool_name: str,
    arguments: dict,
    result: object,
) -> None:
    """记录模型参数决策事件，但不把它计入 Tool 故障。"""
    events = list(context.input_coverage.get("model_decision_events", []))
    event_key = json.dumps(
        {
            "tool": tool_name,
            "arguments": arguments,
            "result": str(result),
        },
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    if not any(item.get("key") == event_key for item in events):
        events.append(
            {
                "key": event_key,
                "tool": tool_name,
                "arguments": dict(arguments),
                "message": str(result),
            }
        )
    context.input_coverage["model_decision_events"] = events
    context.input_coverage["model_decision_errors"] = len(events)


def _is_model_decision_result(tool_name: str, result: object) -> bool:
    """识别 Tool 已正常执行、但拒绝了模型请求的结果。"""
    if tool_name != "ReadFile" or not isinstance(result, str):
        return False
    return any(
        marker in result
        for marker in (
            "invalid tool arguments",
            "invalid line range",
            "line range is outside file",
            "file context is not approved",
            "file not found:",
        )
    )


def _normalise_read_file_arguments(arguments: dict) -> dict:
    """兼容模型参数别名，并将超长读取请求收敛为单页读取。"""
    normalised = dict(arguments)
    if "max_line" in normalised:
        normalised.setdefault("max_lines", normalised["max_line"])
        normalised.pop("max_line", None)
    max_lines = normalised.get("max_lines")
    if isinstance(max_lines, int) and not isinstance(max_lines, bool):
        if max_lines > READ_FILE_MAX_LINES:
            normalised["max_lines"] = READ_FILE_MAX_LINES
    elif isinstance(max_lines, str) and re.fullmatch(r"[+]?\d+", max_lines.strip()):
        if int(max_lines) > READ_FILE_MAX_LINES:
            normalised["max_lines"] = READ_FILE_MAX_LINES
    return normalised


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
    tool_budget: ToolCallBudget | None = None
    input_coverage: dict = field(default_factory=dict)
    log_hook: Callable | None = None
    output_hook: Callable[[str, str], None] | None = None
    output_metadata_hook: Callable[[str, dict], None] | None = None
    cancel_check: Callable[[], bool] | None = None
    last_output_metadata: dict = field(default_factory=dict)


class BaseReviewer(ABC):
    """Reviewer 抽象基类。

    子类必须定义:
      - name: 审查器名称
      - system_prompt: 系统提示词
      - required_tools: 需要的 Tool 名称列表
    """

    name: str = "base"
    system_prompt: str = ""
    required_tools: list[str] = []

    def __init__(self):
        self._llm: LLMProvider | None = None

    @property
    def llm(self) -> LLMProvider:
        if self._llm is None:
            self._llm = get_llm()
        return self._llm

    def get_tool_schemas(self) -> list[dict]:
        """返回此 Reviewer 所需的 Tool Schema 列表（OpenAI function 格式）。"""
        schemas = []
        for name in self.required_tools:
            if name in TOOL_REGISTRY:
                s = TOOL_REGISTRY[name]["schema"]
                schemas.append({
                    "type": "function",
                    "function": {
                        "name": s["name"],
                        "description": s["description"],
                        "parameters": s["parameters"],
                    },
                })
        return schemas

    def _build_tool_handlers(self, context: ReviewerContext | None = None) -> dict[str, callable]:
        """构建 tool_name → handler 映射。"""
        handlers = {
            name: TOOL_REGISTRY[name]["handler"]
            for name in self.required_tools
            if name in TOOL_REGISTRY
        }
        if context and context.tool_context:
            from app.engine.tools.read_file import read_file_in_context

            def execute_tool(
                tool_name: str,
                arguments: dict,
                handler: Callable,
                *,
                model_decision_error: bool = False,
            ):
                context.input_coverage.setdefault("tool_errors", 0)
                context.input_coverage.setdefault("tool_error_events", [])
                context.input_coverage["tool_requests"] = (
                    context.input_coverage.get("tool_requests", 0) + 1
                )
                if context.tool_budget and not context.tool_budget.reserve():
                    result = f"Error: {tool_name} 调用预算已用尽"
                    context.input_coverage["tool_budget_exhausted"] = True
                    return result

                def load():
                    try:
                        return handler(**arguments)
                    except Exception as exc:
                        return f"Error: {type(exc).__name__}: {exc}"

                if context.tool_cache:
                    result, cache_hit = context.tool_cache.get_or_load(
                        context.revision or context.tool_context.revision,
                        tool_name,
                        arguments,
                        load,
                    )
                    context.input_coverage["tool_cache_hits"] = (
                        context.input_coverage.get("tool_cache_hits", 0) + int(cache_hit)
                    )
                    context.input_coverage["tool_cache_misses"] = (
                        context.input_coverage.get("tool_cache_misses", 0) + int(not cache_hit)
                    )
                else:
                    result = load()

                # 上下文收集阶段缓存的是带覆盖元数据的 FileReadPage；Reviewer
                # 对外只接受文本，命中共享缓存时必须沿用 ReadFile 的文本契约。
                if tool_name == "ReadFile":
                    from app.engine.tools.read_file import FileReadPage

                    if isinstance(result, FileReadPage):
                        result = result.render()
                if isinstance(result, str) and result.startswith("Error:"):
                    if model_decision_error or _is_model_decision_result(tool_name, result):
                        _record_model_decision_error(context, tool_name, arguments, result)
                    else:
                        _record_tool_error(context, tool_name, arguments, result)
                return result

            def scoped_read_file(**kwargs):
                kwargs = _normalise_read_file_arguments(kwargs)
                raw_file_path = kwargs.get("file_path")
                if raw_file_path is not None:
                    try:
                        kwargs["file_path"] = relative_snapshot_path(
                            context.tool_context.repo_root,
                            raw_file_path,
                        )
                    except PathSecurityError as exc:
                        kwargs["file_path"] = "<invalid-path>"
                        error_message = str(exc)
                        return execute_tool(
                            "ReadFile",
                            kwargs,
                            lambda **_kwargs: (
                                f"Error: invalid tool arguments: {error_message}"
                            ),
                            model_decision_error=True,
                        )
                try:
                    kwargs = coerce_tool_arguments("ReadFile", kwargs)
                except ToolArgumentError as exc:
                    error_message = str(exc)
                    return execute_tool(
                        "ReadFile",
                        kwargs,
                        lambda **_kwargs: f"Error: invalid tool arguments: {error_message}",
                        model_decision_error=True,
                    )
                return execute_tool(
                    "ReadFile",
                    kwargs,
                    lambda **arguments: read_file_in_context(
                        context.tool_context, **arguments
                    ),
                )

            handlers["ReadFile"] = scoped_read_file
            for name in self.required_tools:
                schema = TOOL_REGISTRY.get(name, {}).get("schema", {})
                properties = schema.get("parameters", {}).get("properties", {})
                handler = handlers.get(name)
                if name == "ReadFile" or not handler or "repo_root" not in properties:
                    continue

                def scoped_handler(_handler=handler, _tool_name=name, **kwargs):
                    # Reviewer 只能查询当前任务快照，不能用参数切换到源仓库或其他目录。
                    kwargs["repo_root"] = context.tool_context.repo_root
                    try:
                        kwargs = coerce_tool_arguments(_tool_name, kwargs)
                    except ToolArgumentError as exc:
                        error_message = str(exc)
                        return execute_tool(
                            _tool_name,
                            kwargs,
                            lambda **_kwargs: f"Error: invalid tool arguments: {error_message}",
                            model_decision_error=True,
                        )
                    return execute_tool(_tool_name, kwargs, _handler)

                handlers[name] = scoped_handler
        return handlers

    def _build_messages(self, context: ReviewerContext) -> list[dict]:
        """构建发送给 LLM 的消息列表。"""
        user_parts = []

        if context.diff and context.diff != "(no changes)":
            # 语义 ReviewUnit 已保证单元不超过该预算；这里不能再用旧的
            # 12K 兼容批次上限截掉完整 Hunk。
            diff_limit = max(REVIEW_DIFF_BATCH_CHARS, settings.review_unit_max_chars)
            diff = context.diff[:diff_limit]
            if len(context.diff) > diff_limit:
                diff += (
                    f"\n[输入截断：Diff 仅展示前 {diff_limit} 个字符，"
                    f"原始长度 {len(context.diff)}；请以快照 Tool 查询为准]"
                )
                _record_truncation(context, "diff:character_budget")
            user_parts.append(f"## 代码变更 (diff)\n```diff\n{diff}\n```")

        if context.changed_files:
            user_parts.append(
                "## 变更文件\n"
                + "\n".join(
                    f"- {self._display_path(context, file_path)}"
                    for file_path in context.changed_files
                )
            )

        if context.revision:
            user_parts.append(
                "## 审查快照\n"
                f"revision: {context.revision}"
            )

        if context.file_context:
            ctx_parts = []
            for fp, content in context.file_context.items():
                display_path = self._display_path(context, fp)
                file_limit = max(1, settings.review_context_max_chars)
                displayed = content[:file_limit]
                if len(content) > file_limit:
                    displayed += (
                        f"\n[输入截断：{display_path} 仅展示前 {file_limit} 个字符，"
                        f"原始长度 {len(content)}；请以快照 Tool 查询为准]"
                    )
                    _record_truncation(context, f"file:{display_path}:character_budget")
                ctx_parts.append(f"### {display_path}\n```\n{displayed}\n```")
            user_parts.append("## 文件内容\n" + "\n".join(ctx_parts))

        return [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": "\n\n".join(user_parts)},
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
        """调用 LLM 执行审查（含 Function Calling），返回 LLM 文本输出。"""
        messages = self._build_messages(context)
        tools = self.get_tool_schemas()
        handlers = self._build_tool_handlers(context)
        output_metadata: dict = {}

        def capture_metadata(metadata: dict) -> None:
            if isinstance(metadata, dict):
                output_metadata.update(metadata)

        if tools and handlers:
            output = self.llm.chat_with_tools(
                messages,
                tools,
                handlers,
                max_rounds=settings.max_tool_rounds,
                max_tool_calls=settings.max_tool_calls_per_unit,
                timeout_seconds=settings.reviewer_timeout_seconds,
                cancel_check=context.cancel_check,
                log_hook=context.log_hook,
                response_meta_hook=capture_metadata,
            )
        else:
            if context.cancel_check and context.cancel_check():
                from app.engine.execution import ReviewCancelled

                raise ReviewCancelled("审查任务已取消")
            result = self.llm.chat(
                messages,
                timeout_seconds=settings.reviewer_timeout_seconds,
            )
            output = result.get("content", "")
            if isinstance(result, dict):
                output_metadata.update(
                    {
                        key: result[key]
                        for key in ("finish_reason", "usage")
                        if result.get(key) is not None
                    }
                )

        if context.tool_budget:
            context.input_coverage["tool_calls"] = int(
                output_metadata.get("tool_calls", context.tool_budget.calls)
            )
            context.input_coverage["tool_rounds"] = int(
                output_metadata.get("tool_rounds", 0)
            )
            context.input_coverage["tool_budget_exhausted"] = bool(
                output_metadata.get("tool_budget_exhausted")
                or context.tool_budget.exhausted
            )
        context.last_output_metadata = output_metadata
        if context.output_hook:
            context.output_hook("primary", output if isinstance(output, str) else "")
        if context.output_metadata_hook:
            context.output_metadata_hook("primary", output_metadata)
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

    def _parse_findings_with_repair(
        self,
        llm_output: str,
        context: ReviewerContext,
    ) -> list[dict]:
        """解析 Finding；模型只破坏格式时，额外请求一次 JSON 修复。"""
        try:
            if context.last_output_metadata.get("finish_reason") == "length":
                raise ReviewerOutputError(
                    f"{self.name} output was truncated before complete Finding JSON"
                )
            return self._parse_findings(
                llm_output,
                fallback_file="",
                log_hook=context.log_hook,
            )
        except ReviewerOutputError as parse_error:
            if not isinstance(llm_output, str) or not llm_output.strip():
                raise

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
                    "只将用户提供的审查结果整理为合法 JSON 对象，根节点包含 findings 数组。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "将下面的审查结果转换为合法 JSON 对象。每个 Finding 保留原有的"
                        " severity、file、line、title、reason、suggestion、evidence、impact 字段。"
                        "只返回 {\"findings\":[...]}，不要 Markdown、解释文字或代码围栏。\n\n"
                        f"原始审查结果：\n{llm_output[:12000]}"
                    ),
                },
            ]
            try:
                if context.cancel_check and context.cancel_check():
                    from app.engine.execution import ReviewCancelled

                    raise ReviewCancelled("审查任务已取消")
                repaired = self.llm.chat(
                    repair_messages,
                    response_format={"type": "json_object"},
                    timeout_seconds=settings.reviewer_timeout_seconds,
                )
                repaired_output = repaired.get("content") if isinstance(repaired, dict) else ""
                if context.output_hook:
                    context.output_hook(
                        "format_repair",
                        repaired_output if isinstance(repaired_output, str) else "",
                    )
                if context.output_metadata_hook:
                    context.output_metadata_hook(
                        "format_repair",
                        {
                            key: repaired[key]
                            for key in ("finish_reason", "usage")
                            if isinstance(repaired, dict) and repaired.get(key) is not None
                        },
                    )
                repaired_findings = self._parse_findings(
                    repaired_output if isinstance(repaired_output, str) else "",
                    fallback_file="",
                    log_hook=context.log_hook,
                )
            except Exception as exc:
                from app.engine.execution import ReviewCancelled

                if isinstance(exc, ReviewCancelled):
                    raise
                raise parse_error

            if not repaired_findings:
                raise ReviewerOutputError(
                    f"{self.name} 输出格式修复后仍无法确认 Finding，已拒绝按 0 个问题处理"
                )
            return repaired_findings

    @abstractmethod
    def review(self, context: ReviewerContext) -> list[dict]:
        """执行审查，返回 Finding 列表。

        每个 Finding 格式:
          {"severity": "high", "file": "...", "line": 42,
           "title": "...", "reason": "...", "suggestion": "...",
           "evidence": "...", "impact": "behavior"}
        """
        ...
