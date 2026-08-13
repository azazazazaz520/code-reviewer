"""提供脱敏的当前有效设置快照。

P0 只读取进程当前已经生效的配置。非敏感配置文件持久化、版本冲突和
运行时热更新属于 P1，本模块暂不读取或写入 settings.json，避免页面展示
一个尚未接入消费者的配置值。
"""

from __future__ import annotations

import os
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.config import settings


SettingsSource = Literal["default", "env", "user_file"]
SecretState = Literal["configured", "not_configured"]


class LLMSettingsSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: Literal["deepseek-openai-compatible"]
    model: str
    base_url: str
    temperature: float
    max_tokens: int


class ReviewSettingsSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_reflection_rounds: int
    context_files_per_round: int
    crg_enabled: bool


class PromptSettingsSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timeout_seconds: int
    min_input_chars: int
    max_input_chars: int
    max_output_tokens: int
    session_ttl_seconds: int
    session_max_count: int
    session_max_context_chars: int


class StorageSettingsSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repos_dir: str


class UserSettingsSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    llm: LLMSettingsSnapshot
    review: ReviewSettingsSnapshot
    prompt: PromptSettingsSnapshot
    storage: StorageSettingsSnapshot


class SecretStatusSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    llm_api_key: SecretState
    github_token: SecretState
    gitee_token: SecretState


class EffectiveSettingsSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=1, ge=1)
    # P0 没有用户配置文件，因此版本 0 表示当前进程配置而非持久化版本。
    config_version: int = Field(default=0, ge=0)
    sources: dict[str, SettingsSource]
    settings: UserSettingsSnapshot
    secret_status: SecretStatusSnapshot


_ENV_ALIASES: dict[str, tuple[str, ...]] = {
    "llm_provider": ("LLM_PROVIDER",),
    "llm_model": ("LLM_MODEL",),
    "llm_temperature": ("LLM_TEMPERATURE",),
    "llm_max_tokens": ("LLM_MAX_TOKENS",),
    "deepseek_base_url": ("DEEPSEEK_BASE_URL",),
    "max_reflection_rounds": ("MAX_REFLECTION_ROUNDS",),
    "context_files_per_round": ("CONTEXT_FILES_PER_ROUND",),
    "crg_enabled": ("CRG_ENABLED",),
    "prompt_timeout_seconds": ("PROMPT_TIMEOUT_SECONDS",),
    "prompt_min_input_chars": ("PROMPT_MIN_INPUT_CHARS",),
    "prompt_max_input_chars": ("PROMPT_MAX_INPUT_CHARS",),
    "prompt_max_output_tokens": ("PROMPT_MAX_OUTPUT_TOKENS",),
    "prompt_session_ttl_seconds": ("PROMPT_SESSION_TTL_SECONDS",),
    "prompt_session_max_count": ("PROMPT_SESSION_MAX_COUNT",),
    "prompt_session_max_context_chars": ("PROMPT_SESSION_MAX_CONTEXT_CHARS",),
    "repos_dir": ("REPOS_DIR",),
    "deepseek_api_key": ("DEEPSEEK_API_KEY",),
    "github_token": ("GITHUB_TOKEN",),
    "gitee_token": ("GITEE_TOKEN",),
}


def _field_source(field_name: str) -> SettingsSource:
    """将配置来源归类为默认值或环境配置，不暴露变量名。"""

    aliases = _ENV_ALIASES.get(field_name, (field_name.upper(),))
    if any(os.environ.get(alias) is not None for alias in aliases):
        return "env"

    # pydantic-settings 会将 .env 中加载的字段记录在 fields set 中；这里
    # 统一归类为 env，避免把 .env 文件名和变量名返回给 Renderer。
    fields_set = getattr(settings, "model_fields_set", set())
    if field_name in fields_set:
        return "env"
    return "default"


def _secret_state(value: str) -> SecretState:
    return "configured" if bool(value.strip()) else "not_configured"


def get_effective_settings_snapshot() -> EffectiveSettingsSnapshot:
    """读取当前已经生效的非敏感设置，并返回凭据状态。"""

    fields = {
        "llm.model": "llm_model",
        "llm.base_url": "deepseek_base_url",
        "llm.temperature": "llm_temperature",
        "llm.max_tokens": "llm_max_tokens",
        "review.max_reflection_rounds": "max_reflection_rounds",
        "review.context_files_per_round": "context_files_per_round",
        "review.crg_enabled": "crg_enabled",
        "prompt.timeout_seconds": "prompt_timeout_seconds",
        "prompt.min_input_chars": "prompt_min_input_chars",
        "prompt.max_input_chars": "prompt_max_input_chars",
        "prompt.max_output_tokens": "prompt_max_output_tokens",
        "prompt.session_ttl_seconds": "prompt_session_ttl_seconds",
        "prompt.session_max_count": "prompt_session_max_count",
        "prompt.session_max_context_chars": "prompt_session_max_context_chars",
        "storage.repos_dir": "repos_dir",
    }

    return EffectiveSettingsSnapshot(
        sources={path: _field_source(field) for path, field in fields.items()},
        settings=UserSettingsSnapshot(
            llm=LLMSettingsSnapshot(
                provider="deepseek-openai-compatible",
                model=settings.llm_model,
                base_url=settings.deepseek_base_url,
                temperature=settings.llm_temperature,
                max_tokens=settings.llm_max_tokens,
            ),
            review=ReviewSettingsSnapshot(
                max_reflection_rounds=settings.max_reflection_rounds,
                context_files_per_round=settings.context_files_per_round,
                crg_enabled=settings.crg_enabled,
            ),
            prompt=PromptSettingsSnapshot(
                timeout_seconds=settings.prompt_timeout_seconds,
                min_input_chars=settings.prompt_min_input_chars,
                max_input_chars=settings.prompt_max_input_chars,
                max_output_tokens=settings.prompt_max_output_tokens,
                session_ttl_seconds=settings.prompt_session_ttl_seconds,
                session_max_count=settings.prompt_session_max_count,
                session_max_context_chars=settings.prompt_session_max_context_chars,
            ),
            storage=StorageSettingsSnapshot(repos_dir=settings.repos_dir),
        ),
        secret_status=SecretStatusSnapshot(
            llm_api_key=_secret_state(settings.deepseek_api_key),
            github_token=_secret_state(settings.github_token),
            gitee_token=_secret_state(settings.gitee_token),
        ),
    )
