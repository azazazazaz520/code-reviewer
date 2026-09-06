"""Review Report 聚合纯函数测试。

report 结构是与前端 ReviewReportResponse / ReviewChanges 的契约，
字段变更必须同步检查 frontend/src/types/index.ts。
"""

import unittest

from app.engine.reporting import (
    build_report,
    build_summary,
    count_by_severity,
    derive_review_status,
    derive_risk,
)


class CountBySeverityTests(unittest.TestCase):
    def test_counts_known_and_unknown_severities(self):
        counts = count_by_severity([
            {"severity": "critical"},
            {"severity": "high"},
            {"severity": "medium"},
            {"severity": "low"},
            {"severity": "info"},
            {},
        ])

        self.assertEqual(counts["critical"], 1)
        self.assertEqual(counts["high"], 1)
        self.assertEqual(counts["medium"], 1)
        self.assertEqual(counts["low"], 2)
        self.assertEqual(counts["info"], 1)


class DeriveRiskTests(unittest.TestCase):
    def test_highest_severity_wins(self):
        self.assertEqual(derive_risk({"critical": 1, "high": 0, "medium": 0, "low": 0}), "critical")
        self.assertEqual(derive_risk({"critical": 0, "high": 1, "medium": 2, "low": 0}), "high")
        self.assertEqual(derive_risk({"critical": 0, "high": 0, "medium": 1, "low": 5}), "medium")
        self.assertEqual(derive_risk({"critical": 0, "high": 0, "medium": 0, "low": 1}), "low")
        self.assertEqual(derive_risk({}), "low")


class DeriveReviewStatusTests(unittest.TestCase):
    def test_workflow_errors_are_degraded(self):
        self.assertEqual(derive_review_status([{"reviewer": "style_reviewer"}], {}), "degraded")

    def test_truncated_outputs_are_degraded(self):
        self.assertEqual(
            derive_review_status([], {"truncated_outputs": 1}),
            "degraded",
        )

    def test_tool_errors_and_input_truncation_are_degraded(self):
        self.assertEqual(
            derive_review_status([], {"tool_errors": 1}),
            "degraded",
        )
        self.assertEqual(
            derive_review_status([], {"truncated_inputs": 1}),
            "degraded",
        )

    def test_incomplete_database_or_coverage_is_degraded(self):
        self.assertEqual(
            derive_review_status([], {"database_status": "failed"}),
            "degraded",
        )
        self.assertEqual(
            derive_review_status([], {"coverage_status": "incomplete"}),
            "degraded",
        )
        self.assertEqual(
            derive_review_status([], {"uncovered_files": ["src/app.py"]}),
            "degraded",
        )

    def test_pending_reviewer_assignments_are_degraded(self):
        self.assertEqual(
            derive_review_status(
                [],
                {
                    "coverage_status": "complete",
                    "pending_reviewer_assignments": 1,
                },
            ),
            "degraded",
        )

    def test_clean_run_is_complete(self):
        self.assertEqual(derive_review_status([], {"truncated_outputs": 0}), "complete")

    def test_model_decision_errors_do_not_degrade_review(self):
        self.assertEqual(
            derive_review_status(
                [],
                {
                    "coverage_status": "complete",
                    "model_decision_errors": 1,
                },
            ),
            "complete",
        )


class BuildSummaryTests(unittest.TestCase):
    def test_summary_includes_high_count_when_present(self):
        self.assertEqual(build_summary(3, 1), "本次审查发现 3 个问题（1 个高危）")
        self.assertEqual(build_summary(3, 0), "本次审查发现 3 个问题")

    def test_degraded_empty_summary_exposes_incomplete_review(self):
        self.assertEqual(
            build_summary(0, 0, review_status="degraded"),
            "审查未完整完成，当前未确认问题",
        )


class BuildReportTests(unittest.TestCase):
    def _sample_state(self):
        return {
            "findings": [
                {
                    "severity": "high",
                    "file": "src/app.py",
                    "line": 12,
                    "title": "缺少边界检查",
                    "reason": "原因",
                    "suggestion": "建议",
                    "impact": "behavior",
                }
            ],
            "workflow_errors": [],
            "quality_metrics": {"truncated_outputs": 0, "candidate_findings": 1},
            "checks": [{"name": "finding_gate", "status": "ok", "message": "无"}],
            "reviewer_outputs": {"style_reviewer": {"attempts": []}},
            "review_type": "local",
            "source_type": "workspace",
            "pr_number": None,
            "commit_hash": "abc",
            "branch": "main",
            "base_branch": None,
            "snapshot_base_revision": "base",
            "snapshot_revision": "head",
            "workspace_fingerprint": "fp123",
            "workspace_stats": {"staged": 1, "untracked": 2},
            "changed_files": ["src/app.py"],
            "raw_diff": "diff --git a/src/app.py b/src/app.py",
        }

    def test_report_contract_fields(self):
        report = build_report(self._sample_state())

        self.assertEqual(report["summary"], "本次审查发现 1 个问题（1 个高危）")
        self.assertEqual(report["risk_level"], "high")
        self.assertEqual(report["review_status"], "complete")
        self.assertEqual(len(report["findings"]), 1)
        self.assertEqual(report["checks"][0]["name"], "finding_gate")
        self.assertEqual(report["quality"]["candidate_findings"], 1)
        self.assertIn("style_reviewer", report["reviewer_outputs"])

    def test_report_includes_code_database_metadata(self):
        state = self._sample_state()
        state["code_database_info"] = {
            "database_id": "db-1",
            "database_status": "ready",
            "extraction_status": "complete",
        }

        report = build_report(state)

        self.assertEqual(report["code_database"]["database_id"], "db-1")

    def test_changes_contract_fields(self):
        report = build_report(self._sample_state())

        changes = report["changes"]
        self.assertEqual(changes["review_type"], "local")
        self.assertEqual(changes["source_type"], "workspace")
        self.assertEqual(changes["commit_hash"], "abc")
        self.assertEqual(changes["base_revision"], "base")
        self.assertEqual(changes["head_revision"], "head")
        self.assertEqual(changes["workspace_fingerprint"], "fp123")
        self.assertEqual(changes["workspace_stats"], {"staged": 1, "untracked": 2})
        self.assertEqual(changes["changed_files"], ["src/app.py"])

    def test_stats_contract_fields(self):
        report = build_report(self._sample_state())

        self.assertEqual(report["stats"]["total_findings"], 1)
        self.assertEqual(report["stats"]["by_severity"]["high"], 1)
        self.assertEqual(report["stats"]["impacted_files"], 1)
        self.assertEqual(report["stats"]["test_gaps"], 0)

    def test_empty_state_produces_low_risk_report(self):
        report = build_report({})

        self.assertEqual(report["risk_level"], "low")
        self.assertEqual(report["review_status"], "complete")
        self.assertEqual(report["summary"], "本次审查发现 0 个问题")
        self.assertEqual(report["stats"]["total_findings"], 0)


if __name__ == "__main__":
    unittest.main()
