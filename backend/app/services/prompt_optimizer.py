from __future__ import annotations

from dataclasses import dataclass
from copy import deepcopy
from time import monotonic
import threading
from typing import Any

from app.config import settings
from app.engine.llm import get_llm
from app.engine.prompt.client import PromptLLMClient, PromptLLMResponse
from app.engine.prompt.mapping import suggest_term_mappings
from app.engine.prompt.output_decoder import PromptOutputDecoder
from app.engine.prompt.policy import PromptPolicy, get_prompt_policy
from app.engine.prompt.prompt_builder import build_prompt_messages
from app.engine.prompt.schemas import (
    PromptGenerationMetadata,
    PromptMode,
    PromptOptimizeRequest,
    PromptResult,
)
from app.services.prompt_session import (
    PromptSession,
    PromptSessionLimitReached,
    PromptSessionStore,
    PromptSessionVersionConflict,
)


class PromptOptimizerError(RuntimeError):
    code = "prompt_optimizer_error"


class PromptInputError(PromptOptimizerError):
    code = "prompt_input_invalid"


class PromptLLMError(PromptOptimizerError):
    code = "prompt_llm_failed"


class PromptLLMTimeout(PromptLLMError):
    code = "prompt_llm_timeout"


class PromptLLMEmptyResponse(PromptLLMError):
    code = "prompt_llm_empty_response"


class PromptOutputError(PromptOptimizerError):
    code = "prompt_output_contract_failed"


class PromptOutputRepairError(PromptOutputError):
    code = "prompt_output_repair_failed"


@dataclass
class _GenerationBudget:
    deadline: float
    attempts: int = 0
    last_timeout: float | None = None

    @classmethod
    def create(cls, timeout_seconds: float) -> "_GenerationBudget":
        if timeout_seconds <= 0:
            raise PromptLLMTimeout("模型服务响应超时，请稍后重试")
        return cls(deadline=monotonic() + timeout_seconds)

    def next_timeout(self) -> float:
        remaining = self.deadline - monotonic()
        if remaining <= 0:
            raise PromptLLMTimeout("模型服务响应超时，请稍后重试")
        self.attempts += 1
        if self.last_timeout is not None:
            # 即使两次调用落在同一个高精度时钟刻度，也要把重试预算收窄，
            # 避免修复请求重新获得完整超时时间。
            remaining = min(remaining, max(self.last_timeout - 0.001, 0.001))
        self.last_timeout = remaining
        return remaining


