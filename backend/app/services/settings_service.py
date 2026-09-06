"""设置模块的深接口：读取、校验、持久化并应用用户配置。"""

from __future__ import annotations

import copy
import os
import threading
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.config import settings
from app.services.settings_policy import (
    LLMSettingsPatch,
    PromptSettingsPatch,
    ReviewSettingsPatch,
    SettingsChange,
    SettingsPolicyError,
    SettingsUpdateRequest,
    StorageSettingsPatch,
)
from app.services.settings_store import SettingsStore, SettingsStoreError, SettingsVersionConflict


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
    max_incremental_reflection_rounds: int
    context_files_per_round: int
    crg_enabled: bool
    review_unit_max_chars: int
    review_context_max_files: int
    review_context_max_chars: int
    review_context_padding_lines: int
    max_review_calls: int
    max_review_duration_seconds: int
    max_tool_rounds: int
    max_tool_calls_per_unit: int
    max_related_files_per_unit: int
    review_parallelism: int


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
    config_version: int = Field(default=0, ge=0)
    sources: dict[str, SettingsSource]
    settings: UserSettingsSnapshot
    secret_status: SecretStatusSnapshot


class SettingsServiceError(RuntimeError):
    """设置服务无法完成读取、校验或保存。"""

    code = "settings_failed"


class SettingsInputError(SettingsServiceError):
    code = "settings_input_invalid"


class SettingsConfigurationError(SettingsServiceError):
    code = "settings_configuration_invalid"


class SettingsConflictError(SettingsServiceError):
    code = "settings_version_conflict"


_ENV_ALIASES: dict[str, tuple[str, ...]] = {
    "llm_model": ("LLM_MODEL",),
    "llm_temperature": ("LLM_TEMPERATURE",),
    "llm_max_tokens": ("LLM_MAX_TOKENS",),
    "deepseek_base_url": ("DEEPSEEK_BASE_URL",),
    "max_reflection_rounds": ("MAX_REFLECTION_ROUNDS",),
    "max_incremental_reflection_rounds": ("MAX_INCREMENTAL_REFLECTION_ROUNDS",),
    "context_files_per_round": ("CONTEXT_FILES_PER_ROUND",),
    "crg_enabled": ("CRG_ENABLED",),
    "review_unit_max_chars": ("REVIEW_UNIT_MAX_CHARS",),
    "review_context_max_files": ("REVIEW_CONTEXT_MAX_FILES",),
    "review_context_max_chars": ("REVIEW_CONTEXT_MAX_CHARS",),
    "review_context_padding_lines": ("REVIEW_CONTEXT_PADDING_LINES",),
    "max_review_calls": ("MAX_REVIEW_CALLS",),
    "max_review_duration_seconds": ("MAX_REVIEW_DURATION_SECONDS",),
    "max_tool_rounds": ("MAX_TOOL_ROUNDS",),
    "max_tool_calls_per_unit": ("MAX_TOOL_CALLS_PER_UNIT",),
    "max_related_files_per_unit": ("MAX_RELATED_FILES_PER_UNIT",),
    "review_parallelism": ("REVIEW_PARALLELISM",),
    "prompt_timeout_seconds": ("PROMPT_TIMEOUT_SECONDS",),
    "prompt_min_input_chars": ("PROMPT_MIN_INPUT_CHARS",),
    "prompt_max_input_chars": ("PROMPT_MAX_INPUT_CHARS",),
    "prompt_max_output_tokens": ("PROMPT_MAX_OUTPUT_TOKENS",),
    "prompt_session_ttl_seconds": ("PROMPT_SESSION_TTL_SECONDS",),
    "prompt_session_max_count": ("PROMPT_SESSION_MAX_COUNT",),
    "prompt_session_max_context_chars": ("PROMPT_SESSION_MAX_CONTEXT_CHARS",),
    "repos_dir": ("REPOS_DIR",),
}

