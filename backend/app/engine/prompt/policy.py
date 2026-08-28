from __future__ import annotations

from dataclasses import dataclass

from app.engine.prompt.schemas import PromptPersona


@dataclass(frozen=True)
class PromptPolicy:
    """描述一次生成所使用的提示词和输出契约版本。"""

    prompt_id: str = "devprompt-pro"
    prompt_version: str = "1.0.0"
    schema_version: str = "1"
    persona: PromptPersona = PromptPersona.GENERAL


def get_prompt_policy(persona: PromptPersona) -> PromptPolicy:
    return PromptPolicy(persona=persona)
