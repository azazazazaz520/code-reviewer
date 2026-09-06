"""Reviewer Tool 的任务级快照上下文与文件授权。"""

from __future__ import annotations

import json
from threading import Event, Lock
from dataclasses import dataclass, field, replace
from functools import lru_cache
from typing import Any, Callable

from app.engine.paths import (
    PathSecurityError,
    file_line_count,
    normalize_relative_path,
    relative_snapshot_path,
    resolve_snapshot_path,
)


@dataclass(frozen=True)
class ApprovedContextRef:
    """允许 Reviewer 读取的一个快照文件行范围。"""

    file_path: str
    start_line: int
    end_line: int
    source: str = "changed_file"
    result_id: str | None = None
    rule_id: str | None = None
    database_id: str | None = None

    def as_dict(self) -> dict:
        return {
            "file": self.file_path,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "source": self.source,
            "result_id": self.result_id,
            "rule_id": self.rule_id,
            "database_id": self.database_id,
        }


@dataclass(frozen=True)
class TaskToolContext:
    """绑定单次审查快照、revision 和已批准上下文引用。"""

    repo_root: str
    revision: str
    database_id: str = ""
    approved_context_refs: tuple[ApprovedContextRef, ...] = field(default_factory=tuple)

    def with_database(self, database_id: str) -> "TaskToolContext":
        return replace(self, database_id=database_id)

    def with_refs(self, refs: list[ApprovedContextRef]) -> "TaskToolContext":
        merged = list(self.approved_context_refs)
        seen = {
            (ref.file_path, ref.start_line, ref.end_line, ref.source, ref.result_id)
            for ref in merged
        }
        for ref in refs:
            key = (ref.file_path, ref.start_line, ref.end_line, ref.source, ref.result_id)
            if key not in seen:
                merged.append(ref)
                seen.add(key)
        return replace(self, approved_context_refs=tuple(merged))

    def refs_for(self, file_path: str) -> list[ApprovedContextRef]:
        try:
            normalized = relative_snapshot_path(self.repo_root, file_path)
        except PathSecurityError:
            return []
        return [ref for ref in self.approved_context_refs if ref.file_path == normalized]

    def can_read(self, file_path: str, start_line: int, end_line: int) -> bool:
        return any(
            start_line >= ref.start_line and end_line <= ref.end_line
            for ref in self.refs_for(file_path)
        )


@dataclass
class TaskToolCache:
    """同一审查任务内复用稳定 Tool 结果，包含错误和空结果。"""

    values: dict[str, Any] = field(default_factory=dict)
    hits: int = 0
    misses: int = 0
    calls: int = 0
    requests: int = 0
    read_file_requests: int = 0
    read_file_cache_hits: int = 0
    read_file_cache_misses: int = 0
    read_file_errors: int = 0
    _lock: Lock = field(default_factory=Lock, repr=False)
    _inflight: dict[str, Event] = field(default_factory=dict, repr=False)

    def get_or_load(
        self,
        revision: str,
        tool_name: str,
        arguments: dict[str, Any],
        loader: Callable[[], Any],
    ) -> tuple[Any, bool]:
        """按固定 revision 和规范化参数读取结果，命中时不执行 loader。"""
        key = json.dumps(
            {
                "revision": revision,
                "tool": tool_name,
                "arguments": arguments,
            },
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
        with self._lock:
            self.requests += 1
            if tool_name == "ReadFile":
                self.read_file_requests += 1
            if key in self.values:
                self.hits += 1
                if tool_name == "ReadFile":
                    self.read_file_cache_hits += 1
                return self.values[key], True
            waiting = self._inflight.get(key)
            if waiting is not None:
                self.hits += 1
                if tool_name == "ReadFile":
                    self.read_file_cache_hits += 1
                owner = False
            else:
                waiting = Event()
                self._inflight[key] = waiting
                self.misses += 1
                self.calls += 1
                if tool_name == "ReadFile":
                    self.read_file_cache_misses += 1
                owner = True
        if not owner:
            waiting.wait()
            with self._lock:
                return self.values.get(key), True
        try:
            result = loader()
        except Exception as exc:
            result = f"Error: {type(exc).__name__}: {exc}"
        with self._lock:
            self.values[key] = result
            if tool_name == "ReadFile" and (
                (isinstance(result, str) and result.startswith("Error:"))
                or bool(getattr(result, "error", None))
            ):
                self.read_file_errors += 1
            event = self._inflight.pop(key, None)
            if event:
                event.set()
        return result, False

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {
                "tool_calls": self.calls,
                "tool_requests": self.requests,
                "cache_hits": self.hits,
                "cache_misses": self.misses,
                "read_file_requests": self.read_file_requests,
                "read_file_cache_hits": self.read_file_cache_hits,
                "read_file_cache_misses": self.read_file_cache_misses,
                "read_file_errors": self.read_file_errors,
            }


@dataclass
class ToolCallBudget:
    """单个 ReviewUnit 的 Tool 调用预算。"""

    max_calls: int
    calls: int = 0
    exhausted: bool = False

    def reserve(self) -> bool:
        if self.max_calls > 0 and self.calls >= self.max_calls:
            self.exhausted = True
            return False
        self.calls += 1
        return True


@lru_cache(maxsize=1024)
def _build_changed_file_refs_cached(
    repo_root: str,
    revision: str,
    changed_files: tuple[str, ...],
) -> tuple[ApprovedContextRef, ...]:
    """为 Review Plan 直接负责的变更文件批准其实际源码行范围。"""
    refs: list[ApprovedContextRef] = []
    for file_path in changed_files:
        try:
            normalized = normalize_relative_path(file_path)
            resolved = resolve_snapshot_path(repo_root, normalized)
            if not resolved.is_file():
                continue
            line_count = file_line_count(resolved)
            refs.append(
                ApprovedContextRef(
                    file_path=normalized,
                    start_line=1,
                    end_line=max(1, line_count),
                    source="changed_file",
                )
            )
        except (OSError, PathSecurityError):
            continue
    return tuple(refs)


def build_changed_file_refs(
    repo_root: str,
    changed_files: list[str],
    *,
    revision: str = "",
) -> list[ApprovedContextRef]:
    """为变更文件批准行范围，并按快照 revision 缓存稳定结果。"""
    normalized_files: list[str] = []
    for file_path in changed_files:
        try:
            normalized = relative_snapshot_path(repo_root, file_path)
        except PathSecurityError:
            continue
        if normalized not in normalized_files:
            normalized_files.append(normalized)
    return list(_build_changed_file_refs_cached(
        str(repo_root),
        revision,
        tuple(normalized_files),
    ))
