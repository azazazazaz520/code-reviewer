"""设置读取 API。

P0 只提供脱敏快照读取；配置保存、连接测试和凭据管理按实施方案延后。
"""

from fastapi import APIRouter

from app.services.settings_service import EffectiveSettingsSnapshot, get_effective_settings_snapshot


router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("", response_model=EffectiveSettingsSnapshot)
def get_settings() -> EffectiveSettingsSnapshot:
    return get_effective_settings_snapshot()
