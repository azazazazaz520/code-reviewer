"""审查图节点契约测试。

每个节点只读写职责范围内的 ReviewState 字段；节点间互不依赖，
可直接以最小 state 输入独立调用。
"""

import unittest
import tempfile
import threading
import time
from pathlib import Path
from unittest import mock

import app.engine.nodes.prepare_review as prepare_review_module
import app.engine.nodes.load_pr as load_pr_module
import app.engine.reviewers as reviewers_module
from app.config import settings
from app.engine.nodes import (
    generate_report_node,
    load_pr_node,
    planning_node,
    prepare_review_node,
    run_reviews_node,
    validate_changes_node,
)
from app.engine.context import REVIEW_DIFF_BATCH_CHARS


class LoadPrNodeTests(unittest.TestCase):
    def test_uses_snapshot_without_fetching(self):
        state = {
            "snapshot_revision": "abc123",
            "snapshot_base_revision": "def456",
            "_log_hook": None,
        }

        result = load_pr_node(state)

        self.assertIs(result, state)

    def test_local_mode_collects_diff_and_files(self):
        with mock.patch.object(load_pr_module, "get_diff", return_value="diff text") as get_diff:
            with mock.patch.object(
                load_pr_module,
                "get_changed_files",
                return_value="src/a.py\nsrc/b.py\n",
            ):
                state = {
                    "repo_id": ".",
                    "review_type": "local",
                    "commit_hash": None,
                    "pr_number": None,
                    "git_url": "",
                    "_log_hook": None,
                }
                result = load_pr_node(state)

        get_diff.assert_called_once_with(".", "HEAD~1")
        self.assertEqual(result["raw_diff"], "diff text")
        self.assertEqual(result["changed_files"], ["src/a.py", "src/b.py"])

    def test_pr_error_propagates(self):
        with (
            mock.patch.object(load_pr_module, "get_pr_diff", return_value="Error: fetch failed"),
            mock.patch.object(load_pr_module, "get_pr_changed_files", return_value="ok"),
        ):
            state = {
                "repo_id": ".",
                "review_type": "pr",
                "pr_number": 1,
                "git_url": "https://github.com/example/repo",
                "_log_hook": None,
            }
            with self.assertRaises(RuntimeError):
                load_pr_node(state)


class PlanningNodeTests(unittest.TestCase):
    def test_builds_plan_and_scopes(self):
        state = {"changed_files": ["src/app.ts", "update/windows.json"], "raw_diff": ""}

        result = planning_node(state)

        self.assertIn("style_reviewer", result["review_plan"])
        self.assertEqual(result["change_scopes"]["src/app.ts"], "source_code")
        self.assertEqual(result["change_scopes"]["update/windows.json"], "release_manifest")


class ValidateChangesNodeTests(unittest.TestCase):
    def test_skips_non_manifest_changes(self):
        state = {"repo_id": ".", "changed_files": ["src/app.ts"], "_log_hook": None}

        result = validate_changes_node(state)

        self.assertEqual(result["validator_findings"], [])
        self.assertEqual(result["checks"], [])


