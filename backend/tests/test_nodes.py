"""审查图节点契约测试。

每个节点只读写职责范围内的 ReviewState 字段；节点间互不依赖，
可直接以最小 state 输入独立调用。
"""

import unittest
from unittest import mock

import app.engine.nodes.collect_context as collect_context_module
import app.engine.nodes.load_pr as load_pr_module
import app.engine.reviewers as reviewers_module
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
            }
        ]


class _FailReviewer:
    def review(self, _context):
        raise RuntimeError("boom")


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
