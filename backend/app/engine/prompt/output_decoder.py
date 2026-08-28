from __future__ import annotations

import json
import re

from pydantic import ValidationError

from app.engine.prompt.schemas import PromptResult


class PromptOutputDecoder:
    """将模型返回的文本收敛为经过结构校验的 PromptResult。"""

    @staticmethod
    def parse(raw: str) -> PromptResult:
        text = raw.strip()
        candidates = [text]
        candidates.extend(
            match.group(1)
            for match in re.finditer(r"```(?:json)?\s*(.*?)```", text, re.IGNORECASE | re.DOTALL)
        )
        decoder = json.JSONDecoder()
        for candidate in candidates:
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict):
                    return PromptOutputDecoder._validate(PromptResult.model_validate(parsed))
            except (json.JSONDecodeError, ValidationError):
                pass
            start = candidate.find("{")
            while start >= 0:
                try:
                    parsed, _ = decoder.raw_decode(candidate[start:])
                    if isinstance(parsed, dict):
                        return PromptOutputDecoder._validate(PromptResult.model_validate(parsed))
                except (json.JSONDecodeError, ValidationError):
                    pass
                start = candidate.find("{", start + 1)
        raise ValueError("模型输出无法解析为 PromptResult")

    @staticmethod
    def _validate(result: PromptResult) -> PromptResult:
        """拦截结构合法但明显重复的输出，避免把格式正确误判为质量合格。"""
        for field_name in ("solution", "assumptions", "checks"):
            values = getattr(result, field_name)
            if len(values) != len(set(values)):
                raise ValueError(f"{field_name} 不应包含重复项")
        originals = [item.original for item in result.term_mappings]
        if len(originals) != len(set(originals)):
            raise ValueError("term_mappings 不应包含重复的原始表达")
        return result
