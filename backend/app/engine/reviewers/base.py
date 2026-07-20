"""Reviewer 基类。

Reviewer = System Prompt + Tool 列表 + LLM 调用 → Finding[]。
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from app.engine.tools.registry import TOOL_REGISTRY, get_tools_for_reviewer
from app.engine.llm import get_llm, LLMProvider


@dataclass
class ReviewerContext:
    """传入 Reviewer 的审查上下文。"""
    diff: str = ""
    changed_files: list[str] = field(default_factory=list)
    file_context: dict[str, str] = field(default_factory=dict)  # file_path → content


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
            return self.llm.chat_with_tools(messages, tools, handlers)
        else:
            result = self.llm.chat(messages)
            return result.get("content", "")

    def _parse_findings(self, llm_output: str, fallback_file: str = "") -> list[dict]:
        """从 LLM 输出中解析 Finding 列表。

        期望 LLM 返回 JSON 数组，容错处理非 JSON 输出。
        """
        text = llm_output.strip()

        # 策略 1: ```json ... ``` 代码块
        try:
            if "```json" in text:
                block = text.split("```json")[1].split("```")[0]
                findings = json.loads(block)
                if isinstance(findings, dict):
                    findings = findings.get("findings", [])
                if isinstance(findings, list):
                    return findings
        except (json.JSONDecodeError, IndexError):
            pass

        # 策略 2: ``` ... ``` 代码块
        try:
            if "```" in text:
                block = text.split("```")[1].split("```")[0]
                findings = json.loads(block)
                if isinstance(findings, dict):
                    findings = findings.get("findings", [])
                if isinstance(findings, list):
                    return findings
        except (json.JSONDecodeError, IndexError):
            pass

        # 策略 3: 全文本中提取 JSON 数组 [...]
        try:
            start = text.find("[")
            end = text.rfind("]")
            if start != -1 and end != -1 and end > start:
                candidate = text[start:end + 1]
                findings = json.loads(candidate)
                if isinstance(findings, list):
                    return findings
        except (json.JSONDecodeError, IndexError):
            pass

        # 无法解析，返回错误 Finding
        return [{
            "severity": "low",
            "file": fallback_file,
            "line": 0,
            "title": "LLM 输出解析失败",
            "reason": llm_output[:200],
            "suggestion": "检查 Reviewer Prompt 是否要求输出 JSON 格式",
        }]

    @abstractmethod
    def review(self, context: ReviewerContext) -> list[dict]:
        """执行审查，返回 Finding 列表。

        每个 Finding 格式:
          {"severity": "high", "file": "...", "line": 42,
           "title": "...", "reason": "...", "suggestion": "..."}
        """
        ...
