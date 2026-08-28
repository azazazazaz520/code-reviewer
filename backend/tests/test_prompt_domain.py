import json
import time
import unittest

from app.engine.prompt.exporters import export_issue, export_jira, export_markdown
from app.engine.prompt.mapping import suggest_term_mappings
from app.engine.prompt.output_decoder import PromptOutputDecoder
from app.engine.prompt.prompt_builder import build_prompt_messages
from app.engine.prompt.schemas import PromptMode, PromptOptimizeRequest, PromptPersona
from app.services.prompt_optimizer import PromptLLMEmptyResponse, PromptOptimizer, PromptOutputRepairError
from app.services.prompt_session import (
    PromptSessionContextTooLong,
    PromptSessionLimitReached,
    PromptSessionStore,
    PromptSessionVersionConflict,
)


VALID_RESULT = {
    "classification": {
        "type": "bug",
        "confidence": 0.82,
        "reason": "描述包含操作后未产生预期状态变化的现象",
    },
    "problem_phenomenon": "点击切换后界面仍显示原状态，刷新后状态恢复。",
    "technical_essence": "状态更新或初始化覆盖逻辑存在不一致。",
    "solution": ["检查状态更新链路", "补充刷新前后的回归测试"],
    "bug_view": "用户操作后状态未按预期保持，需定位状态写入和初始化时序。",
    "prd_view": "明确切换状态的持久化范围、刷新后的预期表现和验收条件。",
    "team_message": "切换状态未稳定保持，建议优先检查状态写入与初始化覆盖。",
    "term_mappings": [],
    "assumptions": [],
    "checks": ["尚未提供复现环境和浏览器版本"],
}


