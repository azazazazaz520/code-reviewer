"""User-facing messages for errors raised during a review workflow."""

from __future__ import annotations


def format_user_error(error: BaseException | str) -> str:
    """Convert known provider errors into concise, actionable messages."""
    raw = str(error).strip()
    lowered = raw.lower()

    if "insufficient balance" in lowered or (
        "402" in lowered and "balance" in lowered
    ):
        return "模型服务余额不足，请补充余额或更换模型服务后重试。"

    if "401" in lowered or "invalid api key" in lowered or "authentication" in lowered:
        return "模型服务认证失败，请检查 API Key 配置后重试。"

    if "429" in lowered or "rate limit" in lowered or "too many requests" in lowered:
        return "模型服务请求过于频繁，请稍后重试。"

    return raw or "模型服务调用失败，请稍后重试。"
