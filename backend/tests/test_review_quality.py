import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from app.engine.finding_gate import filter_findings
from app.engine.errors import format_user_error
from app.engine.llm import LLMProvider
from app.engine.reviewers.base import ReviewerContext, ReviewerOutputError
from app.engine.reviewers.style import StyleReviewer
from app.engine.scope import build_review_plan, classify_files
from app.engine.validators.release import validate_release_manifest
from app.engine.nodes import generate_report_node, reflection_node, run_reviews_node
from app.engine.workflow import run_workflow


class ReviewQualityTests(unittest.TestCase):
    def test_insufficient_balance_error_is_user_friendly(self):
        raw = "Error code: 402 - {'error': {'message': 'Insufficient Balance', 'type': 'unknown_error'}}"

        self.assertEqual(
            format_user_error(raw),
            "模型服务余额不足，请补充余额或更换模型服务后重试。",
        )

    def test_reviewer_balance_error_is_normalised_in_report_state(self):
        class BalanceReviewer:
            def review(self, _context):
                raise RuntimeError(
                    "Error code: 402 - {'error': {'message': 'Insufficient Balance'}}"
                )

        state = {
            "review_plan": ["style_reviewer"],
            "validator_findings": [],
            "checks": [],
            "workflow_errors": [],
            "reviewer_outputs": {},
            "changed_files": ["src/app.py"],
            "raw_diff": "@@ -1,0 +1,1 @@\n+value = 1\n",
            "findings": [],
            "quality_metrics": {},
            "file_context_cache": {},
            "_log_hook": None,
        }

        import app.engine.reviewers as reviewers

        original_registry = dict(reviewers.REVIEWER_REGISTRY)
        reviewers.REVIEWER_REGISTRY.clear()
        reviewers.REVIEWER_REGISTRY.update({"style_reviewer": BalanceReviewer()})
        try:
            run_reviews_node(state)
        finally:
            reviewers.REVIEWER_REGISTRY.clear()
            reviewers.REVIEWER_REGISTRY.update(original_registry)

        self.assertEqual(
            state["checks"][0]["message"],
            "模型服务余额不足，请补充余额或更换模型服务后重试。",
        )
        self.assertEqual(
            state["reviewer_outputs"]["style_reviewer"]["error_message"],
            "模型服务余额不足，请补充余额或更换模型服务后重试。",
        )

    def test_release_manifest_does_not_activate_generic_reviewers(self):
        scopes = classify_files(["update/windows.json"])

        self.assertEqual(scopes["update/windows.json"].kind, "release_manifest")
        self.assertEqual(build_review_plan(["update/windows.json"], ""), [])

    def test_mixed_change_keeps_source_review_and_skips_manifest_style_review(self):
        changed = ["update/windows.json", "src/app.ts"]
        scopes = classify_files(changed)

        self.assertEqual(scopes["src/app.ts"].kind, "source_code")
        self.assertEqual(build_review_plan(changed, ""), ["style_reviewer"])

    def test_release_manifest_validator_reports_only_deterministic_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "windows.json"
            path.write_text(
                json.dumps(
                    {
                        "version": "0.4.2",
                        "download_url": "https://example.test/v0.4.2/app.exe",
                        "sha256": "invalid",
                        "release_notes": "notes",
                        "release_url": "https://example.test/releases/v0.4.2",
                        "release_date": "2026-07-29T12:21:46Z",
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            result = validate_release_manifest(str(path), set(), tmp)

        self.assertEqual(len(result.findings), 1)
        self.assertIn("SHA256", result.findings[0]["title"])
        self.assertEqual(result.findings[0]["evidence_type"], "static_check")

    def test_finding_gate_rejects_uncertain_unlocated_and_unrelated_findings(self):
        diff = """diff --git a/src/app.py b/src/app.py
--- a/src/app.py
+++ b/src/app.py
@@ -1,2 +1,3 @@
+value = 1
 value += 1
"""
        findings = [
            {
                "severity": "low",
                "file": "src/app.py",
                "line": 1,
                "title": "存在具体问题",
                "reason": "该变更会导致具体行为错误。",
                "suggestion": "改为使用明确的初始化逻辑。",
            },
            {
                "severity": "low",
                "file": "src/app.py",
                "line": 0,
                "title": "无法验证外部资产",
                "reason": "无法确认该值是否正确。",
                "suggestion": "建议检查发布页面。",
            },
            {
                "severity": "low",
                "file": "README.md",
                "line": 1,
                "title": "无关文件问题",
                "reason": "该问题与当前源码变更无关。",
                "suggestion": "调整文档。",
            },
        ]

        accepted = filter_findings(findings, ["src/app.py"], diff)

        self.assertEqual(len(accepted), 1)
        self.assertEqual(accepted[0]["title"], "存在具体问题")

    def test_finding_gate_keeps_changed_file_context_findings_for_review(self):
        diff = """diff --git a/src/app.py b/src/app.py
--- a/src/app.py
+++ b/src/app.py
@@ -1,2 +1,3 @@
+value = 1
 value += 1
"""
        finding = {
            "severity": "low",
            "file": "src/app.py",
            "line": 2,
            "title": "变更文件中的上下文问题",
            "reason": "问题位于变更文件的关联上下文中。",
            "suggestion": "复核该处与变更的关系。",
        }

        accepted = filter_findings([finding], ["src/app.py"], diff)

        self.assertEqual(len(accepted), 1)
        self.assertEqual(accepted[0]["evidence_type"], "reviewer_context")

    def test_finding_gate_merges_same_location_similar_titles(self):
        diff = """diff --git a/src/app.py b/src/app.py
--- a/src/app.py
+++ b/src/app.py
@@ -1,2 +1,3 @@
+value = 1
 value += 1
"""
        findings = [
            {
                "severity": "high",
                "file": "src/app.py",
                "line": 1,
                "title": "OAuth 回调缺少 state 参数校验",
                "reason": "回调未校验 state，存在 CSRF 风险。",
                "suggestion": "校验 state 参数。",
            },
            {
                "severity": "medium",
                "file": "src/app.py",
                "line": 1,
                "title": "OAuth 回调缺少状态参数验证",
                "reason": "缺少 state 校验。",
                "suggestion": "校验 state。",
            },
            {
                "severity": "medium",
                "file": "src/app.py",
                "line": 1,
                "title": "OAuth 回调缺少错误处理",
                "reason": "错误被静默吞掉。",
                "suggestion": "补充错误处理。",
            },
        ]

        accepted = filter_findings(findings, ["src/app.py"], diff)

        # 同位置语义重复的两条只保留一条，不同问题保留。
        self.assertEqual(len(accepted), 2)
        titles = {f["title"] for f in accepted}
        self.assertIn("OAuth 回调缺少 state 参数校验", titles)
        self.assertIn("OAuth 回调缺少错误处理", titles)

    def test_finding_gate_merges_normalised_title_duplicates(self):
        diff = """diff --git a/src/app.py b/src/app.py
--- a/src/app.py
+++ b/src/app.py
@@ -1,2 +1,3 @@
+value = 1
 value += 1
"""
        findings = [
            {
                "severity": "low",
                "file": "src/app.py",
                "line": 1,
                "title": "HTTP response body size limit is hardcoded",
                "reason": "原因一",
                "suggestion": "建议一",
            },
            {
                "severity": "low",
                "file": "src/app.py",
                "line": 1,
                "title": "HTTP response body size limit hardcoded!",
                "reason": "原因二",
                "suggestion": "建议二",
            },
        ]

        accepted = filter_findings(findings, ["src/app.py"], diff)

        self.assertEqual(len(accepted), 1)

    def test_finding_gate_keeps_distinct_problems_at_same_location(self):
        diff = """diff --git a/src/app.py b/src/app.py
--- a/src/app.py
+++ b/src/app.py
@@ -1,2 +1,3 @@
+value = 1
 value += 1
"""
        findings = [
            {
                "severity": "low",
                "file": "src/app.py",
                "line": 1,
                "title": "OAuth 回调缺少 state 参数校验",
                "reason": "原因一",
                "suggestion": "建议一",
            },
            {
                "severity": "low",
                "file": "src/app.py",
                "line": 1,
                "title": "Token refresh failure returns original error",
                "reason": "原因二",
                "suggestion": "建议二",
            },
        ]

        accepted = filter_findings(findings, ["src/app.py"], diff)

        self.assertEqual(len(accepted), 2)

    def test_release_only_commit_produces_checks_without_llm_findings(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "update").mkdir()
            (repo / "update" / "windows.json").write_text(
                json.dumps(
                    {
                        "version": "0.4.2",
                        "download_url": "https://example.test/v0.4.2/app.exe",
                        "sha256": "a" * 64,
                        "release_notes": "notes",
                        "release_url": "https://example.test/releases/v0.4.2",
                        "release_date": "2026-07-29T12:21:46Z",
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            self._git(repo, "init")
            self._git(repo, "add", ".")
            self._git(
                repo,
                "-c",
                "user.name=Test",
                "-c",
                "user.email=test@example.com",
                "commit",
                "-m",
                "initial",
            )

            (repo / "update" / "windows.json").write_text(
                (repo / "update" / "windows.json")
                .read_text(encoding="utf-8")
                .replace("0.4.2", "0.4.3"),
                encoding="utf-8",
            )
            self._git(repo, "add", ".")
            self._git(
                repo,
                "-c",
                "user.name=Test",
                "-c",
                "user.email=test@example.com",
                "commit",
                "-m",
                "release manifest",
            )
            commit = self._git(repo, "rev-parse", "HEAD")

            report = run_workflow(
                str(repo),
                review_type="local",
                commit_hash=commit,
            )

        self.assertEqual(report["findings"], [])
        self.assertEqual(report["stats"]["total_findings"], 0)
        self.assertEqual(report["quality"]["candidate_findings"], 0)
        self.assertEqual(report["quality"]["filtered_findings"], 0)
        self.assertTrue(any(check["name"] == "release_artifact_sha256" for check in report["checks"]))
        self.assertEqual(report["changes"]["changed_files"], ["update/windows.json"])
        self.assertEqual(report["changes"]["head_revision"], commit)
        self.assertIn("windows.json", report["changes"]["diff"])

    def test_invalid_reviewer_output_is_visible_without_blocking_report(self):
        class BrokenReviewer:
            def review(self, _context):
                raise ReviewerOutputError("输出不是有效的 Finding JSON")

        state = {
            "review_plan": ["style_reviewer"],
            "validator_findings": [],
            "checks": [],
            "workflow_errors": [],
            "changed_files": ["src/app.py"],
            "raw_diff": "@@ -1,0 +1,1 @@\n+value = 1\n",
            "findings": [],
            "quality_metrics": {},
            "reflection_round": 0,
            "context_candidates": [],
            "file_context_cache": {},
            "_log_hook": None,
        }

        import app.engine.reviewers as reviewers

        original_registry = dict(reviewers.REVIEWER_REGISTRY)
        reviewers.REVIEWER_REGISTRY.clear()
        reviewers.REVIEWER_REGISTRY.update({"style_reviewer": BrokenReviewer()})
        try:
            run_reviews_node(state)
        finally:
            reviewers.REVIEWER_REGISTRY.clear()
            reviewers.REVIEWER_REGISTRY.update(original_registry)

        report_state = generate_report_node(reflection_node(state))

        self.assertEqual(report_state["findings"], [])
        self.assertTrue(report_state["report"])
        self.assertEqual(report_state["report"]["review_status"], "degraded")
        self.assertEqual(report_state["report"]["summary"], "本次审查发现 0 个问题")

    def test_context_findings_do_not_make_report_degraded(self):
        state = {
            "findings": [],
            "workflow_errors": [],
            "quality_metrics": {
                "candidate_findings": 2,
                "accepted_findings": 2,
                "filtered_findings": 0,
                "reviewer_context_findings": 2,
                "truncated_outputs": 0,
            },
            "checks": [],
        }

        report_state = generate_report_node(state)

        self.assertEqual(report_state["report"]["review_status"], "complete")
        self.assertEqual(report_state["report"]["summary"], "本次审查发现 0 个问题")

    def test_invalid_reviewer_json_is_not_silently_treated_as_clean_review(self):
        with self.assertRaises(ReviewerOutputError):
            StyleReviewer()._parse_findings("这不是 JSON")

    def test_embedded_scalar_array_is_not_treated_as_empty_findings(self):
        with self.assertRaises(ReviewerOutputError):
            StyleReviewer()._parse_findings(
                'analysis: `"".split("-")` returns [""]。Actually,'
            )

    def test_reviewer_parser_accepts_common_json_wrappers(self):
        reviewer = StyleReviewer()

        self.assertEqual(reviewer._parse_findings("```JSON\n[]\n```"), [])
        self.assertEqual(
            reviewer._parse_findings("审查结果：{\"findings\": []}"),
            [],
        )

    def test_reviewer_parser_normalises_json_scalar_types(self):
        reviewer = StyleReviewer()

        findings = reviewer._parse_findings(
            '{"findings":[{"severity":"LOW","file":"src/app.py",'
            '"line":"1","title":"标题","reason":"原因","suggestion":"建议"}]}'
        )

        self.assertEqual(findings[0]["severity"], "low")
        self.assertEqual(findings[0]["line"], 1)

    def test_filtered_candidates_do_not_make_report_degraded(self):
        state = {
            "findings": [],
            "workflow_errors": [],
            "quality_metrics": {
                "candidate_findings": 3,
                "accepted_findings": 0,
                "filtered_findings": 3,
            },
            "checks": [],
        }

        report_state = generate_report_node(state)

        self.assertEqual(report_state["report"]["review_status"], "complete")
        self.assertEqual(report_state["report"]["summary"], "本次审查发现 0 个问题")

    def test_tool_call_review_always_closes_with_structured_json(self):
        provider = object.__new__(LLMProvider)
        calls = []
        responses = iter(
            [
                {
                    "content": "分析过程很长，但这不是最终结果。",
                    "tool_calls": [],
                    "finish_reason": "stop",
                },
                {
                    "content": '{"findings":[]}',
                    "tool_calls": [],
                    "finish_reason": "stop",
                },
            ]
        )

        def fake_chat(messages, **kwargs):
            calls.append({"messages": messages, "kwargs": kwargs})
            return next(responses)

        provider.chat = fake_chat
        result = provider.chat_with_tools(
            [{"role": "user", "content": "review"}],
            tools=[],
            tool_handlers={},
        )

        self.assertEqual(result, '{"findings":[]}')
        self.assertEqual(calls[1]["kwargs"]["response_format"], {"type": "json_object"})
        self.assertIn("分析过程很长", calls[1]["messages"][-2]["content"])

    def test_tool_call_review_recovers_from_empty_forced_final_response(self):
        provider = object.__new__(LLMProvider)
        responses = iter(
            [
                {
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "name": "ReadFile",
                            "arguments": {"file_path": "src/app.py"},
                        }
                    ],
                },
                {"content": None, "tool_calls": []},
                {"content": "[]", "tool_calls": []},
            ]
        )

        def fake_chat(_messages, tools=None, **_kwargs):
            return next(responses)

        provider.chat = fake_chat
        result = provider.chat_with_tools(
            [{"role": "user", "content": "review"}],
            tools=[],
            tool_handlers={"ReadFile": lambda **_: "content"},
            max_rounds=1,
        )

        self.assertEqual(result, "[]")

    def test_reviewer_repairs_non_json_model_output_before_failing(self):
        class RepairingLLM:
            def __init__(self):
                self.repair_messages = []

            def chat_with_tools(self, *_args, **_kwargs):
                return "审查结果：```json\n[{'severity': 'low'}]\n```"

            def chat(self, messages, **_kwargs):
                self.repair_messages.append(messages)
                return {
                    "content": (
                        '{"findings":[{"severity":"low","file":"src/app.py",'
                        '"line":1,"title":"示例","reason":"原因","suggestion":"建议"}]}'
                    ),
                    "tool_calls": [],
                }

        reviewer = StyleReviewer()
        reviewer._llm = RepairingLLM()

        findings = reviewer.review(ReviewerContext(diff="diff"))

        self.assertEqual(findings[0]["file"], "src/app.py")
        self.assertEqual(len(reviewer._llm.repair_messages), 1)

    def test_reviewer_does_not_turn_unverifiable_output_into_clean_review(self):
        class EmptyRepairLLM:
            def chat_with_tools(self, *_args, **_kwargs):
                return "模型分析被截断，无法确认结果"

            def chat(self, _messages, **_kwargs):
                return {"content": '{"findings":[]}', "tool_calls": []}

        reviewer = StyleReviewer()
        reviewer._llm = EmptyRepairLLM()

        with self.assertRaises(ReviewerOutputError):
            reviewer.review(ReviewerContext(diff="diff"))

    def test_truncated_reviewer_output_is_not_treated_as_clean_review(self):
        class TruncatedLLM:
            def chat_with_tools(self, *args, **kwargs):
                callback = kwargs.get("response_meta_hook")
                if callback:
                    callback({"finish_reason": "length"})
                return 'analysis: `"".split("-")` returns [""]。Actually,'

            def chat(self, _messages, **_kwargs):
                return {
                    "content": '{"findings":[]}',
                    "tool_calls": [],
                    "finish_reason": "stop",
                }

        reviewer = StyleReviewer()
        reviewer._llm = TruncatedLLM()

        with self.assertRaises(ReviewerOutputError):
            reviewer.review(ReviewerContext(diff="diff"))

    def test_truncated_reviewer_trace_is_degraded(self):
        class TruncatedReviewer:
            def review(self, context):
                context.output_hook("primary", 'analysis [""]。Actually,')
                context.output_metadata_hook("primary", {"finish_reason": "length"})
                raise ReviewerOutputError("output was truncated")

        state = {
            "review_plan": ["style_reviewer"],
            "validator_findings": [],
            "checks": [],
            "workflow_errors": [],
            "reviewer_outputs": {},
            "changed_files": ["src/app.py"],
            "raw_diff": "@@ -1,0 +1,1 @@\n+value = 1\n",
            "findings": [],
            "quality_metrics": {},
            "reflection_round": 0,
            "context_candidates": [],
            "file_context_cache": {},
            "_log_hook": None,
        }

        import app.engine.reviewers as reviewers

        original_registry = dict(reviewers.REVIEWER_REGISTRY)
        reviewers.REVIEWER_REGISTRY.clear()
        reviewers.REVIEWER_REGISTRY.update({"style_reviewer": TruncatedReviewer()})
        try:
            run_reviews_node(state)
        finally:
            reviewers.REVIEWER_REGISTRY.clear()
            reviewers.REVIEWER_REGISTRY.update(original_registry)

        report_state = generate_report_node(reflection_node(state))

        attempt = state["reviewer_outputs"]["style_reviewer"]["attempts"][0]
        self.assertEqual(attempt["finish_reason"], "length")
        self.assertTrue(attempt["truncated"])
        self.assertEqual(state["quality_metrics"]["truncated_outputs"], 1)
        self.assertEqual(report_state["report"]["review_status"], "degraded")

    def test_reviewer_captures_primary_output_for_report_trace(self):
        class TracedLLM:
            def chat_with_tools(self, *_args, **_kwargs):
                return '{"findings":[]}'

        outputs = []
        reviewer = StyleReviewer()
        reviewer._llm = TracedLLM()

        reviewer.review(
            ReviewerContext(
                diff="diff",
                output_hook=lambda stage, output: outputs.append((stage, output)),
            )
        )

        self.assertEqual(outputs, [("primary", '{"findings":[]}')])

    def test_report_preserves_reviewer_output_trace(self):
        state = {
            "findings": [],
            "workflow_errors": [],
            "quality_metrics": {},
            "checks": [],
            "reviewer_outputs": {
                "style_reviewer": {
                    "attempts": [
                        {"stage": "primary", "output": "{\"findings\":[]}", "truncated": False}
                    ],
                    "candidate_findings": [],
                    "error_message": None,
                }
            },
        }

        report_state = generate_report_node(state)

        self.assertIn("style_reviewer", report_state["report"]["reviewer_outputs"])

    @staticmethod
    def _git(repo: Path, *args: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(repo), *args],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()


if __name__ == "__main__":
    unittest.main()
