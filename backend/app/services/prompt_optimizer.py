from __future__ import annotations

from datetime import UTC
import json
import re
from time import monotonic
from typing import Any

from pydantic import ValidationError

from app.config import settings
from app.engine.llm import LLMProvider, get_llm
from app.engine.prompt.mapping import suggest_term_mappings
from app.engine.prompt.prompt_builder import build_prompt_messages
from app.engine.prompt.schemas import (
    PromptMode,
    PromptOptimizeRequest,
    PromptPersona,
    PromptResult,
)
from app.services.prompt_session import (
    PromptSession,
    PromptSessionStore,
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


class PromptOptimizer:
    def __init__(
        self,
        llm: LLMProvider | Any | None = None,
        session_store: PromptSessionStore | None = None,
    ) -> None:
        self._llm = llm
        self.sessions = session_store or PromptSessionStore(
            ttl_seconds=settings.prompt_session_ttl_seconds,
            max_sessions=settings.prompt_session_max_count,
            max_context_chars=settings.prompt_session_max_context_chars,
        )

    def optimize(self, request: PromptOptimizeRequest) -> tuple[PromptResult, dict[str, int | str], PromptSession | None]:
        content = self._sanitize(request.content, "content")
        mappings = suggest_term_mappings(content) if request.glossary_enabled else []
        messages = build_prompt_messages(content, request.persona, mappings)
        result, metadata = self._generate(messages)
        session = None
        if request.mode == PromptMode.REVIEW:
            session_messages = messages + [
                {"role": "assistant", "content": result.model_dump_json(ensure_ascii=False)},
            ]
            session = self.sessions.create(request.mode, request.persona, session_messages, result)
            metadata["turn"] = session.turn
        else:
            metadata["turn"] = 1
        return result, metadata, session

    def add_review_turn(
        self,
        session_id: str,
        feedback: str,
    ) -> tuple[PromptResult, dict[str, int | str], PromptSession]:
        session = self.sessions.get(session_id)
        if session.turn >= session.max_turns:
            from app.services.prompt_session import PromptSessionLimitReached

            raise PromptSessionLimitReached("审查会话最多支持 3 轮，请重新生成")
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
        result, metadata = self._generate(messages)
        updated = self.sessions.advance(
            session_id,
            messages + [{"role": "assistant", "content": result.model_dump_json(ensure_ascii=False)}],
            result,
        )
        metadata["turn"] = updated.turn
        return result, metadata, updated

    def _generate(self, messages: list[dict[str, str]]) -> tuple[PromptResult, dict[str, int | str]]:
        started = monotonic()
        raw = self._call_llm(messages)
        repaired = 0
        try:
            result = self._parse_result(raw)
        except (ValueError, ValidationError) as parse_error:
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
                raw = self._call_llm(repair_messages)
                result = self._parse_result(raw)
                repaired = 1
            except Exception as repair_error:
                raise PromptOutputRepairError(
                    "模型输出经过一次格式修复后仍不符合结构化契约"
                ) from repair_error

        elapsed_ms = int((monotonic() - started) * 1000)
        return result, {
            "elapsed_ms": elapsed_ms,
            "model": str(getattr(self._llm or get_llm(), "model", "unknown")),
            "format_repaired": repaired,
            "candidate_mapping_count": len(result.term_mappings),
        }

    def _call_llm(self, messages: list[dict[str, str]]) -> str:
        client = self._llm or get_llm()
        try:
            response = client.chat(
                messages,
                response_format={"type": "json_object"},
                timeout_seconds=settings.prompt_timeout_seconds,
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
        return content

    @staticmethod
    def _parse_result(raw: str) -> PromptResult:
        text = raw.strip()
        candidates = [text]
        candidates.extend(
            match.group(1)
            for match in re.finditer(r"```(?:json)?\s*(.*?)```", text, re.IGNORECASE | re.DOTALL)
        )
        decoder = json.JSONDecoder()
        for candidate in candidates:
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict):
                    return PromptResult.model_validate(parsed)
            except (json.JSONDecodeError, ValidationError):
                pass
            start = candidate.find("{")
            while start >= 0:
                try:
                    parsed, _ = decoder.raw_decode(candidate[start:])
                    if isinstance(parsed, dict):
                        return PromptResult.model_validate(parsed)
                except (json.JSONDecodeError, ValidationError):
                    pass
                start = candidate.find("{", start + 1)
        raise ValueError("模型输出无法解析为 PromptResult")

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