class PrepareReviewNodeTests(unittest.TestCase):
    def test_builds_plan_context_units_and_complete_diff_coverage(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "src" / "app.py"
            source.parent.mkdir(parents=True)
            source.write_text("value = 1\n", encoding="utf-8")
            state = {
                "repo_id": temp_dir,
                "snapshot_revision": "working-tree",
                "changed_files": ["src/app.py"],
                "raw_diff": (
                    "diff --git a/src/app.py b/src/app.py\n"
                    "--- a/src/app.py\n"
                    "+++ b/src/app.py\n"
                    "@@ -1,0 +1,1 @@\n"
                    "+value = 1\n"
                ),
                "workflow_errors": [],
                "checks": [],
                "_log_hook": None,
            }

            with mock.patch.object(settings, "crg_enabled", False):
                result = prepare_review_node(state)

        self.assertIn("style_reviewer", result["review_plan"])
        self.assertEqual(len(result["review_units"]), 1)
        self.assertEqual(result["coverage"]["coverage_status"], "complete")
        self.assertEqual(result["coverage"]["uncovered_hunks"], [])
        self.assertIn("src/app.py", result["file_context_cache"])
        self.assertEqual(result["database_status"], "skipped")

    def test_deep_context_is_opt_in(self):
        state = {
            "repo_id": ".",
            "snapshot_revision": "rev-1",
            "changed_files": [],
            "raw_diff": "",
            "workflow_errors": [],
            "checks": [],
            "_log_hook": None,
        }

        with (
            mock.patch.object(settings, "crg_enabled", False),
            mock.patch.object(prepare_review_module, "build_database_node") as build_db,
            mock.patch.object(prepare_review_module, "try_crg_context") as try_crg,
        ):
            prepare_review_node(state)

        build_db.assert_not_called()
        try_crg.assert_not_called()
        self.assertFalse(state["crg_enabled"])


class _GoodReviewer:
    def review(self, _context):
        return [
            {
                "severity": "low",
                "file": "src/app.py",
                "line": 1,
                "title": "示例问题",
                "reason": "原因",
                "suggestion": "建议",
                "evidence": "value = 1",
                "impact": "behavior",
            }
        ]


class _FailReviewer:
    def review(self, _context):
        raise RuntimeError("boom")


class _BatchReviewer:
    def __init__(self):
        self.contexts = []

    def review(self, context):
        self.contexts.append(context)
        return []


class _CoverageBatchReviewer:
    def __init__(self):
        self.batch_number = 0

    def review(self, context):
        self.batch_number += 1
        context.input_coverage["truncation_events"] = [
            f"batch:{self.batch_number}:truncation"
        ]
        context.input_coverage["context_request_failure_events"] = [
            {
                "file": f"src/{self.batch_number}.py",
                "message": "模拟上下文读取失败",
            }
        ]
        context.input_coverage["truncated_inputs"] = 1
        context.input_coverage["context_request_failures"] = 1
        return []


class RunReviewsNodeTests(unittest.TestCase):
    def setUp(self):
        self._original = dict(reviewers_module.REVIEWER_REGISTRY)

    def tearDown(self):
        reviewers_module.REVIEWER_REGISTRY.clear()
        reviewers_module.REVIEWER_REGISTRY.update(self._original)

    def _state(self):
        return {
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

    def test_collects_and_filters_findings(self):
        reviewers_module.REVIEWER_REGISTRY.update({"style_reviewer": _GoodReviewer()})

        result = run_reviews_node(self._state())

        self.assertEqual(len(result["findings"]), 1)
        self.assertEqual(result["findings"][0]["title"], "示例问题")
        self.assertEqual(result["quality_metrics"]["candidate_findings"], 1)
        self.assertEqual(result["quality_metrics"]["accepted_findings"], 1)
        self.assertEqual(
            len(result["reviewer_outputs"]["style_reviewer"]["candidate_findings"]),
            1,
        )
        self.assertEqual(result["checks"], [])

    def test_failed_reviewer_degrades_to_workflow_error(self):
        reviewers_module.REVIEWER_REGISTRY.update({"style_reviewer": _FailReviewer()})

        result = run_reviews_node(self._state())

        self.assertEqual(result["findings"], [])
        self.assertEqual(len(result["workflow_errors"]), 1)
        self.assertEqual(result["workflow_errors"][0]["reviewer"], "style_reviewer")
        self.assertIn(
            "reviewer_style_reviewer",
            [check["name"] for check in result["checks"]],
        )
        self.assertEqual(
            result["reviewer_outputs"]["style_reviewer"]["error_message"],
            "boom",
        )

    def test_quality_checks_are_updated_instead_of_duplicated(self):
        state = self._state()
        state["review_plan"] = []
        state["coverage"] = {
            "uncovered_files": ["src/app.py"],
            "uncovered_hunks": ["src/app.py#1"],
            "truncated_inputs": 0,
            "tool_errors": 0,
        }

        run_reviews_node(state)
        run_reviews_node(state)

        names = [check["name"] for check in state["checks"]]
        self.assertEqual(names.count("review_coverage"), 1)
        self.assertEqual(names.count("review_hunks"), 1)

    def test_unrelated_cached_context_does_not_create_extra_batches(self):
        reviewer = _BatchReviewer()
        reviewers_module.REVIEWER_REGISTRY.update({"style_reviewer": reviewer})
        state = self._state()
        state["file_context_cache"] = {
            "src/a.py": "a" * 7000,
            "src/b.py": "b" * 7000,
        }

        with mock.patch.object(settings, "review_context_max_files", 10), mock.patch.object(
            settings, "review_context_max_chars", 12000
        ):
            result = run_reviews_node(state)

        self.assertEqual(len(reviewer.contexts), 1)
        self.assertEqual(result["coverage"]["truncated_inputs"], 0)
        self.assertTrue(all(
            context.input_coverage["truncated_inputs"] == 0
            for context in reviewer.contexts
        ))

        with mock.patch.object(settings, "review_context_max_files", 10), mock.patch.object(
            settings, "review_context_max_chars", 12000
        ):
            run_reviews_node(state)
        self.assertEqual(len(reviewer.contexts), 1)
        self.assertEqual(state["coverage"]["truncated_inputs"], 0)

    def test_unstructured_diff_fallback_does_not_cross_with_context_batches(self):
        reviewer = _BatchReviewer()
        reviewers_module.REVIEWER_REGISTRY.update({"style_reviewer": reviewer})
        state = self._state()
        state["raw_diff"] = "d" * (REVIEW_DIFF_BATCH_CHARS * 2 + 1)
        state["file_context_cache"] = {
            "src/a.py": "a" * 7000,
            "src/b.py": "b" * 7000,
        }

        with mock.patch.object(settings, "review_batch_max_chars", REVIEW_DIFF_BATCH_CHARS):
            run_reviews_node(state)

        self.assertEqual(len(reviewer.contexts), 3)

    def test_input_coverage_is_aggregated_across_reviewer_batches(self):
        reviewer = _CoverageBatchReviewer()
        reviewers_module.REVIEWER_REGISTRY.update({"style_reviewer": reviewer})
        state = self._state()
        state["changed_files"] = ["src/a.py", "src/b.py"]
        state["raw_diff"] = (
            "diff --git a/src/a.py b/src/a.py\n"
            "--- a/src/a.py\n+++ b/src/a.py\n"
            "@@ -1,1 +1,1 @@\n-old\n+new\n"
            "diff --git a/src/b.py b/src/b.py\n"
            "--- a/src/b.py\n+++ b/src/b.py\n"
            "@@ -1,1 +1,1 @@\n-old\n+new\n"
        )

        with mock.patch.object(settings, "review_batch_max_chars", 1):
            result = run_reviews_node(state)

        trace = result["reviewer_outputs"]["style_reviewer"]["input_coverage"]
        self.assertEqual(
            trace["truncation_events"],
            ["batch:1:truncation", "batch:2:truncation"],
        )
        self.assertEqual(trace["truncated_inputs"], 2)
        self.assertEqual(
            [event["file"] for event in trace["context_request_failure_events"]],
            ["src/1.py", "src/2.py"],
        )
        self.assertEqual(trace["context_request_failures"], 2)
        self.assertEqual(result["coverage"]["truncated_inputs"], 2)
        self.assertEqual(result["coverage"]["context_request_failures"], 2)

    def test_context_limits_are_kept_as_diagnostics_without_degrading_review(self):
        class ContextLimitedReviewer:
            def review(self, context):
                context.input_coverage.update(
                    {
                        "context_limit_events": ["selection:omitted:src/related.py"],
                        "context_limited_inputs": 1,
                    }
                )
                return []

        reviewers_module.REVIEWER_REGISTRY.update(
            {"style_reviewer": ContextLimitedReviewer()}
        )

        result = run_reviews_node(self._state())

        self.assertEqual(result["coverage"]["truncated_inputs"], 0)
        self.assertEqual(result["coverage"]["context_limited_inputs"], 1)
        self.assertNotIn(
            "review_input_truncation",
            [check["name"] for check in result["checks"]],
        )

    def test_prompt_cache_metrics_are_aggregated_by_provider_request(self):
        class UsageReviewer:
            def review(self, context):
                context.input_coverage.update(
                    {
                        "provider_requests": 2,
                        "llm_prompt_tokens": 220,
                        "llm_completion_tokens": 14,
                        "llm_total_tokens": 234,
                        "llm_prompt_cache_hit_tokens": 160,
                        "llm_prompt_cache_miss_tokens": 60,
                    }
                )
                return []

        reviewers_module.REVIEWER_REGISTRY.update({"style_reviewer": UsageReviewer()})

        result = run_reviews_node(self._state())

        self.assertEqual(result["quality_metrics"]["provider_requests"], 2)
        self.assertEqual(result["quality_metrics"]["llm_prompt_tokens"], 220)
        self.assertEqual(
            result["quality_metrics"]["llm_prompt_cache_hit_tokens"],
            160,
        )
        self.assertEqual(
            result["quality_metrics"]["llm_prompt_cache_miss_tokens"],
            60,
        )
        self.assertAlmostEqual(
            result["quality_metrics"]["llm_prompt_cache_hit_rate"],
            160 / 220,
        )

    def test_planned_batches_are_not_cut_by_a_call_count_budget(self):
        reviewer = _BatchReviewer()
        reviewers_module.REVIEWER_REGISTRY.update({"style_reviewer": reviewer})
        state = self._state()
        state["raw_diff"] = (
            "diff --git a/src/app.py b/src/app.py\n"
            "--- a/src/app.py\n+++ b/src/app.py\n"
            "@@ -1,1 +1,1 @@\n-old\n+new\n"
            "@@ -500,1 +500,1 @@\n-old\n+newer\n"
        )
        state["coverage"] = {
            "planned_hunks": 2,
            "covered_hunks": 1,
            "uncovered_hunks": ["src/app.py#2"],
            "coverage_status": "incomplete",
        }

        result = run_reviews_node(state)

        self.assertEqual(len(reviewer.contexts), 1)
        self.assertEqual(result["quality_metrics"]["primary_llm_calls"], 1)
        self.assertNotIn("max_review_calls", result["quality_metrics"])
        self.assertEqual(result["quality_metrics"]["pending_units"], 0)
        self.assertEqual(result["quality_metrics"]["reviewed_units"], 2)
        self.assertEqual(result["quality_metrics"]["context_covered_hunks"], 1)
        self.assertEqual(
            result["quality_metrics"]["pending_reviewer_assignments"],
            0,
        )
        self.assertFalse(result["quality_metrics"].get("budget_exhausted"))

    def test_cancel_check_stops_reviewer_before_primary_call(self):
        reviewer = _BatchReviewer()
        reviewers_module.REVIEWER_REGISTRY.update({"style_reviewer": reviewer})
        state = self._state()
        state["_cancel_check"] = lambda: True

        result = run_reviews_node(state)

        self.assertEqual(reviewer.contexts, [])
        self.assertTrue(result["cancel_requested"])
        self.assertEqual(result["quality_metrics"]["primary_llm_calls"], 0)
        self.assertTrue(any(check["name"] == "review_cancelled" for check in result["checks"]))

    def test_reviewers_run_in_parallel_and_merge_in_plan_order(self):
        started: list[tuple[str, int]] = []

        class ParallelReviewer:
            def review(self, _context):
                started.append((threading.current_thread().name, threading.get_ident()))
                time.sleep(0.05)
                return []

        reviewers_module.REVIEWER_REGISTRY.update({
            "style_reviewer": ParallelReviewer(),
            "security_reviewer": ParallelReviewer(),
        })
        state = self._state()
        state["review_plan"] = ["style_reviewer", "security_reviewer"]

        with mock.patch.object(settings, "review_parallelism", 2):
            result = run_reviews_node(state)

        self.assertEqual(len(started), 2)
        self.assertEqual(len({thread_id for _name, thread_id in started}), 2)
        self.assertEqual(list(result["reviewer_outputs"]), ["style_reviewer", "security_reviewer"])


class GenerateReportNodeTests(unittest.TestCase):
    def test_writes_summary_risk_and_report(self):
        state = {
            "findings": [
                {
                    "severity": "high",
                    "file": "src/app.py",
                    "line": 1,
                    "title": "问题",
                    "reason": "原因",
                    "suggestion": "建议",
                    "impact": "behavior",
                }
            ],
            "workflow_errors": [],
            "quality_metrics": {"truncated_outputs": 0},
            "checks": [],
            "reviewer_outputs": {},
            "review_type": "local",
            "changed_files": ["src/app.py"],
            "raw_diff": "@@ -1,0 +1,1 @@\n+value = 1\n",
            "_log_hook": None,
        }

        result = generate_report_node(state)

        self.assertEqual(result["summary"], "本次审查发现 1 个问题（1 个高危）")
        self.assertEqual(result["risk_level"], "high")
        self.assertEqual(result["review_status"], "complete")
        self.assertEqual(result["report"]["stats"]["total_findings"], 1)
        self.assertEqual(result["report"]["changes"]["changed_files"], ["src/app.py"])


if __name__ == "__main__":
    unittest.main()
