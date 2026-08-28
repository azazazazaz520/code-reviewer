"""LLM Provider — OpenAI 兼容接口抽象层。

支持 DeepSeek、OpenAI 及任何 OpenAI 兼容 API。
"""

from __future__ import annotations

import json
from openai import OpenAI

from app.config import settings
from typing import Callable


class LLMProvider:
    """统一的 LLM 调用接口。"""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ):
        self.client = OpenAI(
            api_key=settings.deepseek_api_key if api_key is None else api_key,
            base_url=settings.deepseek_base_url if base_url is None else base_url,
        )
        self.model = settings.llm_model if model is None else model
        self.temperature = settings.llm_temperature if temperature is None else temperature
        self.max_tokens = settings.llm_max_tokens if max_tokens is None else max_tokens

    def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        response_format: dict | None = None,
        timeout_seconds: float | None = None,
        max_tokens: int | None = None,
    ) -> dict:
        """单次 LLM 调用，返回完整响应。

        Returns:
            {"content": str | None, "tool_calls": list | None}
        """
        kwargs = dict(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            max_tokens=max_tokens or self.max_tokens,
        )
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        if response_format:
            kwargs["response_format"] = response_format

        client = self.client
        if timeout_seconds is not None:
            client = client.with_options(timeout=timeout_seconds)
        response = client.chat.completions.create(**kwargs)
        choice = response.choices[0]
        message = choice.message
        usage = getattr(response, "usage", None)
        usage_data = {
            key: getattr(usage, key)
            for key in ("prompt_tokens", "completion_tokens", "total_tokens")
            if usage is not None and getattr(usage, key, None) is not None
        }

        return {
            "content": message.content,
            "tool_calls": [
                {
                    "id": tc.id,
                    "name": tc.function.name,
                    "arguments": json.loads(tc.function.arguments),
                }
                for tc in (message.tool_calls or [])
            ],
            "finish_reason": choice.finish_reason,
            "usage": usage_data,
        }

    def _finalize_json(
        self,
        messages: list[dict],
        response_meta_hook: Callable[[dict], None] | None = None,
    ) -> str:
        messages.append(
            {
                "role": "user",
                "content": (
                    "请基于以上所有工具调用结果完成审查。只返回 JSON 对象，根节点必须包含 findings 数组，"
                    "例如 {\"findings\":[]}。如果没有满足报告门槛的问题，findings 才能为空；"
                    "不要输出 Markdown、解释文字或代码围栏。"
                ),
            }
        )
        json_format = {"type": "json_object"}

        def notify(result: dict) -> None:
            if response_meta_hook:
                response_meta_hook(
                    {
                        key: result[key]
                        for key in ("finish_reason", "usage")
                        if result.get(key) is not None
                    }
                )

        final = self.chat(messages, response_format=json_format)
        notify(final)
        content = final.get("content")
        if isinstance(content, str) and content.strip():
            return content

        messages.append(
            {
                "role": "user",
                "content": (
                    "上一条响应为空。请立即只输出 JSON 对象，格式必须是"
                    "{\"findings\":[...]}；只有确实没有问题时才能返回空 findings，"
                    "不要输出解释、Markdown 或代码围栏。"
                ),
            }
        )
        retry = self.chat(messages, response_format=json_format)
        notify(retry)
        retry_content = retry.get("content")
        return retry_content if isinstance(retry_content, str) else ""

    def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        tool_handlers: dict[str, callable],
        max_rounds: int = 3,
        log_hook: Callable | None = None,
        response_meta_hook: Callable[[dict], None] | None = None,
    ) -> str:
        """LLM 调用 + 自动执行 tool_calls 循环。

        每轮：LLM 决定是否调工具 → 执行工具 → 追加结果到消息。
        直到 LLM 返回纯文本或达到 max_rounds。
        """
        msgs = list(messages)

        for _ in range(max_rounds):
            result = self.chat(msgs, tools=tools)
            if response_meta_hook:
                response_meta_hook(
                    {
                        key: result[key]
                        for key in ("finish_reason", "usage")
                        if result.get(key) is not None
                    }
                )

            if result["content"] and not result["tool_calls"]:
                # 工具调用结束后的第一段 content 可能是分析过程，不能直接
                # 作为最终审查结果返回；统一走结构化 JSON 收口请求。
                msgs.append({"role": "assistant", "content": result["content"]})
                return self._finalize_json(msgs, response_meta_hook)

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
                    if log_hook:
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

                        log_hook(
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

        # 超过 max_rounds，强制要求 LLM 输出最终结果。
        # 这里必须重复机器可解析的输出契约，否则模型容易返回 Markdown 说明，
        # 让 Reviewer 看起来像“没有问题”，实际却没有完成审查。
        final_prompt = {
            "role": "user",
            "content": (
                "请基于以上所有工具调用结果完成审查。只返回 JSON 对象，根节点必须包含 findings 数组，"
                "例如 {\"findings\":[]}。如果没有满足报告门槛的问题，findings 才能为空；"
                "不要输出 Markdown、解释文字或代码围栏。"
            ),
        }
        msgs.append(final_prompt)
        json_format = {"type": "json_object"}
        final = self.chat(msgs, response_format=json_format)
        if response_meta_hook:
            response_meta_hook(
                {
                    key: final[key]
                    for key in ("finish_reason", "usage")
                    if final.get(key) is not None
                }
            )
        content = final.get("content")
        if isinstance(content, str) and content.strip():
            return content

        # 某些模型在工具调用达到上限后会返回空 content。再发一次短请求，
        # 避免把一次瞬时的空响应直接升级为审查失败；若仍为空，调用方仍会
        # 按原有逻辑报告解析错误，不会被误判为“没有问题”。
        msgs.append(
            {
                "role": "user",
                "content": (
                    "上一条响应为空。请立即只输出 JSON 对象，格式必须是"
                    "{\"findings\":[...]}；只有确实没有问题时才能返回空 findings，"
                    "不要输出解释、Markdown 或代码围栏。"
                ),
            }
        )
        retry = self.chat(msgs, response_format=json_format)
        if response_meta_hook:
            response_meta_hook(
                {
                    key: retry[key]
                    for key in ("finish_reason", "usage")
                    if retry.get(key) is not None
                }
            )
        retry_content = retry.get("content")
        return retry_content if isinstance(retry_content, str) else ""


# 全局单例
_llm: LLMProvider | None = None


def get_llm() -> LLMProvider:
    global _llm
    if _llm is None:
        _llm = LLMProvider()
    return _llm


def reset_llm() -> None:
    """丢弃旧配置创建的客户端，使后续任务读取最新模型设置。"""

    global _llm
    _llm = None
