"""用户设置的输入模型与字段级策略。"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class SettingsPolicyError(ValueError):
    """设置不满足字段或关联约束。"""


class LLMSettingsPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str | None = Field(default=None, min_length=1, max_length=200)
    base_url: str | None = Field(default=None, min_length=1, max_length=500)
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1, le=100_000)

    @field_validator("model")
    @classmethod
    def validate_model(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("模型名称不能为空")
        return value.strip() if value else value

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        clean = value.strip().rstrip("/")
        parsed = urlparse(clean)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("模型服务地址必须是有效的 HTTP 或 HTTPS 地址")
        return clean


class ReviewSettingsPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_reflection_rounds: int | None = Field(default=None, ge=1, le=20)
    max_incremental_reflection_rounds: int | None = Field(default=None, ge=0, le=10)
    context_files_per_round: int | None = Field(default=None, ge=1, le=200)
    crg_enabled: bool | None = None
    review_unit_max_chars: int | None = Field(default=None, ge=8_000, le=100_000)
    review_context_max_files: int | None = Field(default=None, ge=1, le=50)
    review_context_max_chars: int | None = Field(default=None, ge=8_000, le=100_000)
    review_context_padding_lines: int | None = Field(default=None, ge=0, le=500)
    max_review_calls: int | None = Field(default=None, ge=1, le=500)
    max_review_duration_seconds: int | None = Field(default=None, ge=60, le=7_200)
    max_tool_rounds: int | None = Field(default=None, ge=1, le=10)
    max_tool_calls_per_unit: int | None = Field(default=None, ge=1, le=20)
    max_related_files_per_unit: int | None = Field(default=None, ge=1, le=20)
    review_parallelism: int | None = Field(default=None, ge=1, le=8)


class PromptSettingsPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timeout_seconds: int | None = Field(default=None, ge=1, le=600)
    min_input_chars: int | None = Field(default=None, ge=1, le=10_000)
    max_input_chars: int | None = Field(default=None, ge=1, le=100_000)
    max_output_tokens: int | None = Field(default=None, ge=1, le=100_000)
    session_ttl_seconds: int | None = Field(default=None, ge=60, le=86_400)
    session_max_count: int | None = Field(default=None, ge=1, le=10_000)
    session_max_context_chars: int | None = Field(default=None, ge=1, le=500_000)


class StorageSettingsPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repos_dir: str | None = Field(default=None, min_length=1, max_length=1000)

    @field_validator("repos_dir")
    @classmethod
    def validate_repos_dir(cls, value: str | None) -> str | None:
        if value is None:
            return None
        clean = str(Path(value.strip()).expanduser().resolve())
        if not clean:
            raise ValueError("仓库目录不能为空")
        return clean


class UserSettingsPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    llm: LLMSettingsPatch | None = None
    review: ReviewSettingsPatch | None = None
    prompt: PromptSettingsPatch | None = None
    storage: StorageSettingsPatch | None = None

    @model_validator(mode="after")
    def validate_non_empty(self) -> "UserSettingsPatch":
        if not any(value is not None for value in (self.llm, self.review, self.prompt, self.storage)):
            raise ValueError("至少需要修改一个设置分区")
        return self


class SettingsUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int | None = Field(default=None, ge=0)
    settings: UserSettingsPatch


class SettingsChange(BaseModel):
    path: str
    effective_for: str
    requires_restart: bool = False


class SettingsUpdateResponse(BaseModel):
    status: str = "saved"
    config_version: int
    changed: list[SettingsChange]
    snapshot: Any


class LLMConnectionTestRequest(LLMSettingsPatch):
    """连接测试只接收非敏感的临时草稿。"""


class ConnectionTestResponse(BaseModel):
    ok: bool
    message: str
