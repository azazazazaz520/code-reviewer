"""LLM Provider — OpenAI 兼容接口抽象层。

支持 DeepSeek、OpenAI 及任何 OpenAI 兼容 API。
"""

from __future__ import annotations

import json
from openai import OpenAI

from app.config import settings
from typing import Callable

_log_hook: Callable | None = None


def set_log_hook(hook: Callable | None):
    global _log_hook
    _log_hook = hook


class LLMProvider:
    """统一的 LLM 调用接口。"""

    def __init__(self):
        self.client = OpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
        )
        self.model = settings.llm_model
        self.temperature = settings.llm_temperature
        self.max_tokens = settings.llm_max_tokens

    def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> dict:
        """单次 LLM 调用，返回完整响应。

        Returns:
            {"content": str | None, "tool_calls": list | None}
        """
        kwargs = dict(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        response = self.client.chat.completions.create(**kwargs)
        choice = response.choices[0].message

        return {
            "content": choice.content,
            "tool_calls": [
                {
                    "id": tc.id,
                    "name": tc.function.name,
                    "arguments": json.loads(tc.function.arguments),
                }
                for tc in (choice.tool_calls or [])
            ],
        }

    def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        tool_handlers: dict[str, callable],
        max_rounds: int = 3,
    ) -> str:
        """LLM 调用 + 自动执行 tool_calls 循环。

        每轮：LLM 决定是否调工具 → 执行工具 → 追加结果到消息。
        直到 LLM 返回纯文本或达到 max_rounds。
        """
        msgs = list(messages)

        for _ in range(max_rounds):
            result = self.chat(msgs, tools=tools)

            if result["content"] and not result["tool_calls"]:
                return result["content"]

            if result["tool_calls"]:
                msgs.append({
                    "role": "assistant",
                    "content": result["content"],
                    "tool_calls": [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": json.dumps(tc["arguments"], ensure_ascii=False),
                            },
                        }
                        for tc in result["tool_calls"]
                    ],
                })

                for tc in result["tool_calls"]:
                    handler = tool_handlers.get(tc["name"])
                    tool_result = handler(**tc["arguments"]) if handler else json.dumps({"error": f"unknown tool: {tc['name']}"})

                    # 日志插桩
                    if _log_hook:
                        try:
                            args_str = json.dumps(tc["arguments"], ensure_ascii=False)
                            if len(args_str) > 200:
                                args_str = args_str[:197] + "..."
                        except Exception:
                            args_str = str(tc["arguments"])[:200]

                        # 简短摘要：取第一个有意义的参数值
                        args_dict = tc.get("arguments") or {}
                        summary = args_dict.get("file_path") or args_dict.get("path") or ""
                        if not summary and isinstance(args_dict, dict):
                            vals = [str(v) for v in args_dict.values() if not str(v).startswith("{")]
                            summary = vals[0] if vals else ""
                        if summary and len(summary) > 60:
                            summary = "..." + summary[-57:]

                        _log_hook(
                            step="tool_call",
                            level="info",
                            message=f"{tc['name']}: {summary}" if summary else tc["name"],
                            tool_name=tc["name"],
                            tool_args=args_str,
                        )

                    msgs.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": tool_result if isinstance(tool_result, str) else json.dumps(tool_result, ensure_ascii=False),
                    })

        # 超过 max_rounds，强制要求 LLM 输出最终结果
        msgs.append({"role": "user", "content": "请基于以上所有工具调用结果，给出最终审查结论。"})
        final = self.chat(msgs)
        return final.get("content", "")


# 全局单例
_llm: LLMProvider | None = None


def get_llm() -> LLMProvider:
    global _llm
    if _llm is None:
        _llm = LLMProvider()
    return _llm
