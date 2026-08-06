"""审查过程日志的批量持久化。"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from threading import Lock
from typing import Any, Callable

from app.models.base import SessionLocal
from app.models.repo import ReviewLog


class ReviewLogBuffer:
    """将高频日志写入独立数据库会话，避免干扰审查事务。"""

    def __init__(
        self,
        task_id: str,
        *,
        batch_size: int = 10,
        flush_interval: float = 5.0,
        session_factory: Callable[[], Any] = SessionLocal,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if batch_size < 1:
            raise ValueError("日志批量大小必须为正数")
        if flush_interval < 0:
            raise ValueError("日志刷新间隔不能为负数")
        self._task_id = task_id
        self._batch_size = batch_size
        self._flush_interval = flush_interval
        self._session_factory = session_factory
        self._clock = clock
        self._pending: list[dict[str, Any]] = []
        self._lock = Lock()
        self._last_flush = clock()

    def append(
        self,
        *,
        step: str,
        level: str,
        message: str,
        tool_name: str | None = None,
        tool_args: str | None = None,
    ) -> None:
        entry = {
            "task_id": self._task_id,
            "step": step,
            "level": level,
            "message": message,
            "tool_name": tool_name,
            "tool_args": tool_args,
            # 在入队时记录时间，批量提交不会打乱日志的展示顺序。
            "created_at": datetime.now(UTC),
        }
        with self._lock:
            self._pending.append(entry)
            should_flush = (
                len(self._pending) >= self._batch_size
                or self._clock() - self._last_flush >= self._flush_interval
            )
        if should_flush:
            self.flush()

    def flush(self) -> None:
        with self._lock:
            if not self._pending:
                return
            entries = self._pending
            self._pending = []
            self._last_flush = self._clock()

        try:
            session = self._session_factory()
        except Exception:
            return
        try:
            session.add_all([ReviewLog(**entry) for entry in entries])
            session.commit()
        except Exception:
            # 日志属于诊断信息，写入失败不能影响审查任务本身。
            try:
                session.rollback()
            except Exception:
                pass
        finally:
            try:
                session.close()
            except Exception:
                pass