_FIELD_PATHS: dict[str, str] = {
    "llm.model": "llm_model",
    "llm.base_url": "deepseek_base_url",
    "llm.temperature": "llm_temperature",
    "llm.max_tokens": "llm_max_tokens",
    "review.max_reflection_rounds": "max_reflection_rounds",
    "review.max_incremental_reflection_rounds": "max_incremental_reflection_rounds",
    "review.context_files_per_round": "context_files_per_round",
    "review.crg_enabled": "crg_enabled",
    "review.review_unit_max_chars": "review_unit_max_chars",
    "review.review_context_max_files": "review_context_max_files",
    "review.review_context_max_chars": "review_context_max_chars",
    "review.review_context_padding_lines": "review_context_padding_lines",
    "review.max_review_calls": "max_review_calls",
    "review.max_review_duration_seconds": "max_review_duration_seconds",
    "review.max_tool_rounds": "max_tool_rounds",
    "review.max_tool_calls_per_unit": "max_tool_calls_per_unit",
    "review.max_related_files_per_unit": "max_related_files_per_unit",
    "review.review_parallelism": "review_parallelism",
    "prompt.timeout_seconds": "prompt_timeout_seconds",
    "prompt.min_input_chars": "prompt_min_input_chars",
    "prompt.max_input_chars": "prompt_max_input_chars",
    "prompt.max_output_tokens": "prompt_max_output_tokens",
    "prompt.session_ttl_seconds": "prompt_session_ttl_seconds",
    "prompt.session_max_count": "prompt_session_max_count",
    "prompt.session_max_context_chars": "prompt_session_max_context_chars",
    "storage.repos_dir": "repos_dir",
}


def _field_source(field_name: str) -> SettingsSource:
    aliases = _ENV_ALIASES.get(field_name, (field_name.upper(),))
    if any(os.environ.get(alias) is not None for alias in aliases):
        return "env"
    fields_set = getattr(settings, "model_fields_set", set())
    return "env" if field_name in fields_set else "default"


def _secret_state(value: str) -> SecretState:
    return "configured" if bool(value.strip()) else "not_configured"


