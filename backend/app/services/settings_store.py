"""本机用户设置的版本化文件存储。

设置文件只保存非敏感用户配置。API Key 和代码托管 Token 由桌面主进程
负责安全存储，并在 sidecar 启动时以环境变量注入，避免进入普通 HTTP 响应。
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any


SETTINGS_SCHEMA_VERSION = 1


class SettingsStoreError(RuntimeError):
    """设置文件无法读取或写入。"""


class SettingsVersionConflict(SettingsStoreError):
    """设置文件已经被其他请求更新。"""


@dataclass(frozen=True)
class StoredSettings:
    schema_version: int
    config_version: int
    settings: dict[str, dict[str, Any]]


def default_settings_path() -> Path:
    """解析本机设置文件位置，桌面模式优先使用 sidecar 数据目录。"""

    explicit_path = os.environ.get("CODE_REVIEWER_SETTINGS_FILE")
    if explicit_path:
        return Path(explicit_path).expanduser().resolve()

    data_dir = os.environ.get("CODE_REVIEWER_DATA_DIR")
    if data_dir:
        return Path(data_dir).expanduser().resolve() / "settings.json"

    return Path("data/settings.json").resolve()


class SettingsStore:
    """提供原子读写和版本检查的设置存储接口。"""

    def __init__(self, path: Path | None = None) -> None:
        self.path = (path or default_settings_path()).expanduser().resolve()
        self._lock = threading.RLock()

    def load(self) -> StoredSettings:
        with self._lock:
            if not self.path.exists():
                return StoredSettings(SETTINGS_SCHEMA_VERSION, 0, {})

            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as error:
                raise SettingsStoreError("用户设置文件无法读取，请检查文件权限或恢复备份") from error

            if not isinstance(raw, dict):
                raise SettingsStoreError("用户设置文件格式无效")
            if raw.get("schema_version") != SETTINGS_SCHEMA_VERSION:
                raise SettingsStoreError("用户设置文件版本不受支持，请升级应用后重试")

            config_version = raw.get("config_version", 0)
            user_settings = raw.get("settings", {})
            if not isinstance(config_version, int) or config_version < 0:
                raise SettingsStoreError("用户设置版本无效")
            if not isinstance(user_settings, dict):
                raise SettingsStoreError("用户设置内容无效")
            if not all(isinstance(key, str) and isinstance(value, dict) for key, value in user_settings.items()):
                raise SettingsStoreError("用户设置分区格式无效")

            return StoredSettings(
                schema_version=SETTINGS_SCHEMA_VERSION,
                config_version=config_version,
                settings={str(key): dict(value) for key, value in user_settings.items()},
            )

    def save(
        self,
        user_settings: dict[str, dict[str, Any]],
        *,
        expected_version: int | None,
    ) -> StoredSettings:
        with self._lock:
            current = self.load()
            if expected_version is not None and expected_version != current.config_version:
                raise SettingsVersionConflict("设置已在其他窗口更新，请重新读取后再保存")

            next_value = StoredSettings(
                schema_version=SETTINGS_SCHEMA_VERSION,
                config_version=current.config_version + 1,
                settings={str(key): dict(value) for key, value in user_settings.items()},
            )
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "schema_version": next_value.schema_version,
                "config_version": next_value.config_version,
                "settings": next_value.settings,
            }

            try:
                with NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    dir=self.path.parent,
                    prefix=f".{self.path.name}.",
                    suffix=".tmp",
                    delete=False,
                ) as temporary:
                    json.dump(payload, temporary, ensure_ascii=False, indent=2)
                    temporary.write("\n")
                    temporary.flush()
                    os.fsync(temporary.fileno())
                    temporary_path = Path(temporary.name)
                os.replace(temporary_path, self.path)
            except OSError as error:
                try:
                    temporary_path.unlink(missing_ok=True)
                except UnboundLocalError:
                    pass
                raise SettingsStoreError("用户设置保存失败，原有配置未被覆盖") from error

            return next_value
