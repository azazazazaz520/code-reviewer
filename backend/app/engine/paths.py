"""审查快照内的路径规范化与边界校验。"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path


class PathSecurityError(ValueError):
    """路径无法证明属于当前审查快照。"""


_WINDOWS_DRIVE_PATTERN = re.compile(r"^[A-Za-z]:")


def normalize_relative_path(path: str, *, allow_empty: bool = False) -> str:
    """将仓库内路径规范化为 POSIX 形式，并拒绝越界语义。

    只移除明确的 ``./`` 前缀，保留 ``.env``、``.github`` 等合法隐藏路径。
    ``..``、绝对路径、UNC 路径和空字节永远不作为仓库内路径接受。
    """
    value = str(path or "").replace("\\", "/").strip()
    if "\x00" in value:
        raise PathSecurityError("路径不能包含空字节")

    while value.startswith("./"):
        value = value[2:]

    if value.startswith("/") or _WINDOWS_DRIVE_PATTERN.match(value):
        raise PathSecurityError("不允许使用绝对路径")

    if value in {"", "."}:
        if allow_empty:
            return ""
        raise PathSecurityError("路径不能为空")

    parts = value.split("/")
    if any(part == ".." for part in parts):
        raise PathSecurityError("路径不能包含 ..")
    if any(part == "" for part in parts):
        raise PathSecurityError("路径不能包含重复分隔符")
    return "/".join(parts)


def normalize_diff_path(path: str) -> str:
    """规范化 unified diff 中的 ``a/``、``b/`` 文件路径。"""
    value = str(path or "").replace("\\", "/").strip()
    if value.startswith("a/") or value.startswith("b/"):
        value = value[2:]
    return normalize_relative_path(value)


def relative_snapshot_path(repo_root: str | Path, path: str) -> str:
    """将快照内绝对或相对路径转换为受控的相对路径。"""
    root = Path(repo_root).resolve()
    raw = str(path or "").replace("\\", "/").strip()
    candidate = Path(raw)
    if candidate.is_absolute() or _WINDOWS_DRIVE_PATTERN.match(raw):
        try:
            relative = candidate.resolve(strict=False).relative_to(root)
        except ValueError as exc:
            raise PathSecurityError("路径超出审查快照根目录") from exc
        return normalize_relative_path(relative.as_posix())
    return normalize_relative_path(raw)


def resolve_snapshot_path(repo_root: str | Path, file_path: str) -> Path:
    """解析快照内路径，并在符号链接解析后再次检查边界。"""
    root = Path(repo_root).resolve()
    relative = normalize_relative_path(file_path)
    candidate = (root / Path(*relative.split("/"))).resolve(strict=False)
    try:
        resolved_relative = candidate.relative_to(root)
    except ValueError as exc:
        raise PathSecurityError("路径超出审查快照根目录") from exc
    if ".git" in resolved_relative.parts:
        raise PathSecurityError("不允许访问版本控制元数据目录")
    return candidate


@lru_cache(maxsize=4096)
def _cached_file_line_count(path_name: str, modified_ns: int, size: int) -> int:
    """在文件元数据未变化时复用行数，避免重复分配完整文本。"""
    count = 0
    has_bytes = False
    last_byte = b""
    with open(path_name, "rb") as handle:
        while chunk := handle.read(1024 * 1024):
            has_bytes = True
            count += chunk.count(b"\n")
            last_byte = chunk[-1:]
    if has_bytes and last_byte != b"\n":
        count += 1
    return count


def file_line_count(path: Path) -> int:
    """返回文本文件的实际行数，使用流式读取和元数据缓存。"""
    resolved = path.resolve()
    stat = resolved.stat()
    return _cached_file_line_count(
        str(resolved),
        stat.st_mtime_ns,
        stat.st_size,
    )