def _deep_merge(left: dict[str, dict[str, Any]], right: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    merged = copy.deepcopy(left)
    for section, values in right.items():
        merged.setdefault(section, {}).update(values)
    return merged


class SettingsService:
    """隐藏文件格式、全局配置刷新和字段策略的设置模块接口。"""

    def __init__(self, store: SettingsStore | None = None) -> None:
        self.store = store or SettingsStore()
        self._lock = threading.RLock()
        self._initialized = False
        self._stored_settings: dict[str, dict[str, Any]] = {}
        self._config_version = 0

    def initialize(self) -> EffectiveSettingsSnapshot:
        with self._lock:
            if not self._initialized:
                try:
                    stored = self.store.load()
                    self._validate_stored_settings(stored.settings)
                except SettingsStoreError:
                    raise
                except (TypeError, ValueError) as error:
                    raise SettingsConfigurationError("用户设置文件中的值无效，请修正或删除该文件") from error

                self._stored_settings = copy.deepcopy(stored.settings)
                self._config_version = stored.config_version
                self._apply_settings(self._stored_settings)
                self._initialized = True
            return self._snapshot()

    def get_snapshot(self) -> EffectiveSettingsSnapshot:
        self.initialize()
        with self._lock:
            return self._snapshot()

    def update(self, request: SettingsUpdateRequest) -> tuple[EffectiveSettingsSnapshot, list[SettingsChange]]:
        self.initialize()
        with self._lock:
            if request.expected_version is not None and request.expected_version != self._config_version:
                raise SettingsConflictError("设置已在其他窗口更新，请重新读取后再保存")

            patch = request.settings.model_dump(exclude_none=True)
            candidate = _deep_merge(self._stored_settings, patch)
            try:
                self._validate_stored_settings(candidate)
            except (TypeError, ValueError, SettingsPolicyError) as error:
                raise SettingsInputError(str(error)) from error

            try:
                stored = self.store.save(candidate, expected_version=self._config_version)
            except SettingsVersionConflict as error:
                raise SettingsConflictError(str(error)) from error
            except SettingsStoreError:
                raise

            self._stored_settings = copy.deepcopy(stored.settings)
            self._config_version = stored.config_version
            self._apply_settings(self._stored_settings)
            if "repos_dir" in self._stored_settings.get("storage", {}):
                Path(settings.repos_dir).mkdir(parents=True, exist_ok=True)

            changed = [
                SettingsChange(
                    path=path,
                    effective_for=(
                        "new_prompt_requests"
                        if path.startswith("llm.") or path.startswith("prompt.")
                        else "new_reviews"
                    ),
                    requires_restart=False,
                )
                for path in self._changed_paths(patch)
            ]
            return self._snapshot(), changed

    def _changed_paths(self, patch: dict[str, dict[str, Any]]) -> list[str]:
        return [
            f"{section}.{field}"
            for section, values in patch.items()
            for field in values
            if f"{section}.{field}" in _FIELD_PATHS
        ]

    def _validate_stored_settings(self, values: dict[str, dict[str, Any]]) -> None:
        allowed_models = {
            "llm": LLMSettingsPatch,
            "review": ReviewSettingsPatch,
            "prompt": PromptSettingsPatch,
            "storage": StorageSettingsPatch,
        }
        for section, section_values in values.items():
            model = allowed_models.get(section)
            if model is None:
                raise SettingsPolicyError(f"不支持的设置分区：{section}")
            model.model_validate(section_values)

        prompt_values = values.get("prompt", {})
        min_chars = prompt_values.get("min_input_chars", settings.prompt_min_input_chars)
        max_chars = prompt_values.get("max_input_chars", settings.prompt_max_input_chars)
        if min_chars > max_chars:
            raise SettingsPolicyError("Prompt 最小输入长度不能大于最大输入长度")

    def _apply_settings(self, values: dict[str, dict[str, Any]]) -> None:
        for section, section_values in values.items():
            for field, value in section_values.items():
                config_field = _FIELD_PATHS.get(f"{section}.{field}")
                if config_field:
                    setattr(settings, config_field, value)

    def _snapshot(self) -> EffectiveSettingsSnapshot:
        return EffectiveSettingsSnapshot(
            schema_version=1,
            config_version=self._config_version,
            sources={
                path: (
                    "user_file"
                    if path.split(".")[0] in self._stored_settings
                    and path.split(".")[1] in self._stored_settings[path.split(".")[0]]
                    else _field_source(field)
                )
                for path, field in _FIELD_PATHS.items()
            },
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
                    max_incremental_reflection_rounds=settings.max_incremental_reflection_rounds,
                    context_files_per_round=settings.context_files_per_round,
                    crg_enabled=settings.crg_enabled,
                    review_unit_max_chars=settings.review_unit_max_chars,
                    review_context_max_files=settings.review_context_max_files,
                    review_context_max_chars=settings.review_context_max_chars,
                    review_context_padding_lines=settings.review_context_padding_lines,
                    max_review_calls=settings.max_review_calls,
                    max_review_duration_seconds=settings.max_review_duration_seconds,
                    max_tool_rounds=settings.max_tool_rounds,
                    max_tool_calls_per_unit=settings.max_tool_calls_per_unit,
                    max_related_files_per_unit=settings.max_related_files_per_unit,
                    review_parallelism=settings.review_parallelism,
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


_service = SettingsService()


def get_settings_service() -> SettingsService:
    return _service


def initialize_settings() -> EffectiveSettingsSnapshot:
    return _service.initialize()


def get_effective_settings_snapshot() -> EffectiveSettingsSnapshot:
    return _service.get_snapshot()


def refresh_runtime_consumers() -> None:
    """让后续请求和新任务使用已保存设置，当前任务继续使用原对象。"""

    from app.engine.llm import reset_llm

    reset_llm()
    try:
        from app.api.prompts import optimizer

        optimizer.refresh_settings()
    except ImportError:
        # 启动早期导入顺序不应阻断设置文件加载；Prompt API 首次请求时会读取全局设置。
        pass
