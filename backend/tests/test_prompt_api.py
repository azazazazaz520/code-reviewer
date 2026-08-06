import json
import unittest

from fastapi.testclient import TestClient

from app.api import prompts as prompts_api
from app.engine.prompt.schemas import PromptOptimizeRequest
from app.main import app
from app.services.prompt_optimizer import PromptOptimizer


class FakePromptLLM:
    model = "api-test-model"

    def chat(self, _messages, **_kwargs):
        return {
            "content": json.dumps(
                {
                    "classification": {"type": "feature", "confidence": 0.7, "reason": "输入描述了新增能力"},
                    "problem_phenomenon": "当前能力尚未提供。",
                    "technical_essence": "需要新增一个独立的结构化处理流程。",
                    "solution": ["补充接口", "增加回归测试"],
                    "bug_view": "不适用，当前输入更接近新增能力。",
                    "prd_view": "明确输入、输出和验收条件。",
                    "team_message": "需要补充结构化需求处理能力。",
                    "term_mappings": [],
                    "assumptions": [],
                    "checks": [],
                },
                ensure_ascii=False,
            )
        }


class PromptApiTests(unittest.TestCase):
    def test_optimize_and_review_session_endpoints(self):
        original = prompts_api.optimizer
        prompts_api.optimizer = PromptOptimizer(llm=FakePromptLLM())
        try:
            with TestClient(app) as client:
                response = client.post(
                    "/api/prompts/optimize",
                    json={
                        "content": "新增一个结构化需求工作区，支持研发沟通和本地导出",
                        "mode": "review",
                    },
                )
                self.assertEqual(response.status_code, 200)
                body = response.json()
                self.assertEqual(body["turn"], 1)
                self.assertIsNotNone(body["session_id"])
                self.assertIn("team_message", body["result"])

                status = client.get(f"/api/prompts/sessions/{body['session_id']}")
                self.assertEqual(status.status_code, 200)
                self.assertNotIn("messages", status.json())

                turn = client.post(
                    f"/api/prompts/sessions/{body['session_id']}/turns",
                    json={"feedback": "确认需要保留本地导出"},
                )
                self.assertEqual(turn.status_code, 200)
                self.assertEqual(turn.json()["turn"], 2)
        finally:
            prompts_api.optimizer = original

    def test_invalid_input_and_unknown_session_have_explicit_errors(self):
        with TestClient(app) as client:
            invalid = client.post("/api/prompts/optimize", json={"content": ""})
            self.assertEqual(invalid.status_code, 422)

            unknown = client.get("/api/prompts/sessions/not-found")
            self.assertEqual(unknown.status_code, 404)
            self.assertEqual(unknown.json()["detail"]["code"], "prompt_session_not_found")


if __name__ == "__main__":
    unittest.main()
