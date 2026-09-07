import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from app.config import settings
from app.engine.finding_gate import filter_findings
from app.engine.context import (
    ContextBudget,
    REVIEW_CONTEXT_HARD_MAX_CHARS,
    REVIEW_CONTEXT_HARD_MAX_FILES,
    REVIEW_DIFF_BATCH_CHARS,
    select_reviewer_context_with_metadata,
    split_diff_batches,
)
from app.engine.coverage import initial_coverage, update_coverage
from app.engine.errors import format_user_error
from app.engine.llm import LLMProvider
from app.engine.reviewers.base import BaseReviewer, ReviewerContext, ReviewerOutputError
from app.engine.reviewers.style import StyleReviewer
from app.engine.tools.context import ApprovedContextRef, TaskToolCache, TaskToolContext
from app.engine.scope import build_review_plan, classify_files
from app.engine.validators.release import validate_release_manifest
from app.engine.nodes import generate_report_node, run_reviews_node
from app.engine.workflow import run_workflow


class ReviewQualityTests(unittest.TestCase):
    def test_insufficient_balance_error_is_user_friendly(self):
        raw = "Error code: 402 - {'error': {'message': 'Insufficient Balance', 'type': 'unknown_error'}}"

        self.assertEqual(
            format_user_error(raw),
            "模型服务余额不足，请补充余额或更换模型服务后重试。",
        )

    def test_related_context_limit_does_not_count_as_critical_truncation(self):
        with mock.patch.object(settings, "review_context_max_files", 1), mock.patch.object(
            settings, "review_context_max_chars", 100
        ):
            selection = select_reviewer_context_with_metadata(
                {"src/changed.py": "x" * 20, "src/related.py": "y" * 20},
                ["src/changed.py"],
                "style_reviewer",
            )

        self.assertEqual(selection.truncated_inputs, 0)
        self.assertEqual(len(selection.context_limit_events), 1)

    def test_context_budget_clamps_external_override(self):
        source = {
            f"src/{index}.py": "x" * 4_000
            for index in range(REVIEW_CONTEXT_HARD_MAX_FILES + 5)
        }
        with mock.patch.object(settings, "review_context_max_files", 500), mock.patch.object(
            settings, "review_context_max_chars", 2_000_000
        ):
            selection = select_reviewer_context_with_metadata(
                source,
                [],
                "style_reviewer",
            )

        self.assertLessEqual(len(selection.files), REVIEW_CONTEXT_HARD_MAX_FILES)
        self.assertLessEqual(
            sum(len(content) for content in selection.files.values()),
            REVIEW_CONTEXT_HARD_MAX_CHARS,
        )

    def test_reviewer_messages_keep_task_prefix_before_unit_diff(self):
        reviewer = StyleReviewer()
        common = {
            "revision": "rev-1",
            "task_changed_files": ["src/a.py", "src/b.py"],
            "shared_file_context": {"src/a.py": "value = 1\n"},
        }
        first_context = ReviewerContext(
            **common,
            changed_files=["src/a.py"],
            diff="+value = 2\n",
        )
        second_context = ReviewerContext(
            **common,
            changed_files=["src/a.py"],
            diff="+value = 3\n",
        )
        first = reviewer._build_messages(first_context)
        second = reviewer._build_messages(second_context)

        first_prefix = first[1]["content"].split("## 当前审查单元", 1)[0]
        second_prefix = second[1]["content"].split("## 当前审查单元", 1)[0]
        self.assertEqual(first_prefix, second_prefix)
        self.assertIn("revision: rev-1", first_prefix)
        self.assertIn("src/a.py", first_prefix)
        self.assertNotIn("+value = 2", first_prefix)
        self.assertNotIn("+value = 3", second_prefix)
        self.assertEqual(
            first_context.input_coverage["stable_prefix_hash"],
            second_context.input_coverage["stable_prefix_hash"],
        )
        self.assertNotEqual(
            first_context.input_coverage["dynamic_suffix_hash"],
            second_context.input_coverage["dynamic_suffix_hash"],
        )

    def test_reviewer_prompt_bounds_json_output_without_changing_token_budget(self):
        messages = StyleReviewer()._build_messages(
            ReviewerContext(
                diff="@@ -1,1 +1,1 @@\n-value = 0\n+value = 1\n",
                changed_files=["src/app.py"],
            )
        )

        system_prompt = messages[0]["content"]
        self.assertIn("每个审查批次最多返回 5 条最重要的 Finding", system_prompt)
        self.assertIn("title 不超过 80 个字符", system_prompt)
        self.assertIn("不能为了容纳更多条目而省略 JSON 的闭合结构", system_prompt)
        self.assertIn('根节点必须包含 findings 和 context_requests 数组', system_prompt)
        self.assertNotIn("严格返回 JSON 数组", system_prompt)

    def test_reviewer_records_each_provider_usage_response(self):
        class UsageReviewer(BaseReviewer):
            name = "usage_reviewer"
            system_prompt = "test"

        class FakeLLM:
            def chat(self, _messages, **_kwargs):
                return {
                    "content": '{"findings":[],"context_requests":[]}',
                    "usage": {
                        "prompt_tokens": 100,
                        "completion_tokens": 8,
                        "total_tokens": 108,
                        "prompt_cache_hit_tokens": 64,
                        "prompt_cache_miss_tokens": 36,
                    },
                }

        reviewer = UsageReviewer()
        reviewer._llm = FakeLLM()
        logs = []
        context = ReviewerContext(
            task_id="task-1",
            reviewer_name="usage_reviewer",
            input_coverage={"unit_id": "unit-1"},
            log_hook=lambda **entry: logs.append(entry),
        )

        self.assertEqual(reviewer.review(context), [])
        self.assertEqual(context.input_coverage["provider_requests"], 1)
        self.assertEqual(context.input_coverage["llm_prompt_tokens"], 100)
        self.assertEqual(context.input_coverage["llm_prompt_cache_hit_tokens"], 64)
        self.assertEqual(context.input_coverage["llm_prompt_cache_miss_tokens"], 36)
        self.assertEqual(
            [event["stage"] for event in context.input_coverage["llm_usage_events"]],
            ["review"],
        )
        self.assertEqual(
            context.input_coverage["llm_usage_events"][0]["task_id"],
            "task-1",
        )
        self.assertTrue(
            context.input_coverage["llm_usage_events"][0]["first_provider_request"]
        )
        self.assertEqual(
            context.input_coverage["llm_usage_events"][0]["session_scope"],
            "review_batch",
        )
        self.assertTrue(
            context.input_coverage["llm_usage_events"][0]["session_rebuilt"]
        )
        self.assertEqual(len(logs), 1)
        self.assertNotIn("value =", logs[0]["message"])

    def test_complete_json_is_not_repaired_when_provider_reports_length(self):
        class CompleteJsonLengthLLM:
            def __init__(self):
                self.calls = 0
                self.kwargs = []

            def chat(self, _messages, **kwargs):
                self.calls += 1
                self.kwargs.append(kwargs)
                return {
                    "content": (
                        '{"findings":[{"severity":"low","file":"src/app.py",'
                        '"line":1,"title":"完整结果","reason":"有证据",'
                        '"suggestion":"修复","evidence":"value = 1",'
                        '"impact":"maintainability"}],"context_requests":[]}'
                    ),
                    "finish_reason": "length",
                }

        reviewer = StyleReviewer()
        llm = CompleteJsonLengthLLM()
        reviewer._llm = llm
        metadata_updates = []
        context = ReviewerContext(
            diff="@@ -1,1 +1,1 @@\n-value = 0\n+value = 1\n",
            changed_files=["src/app.py"],
            output_metadata_hook=lambda stage, metadata: metadata_updates.append(
                (stage, metadata)
            ),
        )

        findings = reviewer.review(context)

        self.assertEqual(llm.calls, 1)
        self.assertEqual(llm.kwargs[0]["thinking"], "disabled")
        self.assertEqual(findings[0]["title"], "完整结果")
        self.assertIn(("review", {"truncated": False}), metadata_updates)

    def test_reviewer_messages_hide_snapshot_absolute_root(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            context = ReviewerContext(
                repo_root=temp_dir,
                revision="rev-1",
                changed_files=[str(Path(temp_dir) / "src" / "app.py")],
                file_context={str(Path(temp_dir) / "src" / "app.py"): "value = 1\n"},
                tool_context=TaskToolContext(
                    repo_root=temp_dir,
                    revision="rev-1",
                ),
            )

            messages = StyleReviewer()._build_messages(context)

        rendered = "\n".join(message["content"] for message in messages)
        self.assertNotIn(temp_dir, rendered)
        self.assertIn("src/app.py", rendered)

    def test_context_request_past_file_end_does_not_create_failure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            target = root / "src" / "settings.py"
            target.parent.mkdir()
            target.write_text("one\ntwo\nthree\n", encoding="utf-8")
            context = ReviewerContext(
                tool_context=TaskToolContext(
                    repo_root=temp_dir,
                    revision="rev-1",
                    approved_context_refs=(
                        ApprovedContextRef("src/settings.py", 1, 200),
                    ),
                )
            )

            rendered = BaseReviewer()._read_requested_context(
                context,
                [
                    {
                        "file": "src/settings.py",
                        "start_line": 1,
                        "end_line": 200,
                        "reason": "验证文件末尾边界",
                    }
                ],
            )

        self.assertIn("3|three", rendered)
        self.assertEqual(context.input_coverage["context_reads"], 1)
        self.assertEqual(context.input_coverage["context_request_failures"], 0)
        self.assertEqual(context.input_coverage["context_request_failure_events"], [])

    def test_diff_batches_preserve_all_content(self):
        diff = "@@ -1,1 +1,1 @@\n" + ("+value\n" * 2000)

        batches = split_diff_batches(diff)

        self.assertEqual("".join(batches), diff)
        self.assertTrue(all(len(batch) <= REVIEW_DIFF_BATCH_CHARS for batch in batches))

    def test_context_budget_rejects_non_positive_character_limit(self):
        with self.assertRaises(ValueError):
            ContextBudget(max_files=1, max_chars=0)
        with self.assertRaises(ValueError):
            split_diff_batches("", 0)
        with self.assertRaises(ValueError):
            split_diff_batches("content", -1)

    def test_partial_context_coverage_remains_incomplete(self):
        coverage = initial_coverage(
            ["src/a.py", "src/b.py"],
            "",
            database_status="ready",
            extraction_status="complete",
        )

        result = update_coverage(
            coverage,
            ["src/a.py", "src/b.py"],
            {"src/a.py": "value = 1\n"},
            "",
            database_status="ready",
            extraction_status="complete",
        )

        self.assertEqual(result["covered_files"], 1)
        self.assertEqual(result["uncovered_files"], ["src/b.py"])
        self.assertEqual(result["coverage_status"], "incomplete")

    def test_invalid_coverage_path_fails_closed(self):
        with self.assertRaises(ValueError):
            initial_coverage(["../outside.py"], "")

        with self.assertRaises(ValueError):
            update_coverage(
                initial_coverage([], ""),
                ["../outside.py"],
                {},
                "",
            )

    def test_finding_gate_caches_line_count_within_one_filter_pass(self):
        findings = [
            {
                "severity": "medium",
                "file": "src/app.py",
                "line": 1,
                "title": "行为边界错误",
                "reason": "变更后的行为违反约束。",
                "suggestion": "修正该行为。",
                "evidence": "value = 1",
                "impact": "behavior",
            },
            {
                "severity": "low",
                "file": "src/app.py",
                "line": 1,
                "title": "安全边界遗漏",
                "reason": "同一变更位置缺少安全约束。",
                "suggestion": "补充约束并增加测试。",
                "evidence": "value = 1",
                "impact": "security",
            },
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "src" / "app.py"
            source.parent.mkdir()
            source.write_text("value = 1\n", encoding="utf-8")

            with mock.patch(
                "app.engine.finding_gate.file_line_count",
                return_value=1,
            ) as line_count:
                accepted = filter_findings(
                    findings,
                    ["src/app.py"],
                    "@@ -1,0 +1,1 @@\n+value = 1\n",
                    repo_root=temp_dir,
                )

        self.assertEqual(len(accepted), 2)
        line_count.assert_called_once()

    def test_reviewer_performs_at_most_one_context_supplement(self):
        class ContextReviewer(BaseReviewer):
            name = "test_reviewer"
            system_prompt = "test"

        class FakeLLM:
            def __init__(self):
                self.calls = []

            def chat(self, _messages, **kwargs):
                self.calls.append(kwargs)
                if len(self.calls) == 1:
                    content = (
                        '{"findings":[],"context_requests":['
                        '{"file":"src/app.py","start_line":1,'
                        '"end_line":1,"reason":"确认赋值"}]}'
                    )
                else:
                    content = '{"findings":[],"context_requests":[]}'
                return {"content": content, "usage": {}}

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "src" / "app.py"
            path.parent.mkdir()
            path.write_text("value = 1\n", encoding="utf-8")
            context = ReviewerContext(
                tool_context=TaskToolContext(
                    repo_root=temp_dir,
                    revision="rev-1",
                    approved_context_refs=(ApprovedContextRef("src/app.py", 1, 1),),
                ),
                tool_cache=TaskToolCache(),
            )
            reviewer = ContextReviewer()
            reviewer._llm = FakeLLM()

            self.assertEqual(reviewer.review(context), [])

        self.assertEqual(len(reviewer._llm.calls), 2)
        self.assertEqual(context.input_coverage["context_requests"], 1)
        self.assertEqual(context.input_coverage["context_reads"], 1)
        self.assertEqual(context.input_coverage["context_cache_hits"], 0)
        self.assertEqual(reviewer._llm.calls[0]["thinking"], "disabled")
        self.assertEqual(reviewer._llm.calls[1]["thinking"], "disabled")

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
                "evidence": "value = 1",
                "impact": "behavior",
            },
            {
                "severity": "low",
                "file": "src/app.py",
                "line": 0,
                "title": "无法验证外部资产",
                "reason": "无法确认该值是否正确。",
                "suggestion": "建议检查发布页面。",
                "impact": "compatibility",
            },
            {
                "severity": "low",
                "file": "README.md",
                "line": 1,
                "title": "无关文件问题",
                "reason": "该问题与当前源码变更无关。",
                "suggestion": "调整文档。",
                "impact": "maintainability",
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
            "evidence": "value += 1",
            "impact": "behavior",
        }

        accepted = filter_findings([finding], ["src/app.py"], diff)

        self.assertEqual(len(accepted), 1)
        self.assertEqual(accepted[0]["evidence_type"], "reviewer_context")

    def test_finding_gate_strict_mode_keeps_only_current_diff_lines(self):
        diff = """diff --git a/src/app.py b/src/app.py
--- a/src/app.py
+++ b/src/app.py
@@ -1,2 +1,3 @@
+value = 1
 value += 1
"""
        base = {
            "severity": "low",
            "file": "src/app.py",
            "title": "问题",
            "reason": "当前变更会触发错误。",
            "suggestion": "修复当前变更。",
            "evidence": "value = 1",
            "impact": "behavior",
        }
        findings = [
            {**base, "line": 1},
            {**base, "line": 2, "title": "上下文问题", "evidence": "value += 1"},
        ]
        reasons = {}

        accepted = filter_findings(
            findings,
            ["src/app.py"],
            diff,
            require_changed_line=True,
            rejection_reasons=reasons,
        )

        self.assertEqual([finding["line"] for finding in accepted], [1])
        self.assertEqual(reasons["outside_current_diff"], 1)

    def test_finding_gate_validates_snapshot_file_and_line(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "src").mkdir()
            (root / "src" / "app.py").write_text("value = 1\n", encoding="utf-8")
            diff = "diff --git a/src/app.py b/src/app.py\n+++ b/src/app.py\n@@ -1,0 +1,1 @@\n+value = 1\n"
            reasons = {}
            finding = {
                "severity": "low",
                "file": "src/app.py",
                "line": 2,
                "title": "越过文件末尾",
                "reason": "原因",
                "suggestion": "建议",
                "evidence": "value = 1",
                "impact": "behavior",
            }

            accepted = filter_findings(
                [finding],
                ["src/app.py"],
                diff,
                repo_root=temp_dir,
                rejection_reasons=reasons,
            )

        self.assertEqual(accepted, [])
        self.assertEqual(reasons["line_out_of_range"], 1)

    def test_finding_gate_rejects_missing_or_generated_evidence(self):
        diff = "diff --git a/src/app.py b/src/app.py\n+++ b/src/app.py\n@@ -1,0 +1,1 @@\n+value = 1\n"
        base_finding = {
            "severity": "low",
            "file": "src/app.py",
            "line": 1,
            "title": "缺少具体证据",
            "reason": "原因",
            "suggestion": "建议",
            "impact": "behavior",
        }
        reasons = {}

        accepted = filter_findings(
            [base_finding], ["src/app.py"], diff, rejection_reasons=reasons
        )
        self.assertEqual(accepted, [])
        self.assertEqual(reasons["untrusted_evidence"], 1)

        generated = {**base_finding, "evidence": "审查快照定位到 src/app.py:1"}
        reasons = {}
        accepted = filter_findings(
            [generated], ["src/app.py"], diff, rejection_reasons=reasons
        )
        self.assertEqual(accepted, [])
        self.assertEqual(reasons["untrusted_evidence"], 1)

    def test_finding_gate_does_not_trust_model_declared_static_evidence(self):
        finding = {
            "severity": "low",
            "file": "src/app.py",
            "line": 0,
            "title": "未定位问题",
            "reason": "原因",
            "suggestion": "建议",
            "impact": "behavior",
            "evidence_type": "static_check",
            "evidence": "校验器确认文件级契约不满足",
        }

        reasons = {}
        accepted = filter_findings(
            [finding],
            ["src/app.py"],
            "",
            rejection_reasons=reasons,
        )

        self.assertEqual(accepted, [])
        self.assertEqual(reasons["line_out_of_range"], 1)

    def test_finding_gate_accepts_query_approved_related_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "src").mkdir()
            (root / "src" / "app.py").write_text("changed\n", encoding="utf-8")
            (root / "src" / "helper.py").write_text("one\ntwo\n", encoding="utf-8")
            finding = {
                "severity": "medium",
                "file": "src/helper.py",
                "line": 2,
                "title": "关联代码问题",
                "reason": "关联节点影响了该行行为。",
                "suggestion": "复核关联调用。",
                "evidence": "two",
                "impact": "behavior",
            }

            accepted = filter_findings(
                [finding],
                ["src/app.py"],
                "",
                repo_root=temp_dir,
                approved_context_refs=[
                    {
                        "file": "src/helper.py",
                        "start_line": 2,
                        "end_line": 2,
                        "source": "query_result",
                        "result_id": "db-1:result-1",
                        "database_id": "db-1",
                    }
                ],
            )

        self.assertEqual(len(accepted), 1)
        self.assertEqual(accepted[0]["evidence_type"], "reviewer_context")
        self.assertEqual(accepted[0]["evidence_refs"][0]["result_id"], "db-1:result-1")

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
                "evidence": "回调参数中未出现 state 校验",
                "impact": "security",
            },
            {
                "severity": "medium",
                "file": "src/app.py",
                "line": 1,
                "title": "OAuth 回调缺少状态参数验证",
                "reason": "缺少 state 校验。",
                "suggestion": "校验 state。",
                "evidence": "回调参数中未出现 state 校验",
                "impact": "security",
            },
            {
                "severity": "medium",
                "file": "src/app.py",
                "line": 1,
                "title": "OAuth 回调缺少错误处理",
                "reason": "错误被静默吞掉。",
                "suggestion": "补充错误处理。",
                "evidence": "异常路径直接返回原始响应",
                "impact": "behavior",
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
                "evidence": "body_limit = 1024",
                "impact": "security",
            },
            {
                "severity": "low",
                "file": "src/app.py",
                "line": 1,
                "title": "HTTP response body size limit hardcoded!",
                "reason": "原因二",
                "suggestion": "建议二",
                "evidence": "body_limit = 1024",
                "impact": "security",
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
                        "evidence": "state 未经过校验",
                        "impact": "security",
            },
            {
                "severity": "low",
                "file": "src/app.py",
                "line": 1,
                        "title": "Token refresh failure returns original error",
                        "reason": "原因二",
                        "suggestion": "建议二",
                        "evidence": "失败分支返回原始错误",
                        "impact": "security",
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

    def test_workflow_keeps_database_and_coverage_bound_to_snapshot(self):
        class SnapshotReviewer:
            def review(self, _context):
                return [
                    {
                        "severity": "low",
                        "file": "src/app.py",
                        "line": 1,
                        "title": "变更行为问题",
                        "reason": "变更后的行为不符合约束。",
                        "suggestion": "修正变更逻辑。",
                        "evidence": "value = 2",
                        "impact": "behavior",
                    }
                ]

        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            (repo / "src").mkdir()
            (repo / "src" / "app.py").write_text("value = 1\n", encoding="utf-8")
            self._git(repo, "init", "-q", "-b", "main")
            self._git(repo, "config", "user.name", "Workflow Test")
            self._git(repo, "config", "user.email", "test@example.com")
            self._git(repo, "add", ".")
            self._git(repo, "commit", "-qm", "initial")
            (repo / "src" / "app.py").write_text("value = 2\n", encoding="utf-8")
            self._git(repo, "add", ".")
            self._git(repo, "commit", "-qm", "change")
            revision = self._git(repo, "rev-parse", "HEAD")

            import app.engine.reviewers as reviewers
            from app.config import settings

            with mock.patch.dict(
                reviewers.REVIEWER_REGISTRY,
                {
                    "style_reviewer": SnapshotReviewer(),
                    "performance_reviewer": SnapshotReviewer(),
                },
                clear=True,
            ), mock.patch.object(settings, "crg_enabled", False):
                report = run_workflow(
                    str(repo),
                    review_type="local",
                    commit_hash=revision,
                )

        self.assertEqual(report["review_status"], "complete")
        self.assertEqual(report["quality"]["coverage_status"], "complete")
        self.assertEqual(report["quality"]["database_status"], "skipped")
        self.assertEqual(report["code_database"], {})
        self.assertEqual(len(report["findings"]), 1)

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

        report_state = generate_report_node(state)

        self.assertEqual(report_state["findings"], [])
        self.assertTrue(report_state["report"])
        self.assertEqual(report_state["report"]["review_status"], "degraded")
        self.assertEqual(report_state["report"]["summary"], "审查未完整完成，当前未确认问题")

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
            '"line":"1","title":"标题","reason":"原因","suggestion":"建议",'
            '"impact":"behavior"}]}'
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

    def test_dynamic_reviewer_prompt_keeps_diff_but_not_repeated_file_context(self):
        reviewer = StyleReviewer()
        with mock.patch.object(settings, "review_context_max_chars", 0):
            context = ReviewerContext(
                diff="@@ -1,1 +1,2 @@\n+value = 1",
                changed_files=["src/app.py"],
                file_context={"src/app.py": "1|value = 1\n2|value = 2"},
            )
            messages = reviewer._build_messages(context)

        self.assertIn("@@ -1,1 +1,2 @@", messages[1]["content"])
        self.assertNotIn("## 当前文件上下文", messages[1]["content"])
        self.assertEqual(context.input_coverage.get("truncated_inputs", 0), 0)
        self.assertGreater(context.input_coverage["context_limited_inputs"], 0)

    def test_dynamic_context_budget_prioritises_primary_file(self):
        reviewer = StyleReviewer()
        with mock.patch.object(settings, "review_context_max_chars", 20):
            context = ReviewerContext(
                diff="+value = 1",
                changed_files=["src/z.py"],
                file_context={
                    "src/a.py": "1|related = True",
                    "src/z.py": "1|value = 1",
                },
            )
            messages = reviewer._build_messages(context)

        self.assertIn("### src/z.py", messages[1]["content"])
        self.assertLess(
            messages[1]["content"].index("### src/z.py"),
            messages[1]["content"].index("### src/a.py"),
        )
        self.assertGreater(context.input_coverage["context_limited_inputs"], 0)

    def test_reviewer_prompt_declares_strict_current_diff_scope(self):
        messages = StyleReviewer()._build_messages(
            ReviewerContext(
                diff="diff --git a/src/app.py b/src/app.py\n+value = 1",
                changed_files=["src/app.py"],
                review_scope={
                    "target": "提交 abc123 的当前改动",
                    "revision": "abc123",
                    "base_revision": "000000",
                },
            )
        )

        content = messages[1]["content"]
        self.assertIn("审查范围（严格）", content)
        self.assertIn("提交 abc123 的当前改动", content)
        self.assertIn("Finding 必须落在当前 Diff 的变更文件与新增/修改行", content)

    def test_llm_provider_exposes_deepseek_prompt_cache_usage(self):
        provider = object.__new__(LLMProvider)
        provider.model = "deepseek-v4-flash"
        provider.base_url = "https://api.deepseek.com"
        provider.temperature = 0
        provider.max_tokens = 100
        response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="[]", tool_calls=[]),
                    finish_reason="stop",
                )
            ],
            usage=SimpleNamespace(
                prompt_tokens=220,
                completion_tokens=14,
                total_tokens=234,
                prompt_cache_hit_tokens=160,
                prompt_cache_miss_tokens=60,
            ),
        )
        provider.client = mock.Mock()
        provider.client.chat.completions.create.return_value = response

        result = provider.chat([{"role": "user", "content": "review"}])

        self.assertEqual(result["usage"]["prompt_tokens"], 220)
        self.assertEqual(result["usage"]["prompt_cache_hit_tokens"], 160)
        self.assertEqual(result["usage"]["prompt_cache_miss_tokens"], 60)

    def test_llm_provider_sends_explicit_deepseek_thinking_mode(self):
        provider = object.__new__(LLMProvider)
        provider.model = "deepseek-v4-flash"
        provider.base_url = "https://api.deepseek.com"
        provider.temperature = 0
        provider.max_tokens = 100
        response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content='{"findings":[]}', tool_calls=[]),
                    finish_reason="stop",
                )
            ],
            usage=SimpleNamespace(),
        )
        provider.client = mock.Mock()
        provider.client.chat.completions.create.return_value = response

        provider.chat(
            [{"role": "user", "content": "review"}],
            response_format={"type": "json_object"},
            max_tokens=23,
            thinking="disabled",
        )

        kwargs = provider.client.chat.completions.create.call_args.kwargs
        self.assertEqual(kwargs["max_tokens"], 23)
        self.assertEqual(kwargs["extra_body"], {"thinking": {"type": "disabled"}})

    def test_reviewer_session_rebuilds_without_previous_unit_history(self):
        reviewer = StyleReviewer()
        history = [
            {"role": "system", "content": "stale system"},
            {"role": "user", "content": "stale context + previous unit"},
            {"role": "assistant", "content": "stale model output"},
        ]
        context = ReviewerContext(
            diff="new diff",
            llm_history=history,
        )

        messages = reviewer._build_messages(context)

        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["role"], "system")
        self.assertNotEqual(messages[0], history[0])
        self.assertEqual(messages[1]["role"], "user")
        self.assertIn("new diff", messages[1]["content"])
        self.assertNotIn("stale model output", json.dumps(messages, ensure_ascii=False))

    def test_reviewer_does_not_repeat_file_context_already_in_stable_pack(self):
        reviewer = StyleReviewer()
        context = ReviewerContext(
            diff="new diff",
            file_context={"src/app.py": "value = 1\n"},
            shared_file_context={"src/app.py": "value = 1\n"},
        )

        messages = reviewer._build_messages(context)

        self.assertNotIn("## 当前文件上下文", messages[1]["content"])

    def test_reviewer_repairs_non_json_model_output_before_failing(self):
        class RepairingLLM:
            def __init__(self):
                self.repair_messages = []
                self.calls = 0
                self.kwargs = []

            def chat(self, messages, **kwargs):
                self.calls += 1
                self.kwargs.append(kwargs)
                if self.calls == 1:
                    return {
                        "content": "审查结果：```json\n[{'severity': 'low'}]\n```",
                        "finish_reason": "stop",
                    }
                self.repair_messages.append(messages)
                return {
                    "content": (
                        '{"findings":[{"severity":"low","file":"src/app.py",'
                        '"line":1,"title":"示例","reason":"原因",'
                        '"suggestion":"建议","impact":"behavior"}]}'
                    ),
                    "tool_calls": [],
                }

        reviewer = StyleReviewer()
        reviewer._llm = RepairingLLM()

        findings = reviewer.review(ReviewerContext(diff="diff"))

        self.assertEqual(findings[0]["file"], "src/app.py")
        self.assertEqual(len(reviewer._llm.repair_messages), 1)
        # JSON 修复只整理原始输出，并显式关闭思考模式。
        self.assertEqual(reviewer._llm.calls, 2)
        self.assertEqual(
            reviewer._llm.kwargs[1]["thinking"],
            "disabled",
        )
        self.assertEqual(
            reviewer._llm.kwargs[1]["max_tokens"],
            settings.llm_json_repair_max_tokens,
        )
        repair_prompt = "\n".join(
            message["content"]
            for message in reviewer._llm.repair_messages[0]
        )
        self.assertIn("只保留原始输出中已经完整的 Finding", repair_prompt)
        self.assertIn("最多保留 5 条 Finding", repair_prompt)

    def test_reviewer_does_not_turn_unverifiable_output_into_clean_review(self):
        class EmptyRepairLLM:
            def __init__(self):
                self.calls = 0

            def chat(self, _messages, **_kwargs):
                self.calls += 1
                if self.calls == 1:
                    return {"content": "模型分析被截断，无法确认结果"}
                return {"content": '{"findings":[]}', "tool_calls": []}

        reviewer = StyleReviewer()
        reviewer._llm = EmptyRepairLLM()

        with self.assertRaises(ReviewerOutputError):
            reviewer.review(ReviewerContext(diff="diff"))

    def test_truncated_reviewer_output_is_not_treated_as_clean_review(self):
        class TruncatedLLM:
            def __init__(self):
                self.calls = 0

            def chat(self, _messages, **_kwargs):
                self.calls += 1
                if self.calls == 1:
                    return {
                        "content": 'analysis: `"".split("-")` returns [""]。Actually,',
                        "finish_reason": "length",
                    }
                return {
                    "content": '{"findings":[]}',
                    "tool_calls": [],
                    "finish_reason": "stop",
                }

        reviewer = StyleReviewer()
        reviewer._llm = TruncatedLLM()

        with self.assertRaisesRegex(
            ReviewerOutputError,
            "output was truncated before complete review JSON",
        ):
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

        report_state = generate_report_node(state)

        attempt = state["reviewer_outputs"]["style_reviewer"]["attempts"][0]
        self.assertEqual(attempt["finish_reason"], "length")
        self.assertTrue(attempt["truncated"])
        self.assertEqual(state["quality_metrics"]["truncated_outputs"], 1)
        self.assertEqual(report_state["report"]["review_status"], "degraded")

    def test_reviewer_captures_primary_output_for_report_trace(self):
        class TracedLLM:
            def chat(self, *_args, **_kwargs):
                return {
                    "content": '{"findings":[],"context_requests":[]}',
                    "finish_reason": "stop",
                }

        outputs = []
        reviewer = StyleReviewer()
        reviewer._llm = TracedLLM()

        reviewer.review(
            ReviewerContext(
                diff="diff",
                output_hook=lambda stage, output: outputs.append((stage, output)),
            )
        )

        self.assertEqual(
            outputs,
            [("review", '{"findings":[],"context_requests":[]}')],
        )

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
