from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
import threading
import uuid
from contextlib import contextmanager
from collections.abc import Iterator

from app.engine.prompt.schemas import PromptGenerationMetadata, PromptMode, PromptPersona, PromptResult


class PromptSessionError(RuntimeError):
    code = "prompt_session_invalid"


class PromptSessionNotFound(PromptSessionError):
    code = "prompt_session_not_found"


class PromptSessionExpired(PromptSessionError):
    code = "prompt_session_expired"


class PromptSessionLimitReached(PromptSessionError):
    code = "prompt_session_limit_reached"


class PromptSessionContextTooLong(PromptSessionError):
    code = "prompt_session_context_too_long"


class PromptSessionVersionConflict(PromptSessionError):
    code = "prompt_session_version_conflict"


@dataclass
class PromptSession:
    session_id: str
    mode: PromptMode
    persona: PromptPersona
    turn: int
    max_turns: int
    max_context_chars: int
    messages: list[dict[str, str]]
    latest_result: PromptResult
    created_at: datetime
    expires_at: datetime
    latest_metadata: PromptGenerationMetadata | None = None
    last_idempotency_key: str | None = None


class PromptSessionStore:
    """带 TTL 和容量上限的进程内审查会话仓库。"""

    def __init__(
        self,
        ttl_seconds: int = 1800,
        max_sessions: int = 100,
        max_context_chars: int = 24000,
        max_turns: int = 3,
    ) -> None:
        if ttl_seconds <= 0 or max_sessions <= 0 or max_context_chars <= 0 or max_turns <= 0:
            raise ValueError("Prompt 会话配置必须为正数")
        self.ttl_seconds = ttl_seconds
        self.max_sessions = max_sessions
        self.max_context_chars = max_context_chars
        self.max_turns = max_turns
        self._sessions: dict[str, PromptSession] = {}
        self._session_locks: dict[str, threading.Lock] = {}
        self._lock = threading.RLock()

    def create(
        self,
        mode: PromptMode,
        persona: PromptPersona,
        messages: list[dict[str, str]],
        result: PromptResult,
    ) -> PromptSession:
        with self._lock:
            # 先校验新会话，避免输入超限时错误淘汰已有会话。
            self._ensure_context_length(messages)
            self._remove_expired()
            while len(self._sessions) >= self.max_sessions:
                oldest_id = min(
                    self._sessions,
                    key=lambda session_id: self._sessions[session_id].created_at,
                )
                del self._sessions[oldest_id]
            now = datetime.now(UTC)
            session = PromptSession(
                session_id=str(uuid.uuid4()),
                mode=mode,
                persona=persona,
                turn=1,
                max_turns=self.max_turns,
                max_context_chars=self.max_context_chars,
                messages=self._copy_messages(messages),
                latest_result=result,
                created_at=now,
                expires_at=now + timedelta(seconds=self.ttl_seconds),
            )
            self._sessions[session.session_id] = session
            return session

    def get(self, session_id: str) -> PromptSession:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise PromptSessionNotFound("审查会话不存在，请重新生成")
            if session.expires_at <= datetime.now(UTC):
                del self._sessions[session_id]
                raise PromptSessionExpired("审查会话已过期，请重新生成")
            return session

    def advance(
        self,
        session_id: str,
        messages: list[dict[str, str]],
        result: PromptResult,
        metadata: PromptGenerationMetadata | None = None,
        expected_turn: int | None = None,
        idempotency_key: str | None = None,
    ) -> PromptSession:
        with self._lock:
            session = self.get(session_id)
            if expected_turn is not None and session.turn != expected_turn:
                raise PromptSessionVersionConflict("审查会话已被其他请求更新，请刷新后重试")
            if session.turn >= session.max_turns:
                raise PromptSessionLimitReached(
                    f"审查会话最多支持 {session.max_turns} 轮，请重新生成"
                )
            self._ensure_context_length(messages, session.max_context_chars)
            session.messages = self._copy_messages(messages)
            session.latest_result = result
            session.latest_metadata = metadata
            session.last_idempotency_key = idempotency_key
            session.turn += 1
            session.expires_at = datetime.now(UTC) + timedelta(seconds=self.ttl_seconds)
            return session

    def delete(self, session_id: str) -> bool:
        with self._lock:
            return self._sessions.pop(session_id, None) is not None

    @contextmanager
    def generation(self, session_id: str) -> Iterator[PromptSession]:
        """串行化同一会话的生成，避免并发反馈覆盖上下文。"""
        with self._lock:
            self.get(session_id)
            session_lock = self._session_locks.setdefault(session_id, threading.Lock())
        with session_lock:
            yield self.get(session_id)

    def ensure_context_length(self, messages: list[dict[str, str]]) -> None:
        with self._lock:
            self._ensure_context_length(messages)

    def refresh_limits(
        self,
        *,
        ttl_seconds: int,
        max_sessions: int,
        max_context_chars: int,
    ) -> None:
        """更新新会话默认限制，已存在会话保留创建时上下文上限。"""

        if ttl_seconds <= 0 or max_sessions <= 0 or max_context_chars <= 0:
            raise ValueError("Prompt 会话配置必须为正数")
        with self._lock:
            self.ttl_seconds = ttl_seconds
            self.max_sessions = max_sessions
            self.max_context_chars = max_context_chars

    def _remove_expired(self) -> None:
        now = datetime.now(UTC)
        for session_id, session in list(self._sessions.items()):
            if session.expires_at <= now:
                del self._sessions[session_id]

    def _ensure_context_length(self, messages: list[dict[str, str]], limit: int | None = None) -> None:
        total = sum(len(message.get("content", "")) for message in messages)
        if total > (limit or self.max_context_chars):
            raise PromptSessionContextTooLong("审查会话上下文过长，请重新生成")

    @staticmethod
    def _copy_messages(messages: list[dict[str, str]]) -> list[dict[str, str]]:
        return [dict(message) for message in messages]
