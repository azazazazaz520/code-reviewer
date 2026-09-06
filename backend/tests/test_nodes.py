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

import app.engine.nodes.collect_context as collect_context_module
import app.engine.nodes.load_pr as load_pr_module
import app.engine.reviewers as reviewers_module
from app.config import settings
from app.engine.nodes import (
    collect_context_node,
    generate_report_node,
    load_pr_node,
    planning_node,
    reflection_node,
    run_reviews_node,
    should_retry,
    validate_changes_node,
)
from app.engine.tools.context import ApprovedContextRef, TaskToolCache, TaskToolContext
from app.engine.context import REVIEW_DIFF_BATCH_CHARS
from app.engine.reviewers.base import ReviewerContext
from app.engine.reviewers.style import StyleReviewer


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


class CollectContextNodeTests(unittest.TestCase):
    def test_skips_when_plan_is_empty(self):
        state = {
            "repo_id": ".",
            "changed_files": ["a.py"],
            "review_plan": [],
            "_log_hook": None,
        }

        result = collect_context_node(state)

        self.assertTrue(result["context_initialized"])
        self.assertEqual(result["context_candidates"], [])

    def test_reads_candidates_when_crg_unavailable(self):
        with (
            mock.patch.object(collect_context_module, "try_crg_context", return_value=False),
            mock.patch.object(collect_context_module, "read_file", return_value="content"),
        ):
            state = {
                "repo_id": ".",
                "changed_files": ["a.py", "b.py"],
                "review_plan": ["style_reviewer"],
                "_log_hook": None,
            }
            result = collect_context_node(state)

        self.assertFalse(result["crg_enabled"])
        self.assertEqual(result["context_candidates"], ["a.py", "b.py"])
        self.assertEqual(set(result["file_context_cache"]), {"a.py", "b.py"})
        self.assertEqual(result["context_round"], 1)

    def test_context_pages_share_task_tool_cache(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "app.py"
            path.write_text("value = 1\n", encoding="utf-8")
            tool_context = TaskToolContext(
                repo_root=temp_dir,
                revision="rev-1",
                approved_context_refs=(ApprovedContextRef("app.py", 1, 1),),
            )
            tool_cache = TaskToolCache()
            context_errors = {}
            first_progress = {}
            second_progress = {}

            with mock.patch.object(
                collect_context_module,
                "read_file",
                wraps=collect_context_module.read_file,
            ) as read_file:
                collect_context_module._read_context_page(
                    tool_context,
                    "app.py",
                    (1, 1),
                    first_progress,
                    {},
                    context_errors,
                    tool_cache,
                )
                collect_context_module._read_context_page(
                    tool_context,
                    "app.py",
                    (1, 1),
                    second_progress,
                    {},
                    context_errors,
                    tool_cache,
                )

            self.assertEqual(read_file.call_count, 1)
            self.assertEqual(tool_cache.stats()["tool_calls"], 1)
            self.assertEqual(tool_cache.stats()["read_file_requests"], 2)
            self.assertEqual(tool_cache.stats()["read_file_cache_hits"], 1)

    def test_reviewer_cache_hit_renders_context_page_as_string(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "app.py"
            path.write_text("value = 1\n", encoding="utf-8")
            tool_context = TaskToolContext(
                repo_root=temp_dir,
                revision="rev-1",
                approved_context_refs=(ApprovedContextRef("app.py", 1, 1),),
            )
            tool_cache = TaskToolCache()
            progress = {}

            collect_context_module._read_context_page(
                tool_context,
                "app.py",
                (1, 1),
                progress,
                {},
                {},
                tool_cache,
            )

            reviewer_context = ReviewerContext(
                tool_context=tool_context,
                tool_cache=tool_cache,
            )
            result = reviewers_module.StyleReviewer()._build_tool_handlers(
                reviewer_context
            )["ReadFile"](
                file_path=str(path),
                start_line=1,
                max_lines=1,
            )

        self.assertIsInstance(result, str)
        self.assertIn("value = 1", result)
        self.assertEqual(tool_cache.stats()["tool_calls"], 1)
        self.assertEqual(tool_cache.stats()["cache_hits"], 1)

    def test_crg_high_impact_appends_security_reviewer(self):
        with (
            mock.patch.object(collect_context_module, "try_crg_context", return_value=True),
            mock.patch.object(collect_context_module, "read_file", return_value="content"),
        ):
            state = {
                "repo_id": ".",
                "changed_files": ["a.py"],
                "review_plan": ["style_reviewer"],
                "impact_radius": {
                    "changed_nodes": 10,
                    "impacted_nodes": 30,
                    "impacted_files": 5,
                },
                "_log_hook": None,
            }
            result = collect_context_node(state)

        self.assertTrue(result["crg_enabled"])
        self.assertIn("security_reviewer", result["review_plan"])

    def test_low_impact_keeps_plan_unchanged(self):
        with (
            mock.patch.object(collect_context_module, "try_crg_context", return_value=True),
            mock.patch.object(collect_context_module, "read_file", return_value="content"),
        ):
            state = {
                "repo_id": ".",
                "changed_files": ["a.py"],
                "review_plan": ["style_reviewer"],
                "impact_radius": {"changed_nodes": 1, "impacted_nodes": 2, "impacted_files": 1},
                "_log_hook": None,
            }
            result = collect_context_node(state)

        self.assertEqual(result["review_plan"], ["style_reviewer"])

    def test_reads_large_file_in_pages_and_reports_complete_coverage(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "large.py"
            path.write_text("\n".join(f"line-{n}" for n in range(1, 405)), encoding="utf-8")
            state = {
                "repo_id": temp_dir,
                "changed_files": ["large.py"],
                "review_plan": ["style_reviewer"],
                "raw_diff": "@@ -1,0 +1,1 @@\n+line-1\n",
                "context_initialized": False,
                "context_round": 0,
                "context_progress": {},
                "file_context_cache": {},
                "context_errors": {},
                "tool_context": TaskToolContext(
                    repo_root=temp_dir,
                    revision="rev-1",
                    approved_context_refs=(ApprovedContextRef("large.py", 1, 404),),
                ),
                "database_status": "ready",
                "extraction_status": "complete",
                "coverage": {},
                "_log_hook": None,
            }

            with mock.patch.object(collect_context_module, "try_crg_context", return_value=False), \
                    mock.patch.object(collect_context_module.settings, "context_files_per_round", 1):
                collect_context_node(state)
                self.assertEqual(state["coverage"]["covered_files"], 0)
                collect_context_node(state)
                collect_context_node(state)

            self.assertTrue(state["context_progress"]["large.py"]["complete"])
            self.assertEqual(state["coverage"]["covered_files"], 1)
            self.assertEqual(state["coverage"]["coverage_status"], "complete")
            self.assertIn("line-404", state["file_context_cache"]["large.py"])

    def test_priority_context_ranges_mark_file_complete(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "app.py"
            path.write_text("value = 1\nvalue = 2\n", encoding="utf-8")
            state = {
                "repo_id": temp_dir,
                "changed_files": ["app.py"],
                "review_plan": ["style_reviewer"],
                "raw_diff": (
                    "diff --git a/app.py b/app.py\n"
                    "--- a/app.py\n"
                    "+++ b/app.py\n"
                    "@@ -1,2 +1,2 @@\n"
                    "-old\n"
                    "+value = 1\n"
                    " value = 2\n"
                ),
                "context_initialized": False,
                "context_round": 0,
                "context_progress": {},
                "file_context_cache": {},
                "context_errors": {},
                "tool_context": TaskToolContext(
                    repo_root=temp_dir,
                    revision="rev-1",
                    approved_context_refs=(ApprovedContextRef("app.py", 1, 2),),
                ),
                "database_status": "ready",
                "extraction_status": "complete",
                "coverage": {},
                "_log_hook": None,
            }

            with mock.patch.object(collect_context_module, "try_crg_context", return_value=False):
                collect_context_node(state)

        self.assertTrue(state["context_progress"]["app.py"]["complete"])
        self.assertEqual(state["coverage"]["covered_files"], 1)
        self.assertEqual(state["coverage"]["uncovered_files"], [])

    def test_processes_remaining_files_after_first_batch(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            changed_files = []
            refs = []
            for index in range(25):
                file_path = f"src/file-{index}.py"
                target = repo / file_path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(f"value = {index}\n", encoding="utf-8")
                changed_files.append(file_path)
                refs.append(ApprovedContextRef(file_path, 1, 1))

            state = {
                "repo_id": temp_dir,
                "changed_files": changed_files,
                "review_plan": ["style_reviewer"],
                "context_initialized": False,
                "context_round": 0,
                "context_progress": {},
                "file_context_cache": {},
                "context_errors": {},
                "tool_context": TaskToolContext(
                    repo_root=temp_dir,
                    revision="rev-1",
                    approved_context_refs=tuple(refs),
                ),
                "database_status": "ready",
                "extraction_status": "complete",
                "coverage": {},
                "_log_hook": None,
            }

            with mock.patch.object(collect_context_module, "try_crg_context", return_value=False), \
                    mock.patch.object(collect_context_module.settings, "context_files_per_round", 20):
                collect_context_node(state)
                self.assertEqual(state["coverage"]["covered_files"], 20)
                collect_context_node(state)

            self.assertEqual(state["coverage"]["covered_files"], 25)
            self.assertEqual(len(state["coverage"]["uncovered_files"]), 0)


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
        context.input_coverage["tool_error_events"] = [
            {
                "key": f"batch:{self.batch_number}:tool-error",
                "tool": "ReadFile",
                "message": "模拟 Tool 参数错误",
            }
        ]
        context.input_coverage["truncated_inputs"] = 1
        context.input_coverage["tool_errors"] = 1
        return []


class _ModelDecisionReviewer:
    def review(self, context):
        StyleReviewer()._build_tool_handlers(context)["ReadFile"](
            file_path="src/app.py",
            start_line=1,
            max_lines="1.5",
        )
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

    def test_large_reviewer_context_is_split_without_input_truncation(self):
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

        self.assertEqual(len(reviewer.contexts), 2)
        self.assertEqual(result["coverage"]["truncated_inputs"], 0)
        self.assertTrue(all(
            context.input_coverage["truncated_inputs"] == 0
            for context in reviewer.contexts
        ))

        with mock.patch.object(settings, "review_context_max_files", 10), mock.patch.object(
            settings, "review_context_max_chars", 12000
        ):
            run_reviews_node(state)
        self.assertEqual(len(reviewer.contexts), 2)
        self.assertEqual(state["coverage"]["truncated_inputs"], 0)

    def test_diff_and_context_batches_are_not_cross_product(self):
        reviewer = _BatchReviewer()
        reviewers_module.REVIEWER_REGISTRY.update({"style_reviewer": reviewer})
        state = self._state()
        state["raw_diff"] = "d" * (REVIEW_DIFF_BATCH_CHARS * 2 + 1)
        state["file_context_cache"] = {
            "src/a.py": "a" * 7000,
            "src/b.py": "b" * 7000,
        }

        with mock.patch.object(settings, "review_unit_max_chars", REVIEW_DIFF_BATCH_CHARS):
            run_reviews_node(state)

        self.assertEqual(len(reviewer.contexts), 3)

    def test_input_coverage_is_aggregated_across_reviewer_batches(self):
        reviewer = _CoverageBatchReviewer()
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

        trace = result["reviewer_outputs"]["style_reviewer"]["input_coverage"]
        self.assertEqual(
            trace["truncation_events"],
            ["batch:1:truncation", "batch:2:truncation"],
        )
        self.assertEqual(trace["truncated_inputs"], 2)
        self.assertEqual(
            [event["key"] for event in trace["tool_error_events"]],
            ["batch:1:tool-error", "batch:2:tool-error"],
        )
        self.assertEqual(trace["tool_errors"], 2)
        self.assertEqual(result["coverage"]["truncated_inputs"], 2)
        self.assertEqual(result["coverage"]["tool_errors"], 2)

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

    def test_model_decision_errors_do_not_create_tool_error_check(self):
        reviewers_module.REVIEWER_REGISTRY.update(
            {"style_reviewer": _ModelDecisionReviewer()}
        )
        state = self._state()
        state["tool_context"] = TaskToolContext(
            repo_root="E:/snapshot-root",
            revision="rev-1",
        )

        result = run_reviews_node(state)

        self.assertEqual(result["quality_metrics"]["tool_errors"], 0)
        self.assertNotIn(
            "review_tools",
            [check["name"] for check in result["checks"]],
        )
        trace = result["reviewer_outputs"]["style_reviewer"]["input_coverage"]
        self.assertEqual(trace["model_decision_errors"], 1)
        self.assertEqual(trace["tool_errors"], 0)

    def test_primary_budget_is_reserved_when_unit_starts(self):
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

        with mock.patch.object(settings, "max_review_calls", 1):
            result = run_reviews_node(state)

        self.assertEqual(len(reviewer.contexts), 1)
        self.assertEqual(result["quality_metrics"]["primary_llm_calls"], 1)
        self.assertEqual(result["quality_metrics"]["pending_units"], 1)
        self.assertEqual(result["quality_metrics"]["reviewed_units"], 1)
        self.assertEqual(result["quality_metrics"]["context_covered_hunks"], 1)
        self.assertEqual(
            result["quality_metrics"]["pending_reviewer_assignments"],
            1,
        )
        self.assertEqual(result["quality_metrics"]["budget_exhausted_reason"], "primary_calls")

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


class ReflectionNodeTests(unittest.TestCase):
    def test_stops_when_no_findings(self):
        state = {"findings": [], "reflection_round": 0, "_log_hook": None}

        result = reflection_node(state)

        self.assertEqual(result["reflection_round"], 1)
        self.assertFalse(result["need_more_context"])

    def test_stops_when_findings_have_line_refs(self):
        state = {
            "findings": [{"file": "a.py", "line": 3}],
            "reflection_round": 0,
            "context_candidates": ["b.py"],
            "file_context_cache": {},
            "_log_hook": None,
        }

        result = reflection_node(state)

        self.assertFalse(result["need_more_context"])

    def test_requests_more_context_without_line_refs(self):
        state = {
            "findings": [{"file": "a.py", "line": 0}],
            "reflection_round": 0,
            "context_candidates": ["b.py"],
            "file_context_cache": {},
            "_log_hook": None,
        }

        result = reflection_node(state)

        self.assertTrue(result["need_more_context"])

    def test_stops_at_max_rounds(self):
        state = {
            "findings": [{"file": "a.py", "line": 0}],
            "reflection_round": 3,
            "context_candidates": ["b.py"],
            "file_context_cache": {},
            "_log_hook": None,
        }

        result = reflection_node(state)

        self.assertEqual(result["reflection_round"], 4)
        self.assertFalse(result["need_more_context"])

    def test_retries_when_coverage_is_incomplete_even_with_line_refs(self):
        state = {
            "findings": [{"file": "a.py", "line": 3}],
            "reflection_round": 0,
            "coverage": {
                "uncovered_files": ["b.py"],
                "uncovered_hunks": [],
            },
            "_log_hook": None,
        }

        result = reflection_node(state)

        self.assertTrue(result["need_more_context"])


class ShouldRetryTests(unittest.TestCase):
    def test_routes_by_need_more_context(self):
        self.assertEqual(should_retry({"need_more_context": True}), "collect")
        self.assertEqual(should_retry({"need_more_context": False}), "report")


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
