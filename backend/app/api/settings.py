"""设置接口：提供脱敏读取、用户配置保存和模型连接测试。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.config import settings
from app.engine.llm import LLMProvider
from app.services.settings_policy import (
    ConnectionTestResponse,
    LLMConnectionTestRequest,
    SettingsUpdateRequest,
    SettingsUpdateResponse,
)
from app.services.settings_service import (
    EffectiveSettingsSnapshot,
    SettingsConfigurationError,
    SettingsConflictError,
    SettingsInputError,
    SettingsServiceError,
    get_effective_settings_snapshot,
    get_settings_service,
    refresh_runtime_consumers,
)
from app.services.settings_store import SettingsStoreError


router = APIRouter(prefix="/api/settings", tags=["settings"])

# 连接测试只验证服务可用性，固定短响应上限，避免受页面草稿的生成上限影响。
_CONNECTION_TEST_MAX_TOKENS = 8


def _raise_settings_error(error: Exception) -> None:
    if isinstance(error, (SettingsInputError, ValueError)):
        raise HTTPException(
            status_code=422,
            detail={"code": "settings_input_invalid", "message": str(error)},
        ) from error
    if isinstance(error, SettingsConflictError):
        raise HTTPException(
            status_code=409,
            detail={"code": error.code, "message": str(error)},
        ) from error
    if isinstance(error, (SettingsConfigurationError, SettingsStoreError, SettingsServiceError)):
        raise HTTPException(
            status_code=500,
            detail={"code": getattr(error, "code", "settings_failed"), "message": str(error)},
        ) from error
    raise error


@router.get("", response_model=EffectiveSettingsSnapshot)
def get_settings() -> EffectiveSettingsSnapshot:
    try:
        return get_effective_settings_snapshot()
    except Exception as error:
        _raise_settings_error(error)
        raise AssertionError("unreachable")


@router.patch("", response_model=SettingsUpdateResponse)
def update_settings(request: SettingsUpdateRequest) -> SettingsUpdateResponse:
    try:
        snapshot, changed = get_settings_service().update(request)
        refresh_runtime_consumers()
        return SettingsUpdateResponse(
            config_version=snapshot.config_version,
            changed=changed,
            snapshot=snapshot,
        )
    except Exception as error:
        _raise_settings_error(error)
        raise AssertionError("unreachable")


@router.post("/test/llm", response_model=ConnectionTestResponse)
def test_llm_connection(request: LLMConnectionTestRequest) -> ConnectionTestResponse:
    """使用当前凭据和页面草稿测试模型服务，不保存草稿。"""

    try:
        snapshot = get_effective_settings_snapshot()
        draft = request.model_dump(exclude_none=True)
        llm = snapshot.settings.llm.model_dump()
        llm.update(draft)
        if snapshot.secret_status.llm_api_key != "configured":
            raise HTTPException(status_code=422, detail="请先配置模型服务 API Key")

        client = LLMProvider(
            api_key=settings.deepseek_api_key,
            base_url=llm["base_url"],
            model=llm["model"],
            temperature=llm["temperature"],
        )
        client.chat(
            [{"role": "user", "content": "请只回复 OK。"}],
            timeout_seconds=10,
            max_tokens=_CONNECTION_TEST_MAX_TOKENS,
        )
        return ConnectionTestResponse(ok=True, message="模型服务连接正常")
    except HTTPException:
        raise
    except TimeoutError as error:
        raise HTTPException(status_code=504, detail="模型服务连接超时，请检查地址或网络") from error
    except Exception as error:
        raise HTTPException(status_code=502, detail="模型服务连接失败，请检查地址、模型和 API Key") from error
