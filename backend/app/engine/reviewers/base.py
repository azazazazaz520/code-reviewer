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

        if tools and handlers:
            return self.llm.chat_with_tools(
                messages, tools, handlers, log_hook=context.log_hook
            )
        else:
            result = self.llm.chat(messages)
            return result.get("content", "")

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

        def normalise(findings: list) -> list[dict]:
            return [
                {**finding, "evidence_type": finding.get("evidence_type", "reviewer")}
                for finding in findings
                if isinstance(finding, dict)
            ]

        def parse_candidate(candidate: str) -> list[dict] | None:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                if "findings" not in parsed:
                    return None
                parsed = parsed["findings"]
            if isinstance(parsed, list):
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
                        if isinstance(parsed, dict) and "findings" in parsed:
                            parsed = parsed["findings"]
                        if isinstance(parsed, list):
                            return normalise(parsed)
                    except json.JSONDecodeError:
                        pass
                    start = candidate.find(marker, start + 1)

        raise ReviewerOutputError(f"{self.name} 输出无法解析为 Finding JSON")

    @abstractmethod
    def review(self, context: ReviewerContext) -> list[dict]:
        """执行审查，返回 Finding 列表。

        每个 Finding 格式:
          {"severity": "high", "file": "...", "line": 42,
           "title": "...", "reason": "...", "suggestion": "..."}
        """
        ...
