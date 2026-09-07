"""LLM Provider — OpenAI 兼容接口抽象层。

支持 DeepSeek、OpenAI 及任何 OpenAI 兼容 API。
"""

from __future__ import annotations


from openai import OpenAI

from app.config import settings


LLM_USAGE_RESPONSE_FIELDS = (
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "prompt_cache_hit_tokens",
    "prompt_cache_miss_tokens",
)
LLM_USAGE_METRIC_FIELDS = {
    "prompt_tokens": "llm_prompt_tokens",
    "completion_tokens": "llm_completion_tokens",
    "total_tokens": "llm_total_tokens",
    "prompt_cache_hit_tokens": "llm_prompt_cache_hit_tokens",
    "prompt_cache_miss_tokens": "llm_prompt_cache_miss_tokens",
}


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
        self.base_url = settings.deepseek_base_url if base_url is None else base_url
        self.model = settings.llm_model if model is None else model
        self.temperature = settings.llm_temperature if temperature is None else temperature
        self.max_tokens = settings.llm_max_tokens if max_tokens is None else max_tokens

    def chat(
        self,
        messages: list[dict],
        response_format: dict | None = None,
        timeout_seconds: float | None = None,
        max_tokens: int | None = None,
        thinking: str | None = None,
    ) -> dict:
        """单次 LLM 调用，返回完整响应。

        Returns:
            {"content": str | None, "reasoning_content": str | None, "usage": dict}
        """
        kwargs = dict(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens if max_tokens is None else max_tokens,
        )
        if thinking is not None and self._uses_deepseek():
            # DeepSeek 通过 OpenAI 兼容接口的 extra_body 控制思考模式。
            kwargs["extra_body"] = {"thinking": {"type": thinking}}
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
            for key in LLM_USAGE_RESPONSE_FIELDS
            if usage is not None and getattr(usage, key, None) is not None
        }

        return {
            "content": message.content,
            "reasoning_content": getattr(message, "reasoning_content", None),
            "finish_reason": choice.finish_reason,
            "usage": usage_data,
        }

    def _uses_deepseek(self) -> bool:
        """判断当前 Provider 是否需要 DeepSeek 的历史字段兼容处理。"""
        return "deepseek" in (
            f"{getattr(self, 'base_url', '')} {getattr(self, 'model', '')}"
        ).lower()



def get_llm() -> LLMProvider:
    global _llm
    if _llm is None:
        _llm = LLMProvider()
    return _llm


def reset_llm() -> None:
    """丢弃旧配置创建的客户端，使后续任务读取最新模型设置。"""

    global _llm
    _llm = None
