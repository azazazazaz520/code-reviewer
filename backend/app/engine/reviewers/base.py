"""Reviewer 基类。

Reviewer = System Prompt + Tool 列表 + LLM 调用 → Finding[]。
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable

from app.engine.tools.registry import TOOL_REGISTRY, get_tools_for_reviewer
from app.engine.llm import get_llm, LLMProvider


class ReviewerOutputError(ValueError):
    """Reviewer 返回结果无法按约定解析时使用的可观察错误。"""


@dataclass
class ReviewerContext:
    """传入 Reviewer 的审查上下文。"""
    diff: str = ""
    changed_files: list[str] = field(default_factory=list)
    file_context: dict[str, str] = field(default_factory=dict)  # file_path → content
    repo_root: str = ""
    revision: str = ""
    log_hook: Callable | None = None
    output_hook: Callable[[str, str], None] | None = None
    output_metadata_hook: Callable[[str, dict], None] | None = None
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

    def _build_tool_handlers(self) -> dict[str, callable]:
        """构建 tool_name → handler 映射。"""
        return {
            name: TOOL_REGISTRY[name]["handler"]
            for name in self.required_tools
            if name in TOOL_REGISTRY
        }

    def _build_messages(self, context: ReviewerContext) -> list[dict]:
        """构建发送给 LLM 的消息列表。"""
        user_parts = []

        if context.diff and context.diff != "(no changes)":
            user_parts.append(f"## 代码变更 (diff)\n```diff\n{context.diff[:4000]}\n```")

        if context.changed_files:
            user_parts.append(f"## 变更文件\n" + "\n".join(f"- {f}" for f in context.changed_files))

        if context.repo_root:
            user_parts.append(
                f"## 审查快照\n根目录: {context.repo_root}\n"
                f"revision: {context.revision or '(unknown)'}"
            )

        if context.file_context:
            ctx_parts = []
            for fp, content in context.file_context.items():
                ctx_parts.append(f"### {fp}\n```\n{content[:2000]}\n```")
            user_parts.append("## 文件内容\n" + "\n".join(ctx_parts))

        return [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": "\n\n".join(user_parts)},
        ]

    def _call_llm(self, context: ReviewerContext) -> str:
        """调用 LLM 执行审查（含 Function Calling），返回 LLM 文本输出。"""
        messages = self._build_messages(context)
        tools = self.get_tool_schemas()
        handlers = self._build_tool_handlers()
        output_metadata: dict = {}

        def capture_metadata(metadata: dict) -> None:
            if isinstance(metadata, dict):
                output_metadata.update(metadata)

        if tools and handlers:
            output = self.llm.chat_with_tools(
                messages,
                tools,
                handlers,
                log_hook=context.log_hook,
                response_meta_hook=capture_metadata,
            )
        else:
            result = self.llm.chat(messages)
            output = result.get("content", "")
            if isinstance(result, dict):
                output_metadata.update(
                    {
                        key: result[key]
                        for key in ("finish_reason", "usage")
                        if result.get(key) is not None
                    }
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
                        " severity、file、line、title、reason、suggestion 字段。"
                        "只返回 {\"findings\":[...]}，不要 Markdown、解释文字或代码围栏。\n\n"
                        f"原始审查结果：\n{llm_output[:12000]}"
                    ),
                },
            ]
            try:
                repaired = self.llm.chat(
                    repair_messages,
                    response_format={"type": "json_object"},
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
            except Exception:
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
           "title": "...", "reason": "...", "suggestion": "..."}
        """
        ...
