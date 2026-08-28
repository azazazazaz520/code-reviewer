from __future__ import annotations

from typing import Protocol, TypedDict


class PromptLLMResponse(TypedDict, total=False):
    content: str | None
    usage: dict[str, int]
    finish_reason: str | None


class PromptLLMClient(Protocol):
    """Prompt 生成所需的最小 LLM 接口。具体供应商由 Adapter 实现。"""

    model: str

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        response_format: dict[str, str],
        timeout_seconds: float,
        max_tokens: int,
    ) -> PromptLLMResponse: ...