class PromptOptimizer:
    def __init__(
        self,
        llm: PromptLLMClient | Any | None = None,
        session_store: PromptSessionStore | None = None,
    ) -> None:
        self._llm = llm
        self._initial_request_lock = threading.RLock()
        self._initial_requests: dict[
            str,
            tuple[float, PromptResult, PromptGenerationMetadata, PromptSession],
        ] = {}
        self.sessions = session_store or PromptSessionStore(
            ttl_seconds=settings.prompt_session_ttl_seconds,
            max_sessions=settings.prompt_session_max_count,
            max_context_chars=settings.prompt_session_max_context_chars,
        )

    def refresh_settings(self) -> None:
        """更新新 Prompt 会话的限制，不改变已有会话的轮次契约。"""

        self.sessions.refresh_limits(
            ttl_seconds=settings.prompt_session_ttl_seconds,
            max_sessions=settings.prompt_session_max_count,
            max_context_chars=settings.prompt_session_max_context_chars,
        )

    def optimize(
        self,
        request: PromptOptimizeRequest,
    ) -> tuple[PromptResult, PromptGenerationMetadata, PromptSession | None]:
        cached = self._get_initial_request(request.idempotency_key)
        if cached is not None:
            return cached

        content = self._sanitize(request.content, "content")
        mappings = suggest_term_mappings(content) if request.glossary_enabled else []
        policy = get_prompt_policy(request.persona)
        messages = build_prompt_messages(content, request.persona, mappings, policy)
        if request.mode == PromptMode.REVIEW:
            self.sessions.ensure_context_length(messages)
        result, metadata = self._generate(messages, policy)
        session = None
        if request.mode == PromptMode.REVIEW:
            session_messages = messages + [
                {"role": "assistant", "content": result.model_dump_json(ensure_ascii=False)},
            ]
            session = self.sessions.create(request.mode, request.persona, session_messages, result)
            metadata = metadata.model_copy(update={"turn": session.turn})
            self._store_initial_request(request.idempotency_key, result, metadata, session)
        else:
            metadata = metadata.model_copy(update={"turn": 1})
        return result, metadata, session

    def add_review_turn(
        self,
        session_id: str,
        feedback: str,
        expected_turn: int | None = None,
        idempotency_key: str | None = None,
    ) -> tuple[PromptResult, PromptGenerationMetadata, PromptSession]:
        with self.sessions.generation(session_id) as session:
            if idempotency_key and session.last_idempotency_key == idempotency_key:
                if session.latest_metadata is not None:
                    return session.latest_result, session.latest_metadata, session
            if expected_turn is not None and session.turn != expected_turn:
                raise PromptSessionVersionConflict("审查会话已被其他请求更新，请刷新后重试")
            if session.turn >= session.max_turns:
                raise PromptSessionLimitReached(
                    f"审查会话最多支持 {session.max_turns} 轮，请重新生成"
                )

            clean_feedback = self._sanitize(feedback, "feedback")
            messages = list(session.messages)
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "<review_feedback>\n"
                        f"{clean_feedback}\n"
                        "</review_feedback>\n"
                        "请保留已确认的信息，仅根据这次确认或修正意见更新结构化结果。"
                    ),
                }
            )
            self.sessions.ensure_context_length(messages)
            policy = get_prompt_policy(session.persona)
            result, metadata = self._generate(messages, policy)
            metadata = metadata.model_copy(update={"turn": session.turn + 1})
            updated = self.sessions.advance(
                session_id,
                messages + [{"role": "assistant", "content": result.model_dump_json(ensure_ascii=False)}],
                result,
                metadata=metadata,
                expected_turn=session.turn,
                idempotency_key=idempotency_key,
            )
            return result, metadata, updated

    def get_session(self, session_id: str) -> PromptSession:
        return self.sessions.get(session_id)

    def delete_session(self, session_id: str) -> bool:
        return self.sessions.delete(session_id)

    def _generate(
        self,
        messages: list[dict[str, str]],
        policy: PromptPolicy,
    ) -> tuple[PromptResult, PromptGenerationMetadata]:
        started = monotonic()
        budget = _GenerationBudget.create(settings.prompt_timeout_seconds)
        response = self._call_llm(messages, budget)
        raw = response.get("content") or ""
        repaired = False
        usage = dict(response.get("usage") or {})
        try:
            result = PromptOutputDecoder.parse(raw)
        except ValueError:
            repair_messages = list(messages)
            repair_messages.extend(
                [
                    {"role": "assistant", "content": raw[:12000]},
                    {
                        "role": "user",
                        "content": (
                            "上一条响应未满足 JSON 契约。不要重新分析输入，只修复格式和缺失结构，"
                            "并只返回完整的 JSON 对象。缺少且无法从输入确认的内容写入 checks 或 assumptions。"
                        ),
                    },
                ]
            )
            try:
                repair_response = self._call_llm(repair_messages, budget)
                raw = repair_response.get("content") or ""
                result = PromptOutputDecoder.parse(raw)
                repaired = True
                usage = self._merge_usage(usage, repair_response.get("usage") or {})
            except PromptLLMError:
                raise
            except ValueError as repair_error:
                raise PromptOutputRepairError(
                    "模型输出经过一次格式修复后仍不符合结构化契约"
                ) from repair_error

        elapsed_ms = int((monotonic() - started) * 1000)
        return result, PromptGenerationMetadata(
            elapsed_ms=elapsed_ms,
            model=str(getattr(self._llm or get_llm(), "model", "unknown")),
            prompt_id=policy.prompt_id,
            prompt_version=policy.prompt_version,
            schema_version=policy.schema_version,
            llm_attempts=budget.attempts,
            format_repaired=repaired,
            candidate_mapping_count=len(result.term_mappings),
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
            total_tokens=usage.get("total_tokens"),
        )

    def _call_llm(
        self,
        messages: list[dict[str, str]],
        budget: _GenerationBudget,
    ) -> PromptLLMResponse:
        client = self._llm or get_llm()
        try:
            timeout_seconds = budget.next_timeout()
            response = client.chat(
                messages,
                response_format={"type": "json_object"},
                timeout_seconds=timeout_seconds,
                max_tokens=settings.prompt_max_output_tokens,
            )
        except TimeoutError as error:
            raise PromptLLMTimeout("模型服务响应超时，请稍后重试") from error
        except Exception as error:
            if "timeout" in type(error).__name__.lower() or "timed out" in str(error).lower():
                raise PromptLLMTimeout("模型服务响应超时，请稍后重试") from error
            raise PromptLLMError("模型服务调用失败，请检查模型配置后重试") from error
        content = response.get("content") if isinstance(response, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise PromptLLMEmptyResponse("模型服务返回空内容，请重试")
        return response

    @staticmethod
    def _merge_usage(left: dict[str, int], right: dict[str, int]) -> dict[str, int]:
        keys = {"prompt_tokens", "completion_tokens", "total_tokens"}
        return {key: int(left.get(key, 0)) + int(right.get(key, 0)) for key in keys if key in left or key in right}

    def _get_initial_request(
        self,
        idempotency_key: str | None,
    ) -> tuple[PromptResult, PromptGenerationMetadata, PromptSession] | None:
        if not idempotency_key:
            return None
        now = monotonic()
        with self._initial_request_lock:
            ttl = settings.prompt_session_ttl_seconds
            for key, (created_at, *_rest) in list(self._initial_requests.items()):
                if now - created_at > ttl:
                    del self._initial_requests[key]
            cached = self._initial_requests.get(idempotency_key)
            return cached[1:] if cached else None

    def _store_initial_request(
        self,
        idempotency_key: str | None,
        result: PromptResult,
        metadata: PromptGenerationMetadata,
        session: PromptSession,
    ) -> None:
        if not idempotency_key:
            return
        with self._initial_request_lock:
            # 缓存初次响应的快照，避免后续轮次推进时修改已缓存的会话对象。
            self._initial_requests[idempotency_key] = (
                monotonic(),
                result,
                metadata,
                deepcopy(session),
            )
            max_entries = settings.prompt_session_max_count
            while len(self._initial_requests) > max_entries:
                oldest = min(self._initial_requests, key=lambda key: self._initial_requests[key][0])
                del self._initial_requests[oldest]

    @staticmethod
    def _sanitize(value: str, field_name: str) -> str:
        clean = "".join(
            char if char in "\n\r\t" or ord(char) >= 32 else " "
            for char in value
        ).strip()
        min_chars = settings.prompt_min_input_chars if field_name == "content" else 1
        max_chars = settings.prompt_max_input_chars if field_name == "content" else 4000
        if len(clean) < min_chars or len(clean) > max_chars:
            raise PromptInputError(
                f"{field_name} 长度必须在 {min_chars}～{max_chars} 个字符之间"
            )
        return clean
