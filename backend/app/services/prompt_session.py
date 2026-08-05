from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
import threading
import uuid

from app.engine.prompt.schemas import PromptMode, PromptPersona, PromptResult


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


@dataclass
class PromptSession:
    session_id: str
    mode: PromptMode
    persona: PromptPersona
    turn: int
    max_turns: int
    messages: list[dict[str, str]]
    latest_result: PromptResult
    created_at: datetime
    expires_at: datetime


class PromptSessionStore:
    """带 TTL 和容量上限的进程内审查会话仓库。"""

    def __init__(
        self,
        ttl_seconds: int = 1800,
        max_sessions: int = 100,
        max_context_chars: int = 24000,
        max_turns: int = 3,
    ) -> None:
        self.ttl_seconds = ttl_seconds
        self.max_sessions = max_sessions
        self.max_context_chars = max_context_chars
        self.max_turns = max_turns
        self._sessions: dict[str, PromptSession] = {}
        self._lock = threading.RLock()

    def create(
        self,
        mode: PromptMode,
        persona: PromptPersona,
        messages: list[dict[str, str]],
        result: PromptResult,
    ) -> PromptSession:
        with self._lock:
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
                messages=self._copy_messages(messages),
                latest_result=result,
                created_at=now,
                expires_at=now + timedelta(seconds=self.ttl_seconds),
            )
            self._ensure_context_length(session.messages)
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
    ) -> PromptSession:
        with self._lock:
            session = self.get(session_id)
            if session.turn >= session.max_turns:
                raise PromptSessionLimitReached("审查会话最多支持 3 轮，请重新生成")
            self._ensure_context_length(messages)
            session.messages = self._copy_messages(messages)
            session.latest_result = result
            session.turn += 1
            session.expires_at = datetime.now(UTC) + timedelta(seconds=self.ttl_seconds)
            return session

    def delete(self, session_id: str) -> bool:
        with self._lock:
            return self._sessions.pop(session_id, None) is not None

    def _remove_expired(self) -> None:
        now = datetime.now(UTC)
        for session_id, session in list(self._sessions.items()):
            if session.expires_at <= now:
                del self._sessions[session_id]

    def _ensure_context_length(self, messages: list[dict[str, str]]) -> None:
        total = sum(len(message.get("content", "")) for message in messages)
        if total > self.max_context_chars:
            raise PromptSessionContextTooLong("审查会话上下文过长，请重新生成")

    @staticmethod
    def _copy_messages(messages: list[dict[str, str]]) -> list[dict[str, str]]:
        return [dict(message) for message in messages]