class FakeLLM:
    model = "test-model"

    def __init__(self, responses=None):
        self.responses = list(responses or [VALID_RESULT])
        self.calls = []

    def chat(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        response = self.responses.pop(0) if self.responses else VALID_RESULT
        if isinstance(response, Exception):
            raise response
        return {"content": json.dumps(response, ensure_ascii=False)}


class PromptDomainTests(unittest.TestCase):
    def test_input_schema_allows_short_non_empty_content_and_rejects_empty_or_invalid_values(self):
        with self.assertRaises(ValueError):
            PromptOptimizeRequest(content="")
        self.assertEqual(PromptOptimizeRequest(content="太短").content, "太短")
        with self.assertRaises(ValueError):
            PromptOptimizeRequest(content="太短", persona="mobile")

    def test_builtin_mapper_returns_candidates_without_replacing_input(self):
        content = "页面不够丝滑，点击后出现刷新后恢复"
        mappings = suggest_term_mappings(content)

        self.assertEqual([item["original"] for item in mappings], ["不够丝滑", "刷新后恢复"])
        self.assertNotIn("professional", content)

    def test_optimizer_returns_structured_result_and_non_sensitive_metadata(self):
        llm = FakeLLM()
        optimizer = PromptOptimizer(llm=llm)
        request = PromptOptimizeRequest(
            content="点击切换后看起来还是选中，刷新页面又恢复了",
            persona=PromptPersona.FRONTEND,
            mode=PromptMode.INSTANT,
        )

        result, metadata, session = optimizer.optimize(request)

        self.assertEqual(result.classification.type.value, "bug")
        self.assertIsNone(session)
        self.assertEqual(metadata.model, "test-model")
        self.assertNotIn(request.content, str(metadata))
        self.assertEqual(llm.calls[0][1]["response_format"], {"type": "json_object"})

    def test_prompt_builder_serializes_policy_and_mappings_as_data(self):
        messages = build_prompt_messages(
            "页面不够丝滑",
            PromptPersona.FRONTEND,
            suggest_term_mappings("页面不够丝滑"),
        )

        user_prompt = messages[1]["content"]
        self.assertIn('<prompt_policy>{"prompt_id": "devprompt-pro"', user_prompt)
        self.assertIn('<candidate_term_mappings>[{"original": "不够丝滑"', user_prompt)

    def test_output_decoder_rejects_duplicate_semantic_items(self):
        duplicate = dict(VALID_RESULT)
        duplicate["solution"] = ["检查状态写入链路", "检查状态写入链路"]

        with self.assertRaises(ValueError):
            PromptOutputDecoder.parse(json.dumps(duplicate, ensure_ascii=False))

    def test_review_context_is_checked_before_calling_llm(self):
        llm = FakeLLM()
        store = PromptSessionStore(ttl_seconds=60, max_sessions=10, max_context_chars=10)
        optimizer = PromptOptimizer(llm=llm, session_store=store)

        with self.assertRaises(PromptSessionContextTooLong):
            optimizer.optimize(
                PromptOptimizeRequest(content="内容", mode=PromptMode.REVIEW)
            )
        self.assertEqual(llm.calls, [])

    def test_context_failure_does_not_evict_existing_session(self):
        store = PromptSessionStore(ttl_seconds=60, max_sessions=1, max_context_chars=100)
        first = store.create(PromptMode.REVIEW, PromptPersona.GENERAL, [{"role": "user", "content": "ok"}], VALID_RESULT)

        with self.assertRaises(PromptSessionContextTooLong):
            store.create(
                PromptMode.REVIEW,
                PromptPersona.GENERAL,
                [{"role": "user", "content": "x" * 101}],
                VALID_RESULT,
            )
        self.assertEqual(store.get(first.session_id).session_id, first.session_id)

    def test_review_turn_is_idempotent_and_rejects_stale_turn(self):
        llm = FakeLLM()
        store = PromptSessionStore(ttl_seconds=60, max_sessions=10, max_context_chars=10000)
        optimizer = PromptOptimizer(llm=llm, session_store=store)
        _, _, session = optimizer.optimize(
            PromptOptimizeRequest(content="需要确认状态问题", mode=PromptMode.REVIEW)
        )
        assert session is not None

        first_result, first_metadata, first_session = optimizer.add_review_turn(
            session.session_id,
            "确认状态问题",
            expected_turn=1,
            idempotency_key="turn-1",
        )
        call_count = len(llm.calls)
        repeated_result, repeated_metadata, repeated_session = optimizer.add_review_turn(
            session.session_id,
            "不同文本也不应重复执行",
            expected_turn=1,
            idempotency_key="turn-1",
        )

        self.assertEqual(len(llm.calls), call_count)
        self.assertEqual(repeated_result, first_result)
        self.assertEqual(repeated_metadata, first_metadata)
        self.assertEqual(repeated_session.turn, first_session.turn)
        with self.assertRaises(PromptSessionVersionConflict):
            optimizer.add_review_turn(
                session.session_id,
                "过期轮次",
                expected_turn=1,
                idempotency_key="turn-2",
            )

    def test_review_session_allows_three_turns_and_hides_messages_from_status(self):
        llm = FakeLLM()
        store = PromptSessionStore(ttl_seconds=60, max_sessions=10, max_context_chars=10000)
        optimizer = PromptOptimizer(llm=llm, session_store=store)
        request = PromptOptimizeRequest(
            content="点击切换后看起来还是选中，刷新页面又恢复了",
            mode=PromptMode.REVIEW,
        )

        _, _, session = optimizer.optimize(request)
        assert session is not None
        _, _, session = optimizer.add_review_turn(session.session_id, "确认这是前端状态问题")
        _, _, session = optimizer.add_review_turn(session.session_id, "补充刷新后复现")

        self.assertEqual(session.turn, 3)
        with self.assertRaises(PromptSessionLimitReached):
            optimizer.add_review_turn(session.session_id, "再补充一轮")
        self.assertTrue(session.messages)
        self.assertNotIn("messages", session.latest_result.model_dump())

    def test_invalid_output_is_repaired_once_and_failed_repair_is_explicit(self):
        llm = FakeLLM([{"unexpected": True}, {"unexpected": True}])
        optimizer = PromptOptimizer(llm=llm)

        with self.assertRaises(PromptOutputRepairError):
            optimizer.optimize(
                PromptOptimizeRequest(content="这是一段足够长的需求描述，用于验证输出契约修复失败")
            )
        self.assertEqual(len(llm.calls), 2)

    def test_output_repair_uses_one_total_timeout_budget(self):
        class TimedRepairLLM(FakeLLM):
            def chat(self, messages, **kwargs):
                if not self.calls:
                    time.sleep(0.01)
                return super().chat(messages, **kwargs)

        llm = TimedRepairLLM([{"unexpected": True}, VALID_RESULT])
        result, metadata, _ = PromptOptimizer(llm=llm).optimize(
            PromptOptimizeRequest(content="这是一段用于验证总超时预算的需求描述")
        )

        self.assertEqual(result.classification.type.value, "bug")
        self.assertEqual(metadata.llm_attempts, 2)
        self.assertTrue(metadata.format_repaired)
        self.assertLess(
            llm.calls[1][1]["timeout_seconds"],
            llm.calls[0][1]["timeout_seconds"],
        )

    def test_empty_llm_output_has_a_distinct_error(self):
        class EmptyLLM(FakeLLM):
            def chat(self, _messages, **_kwargs):
                return {"content": ""}

        with self.assertRaises(PromptLLMEmptyResponse):
            PromptOptimizer(llm=EmptyLLM()).optimize(
                PromptOptimizeRequest(content="这是一段足够长的需求描述，用于验证空响应错误码")
            )

    def test_exporters_are_deterministic_and_do_not_call_llm(self):
        markdown = export_markdown(VALID_RESULT)
        jira = export_jira(VALID_RESULT)
        issue = export_issue(VALID_RESULT)

        self.assertIn("## 问题现象", markdown)
        self.assertIn("h2. 解决方案", jira)
        self.assertIn("## 实施清单", issue)
        self.assertEqual(markdown, export_markdown(VALID_RESULT))


if __name__ == "__main__":
    unittest.main()
