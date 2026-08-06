"""审查质量指标纯函数测试。"""

import unittest

from app.engine.quality import build_quality_checks, compute_quality_metrics


class ComputeQualityMetricsTests(unittest.TestCase):
    def test_counts_candidates_and_accepted(self):
        findings = [
            {"severity": "low", "file": "a.py", "line": 1},
            {"severity": "low", "file": "a.py", "line": 2},
        ]
        accepted = [findings[0]]

        metrics = compute_quality_metrics(findings, accepted, {})

        self.assertEqual(metrics["candidate_findings"], 2)
        self.assertEqual(metrics["accepted_findings"], 1)
        self.assertEqual(metrics["filtered_findings"], 1)
        self.assertEqual(metrics["located_findings"], 1)

    def test_static_and_context_evidence_are_counted(self):
        findings = [
            {"evidence_type": "static_check"},
            {"evidence_type": "tool_verified"},
            {"evidence_type": "reviewer_context"},
            {"evidence_type": "reviewer"},
        ]

        metrics = compute_quality_metrics(findings, findings, {})

        self.assertEqual(metrics["static_evidence_findings"], 2)
        self.assertEqual(metrics["reviewer_context_findings"], 1)

    def test_truncated_outputs_are_counted_across_reviewers(self):
        reviewer_outputs = {
            "style_reviewer": {
                "attempts": [
                    {"stage": "primary", "output": "x", "truncated": False},
                    {"stage": "repair", "output": "y" * 30000, "truncated": True},
                ]
            },
            "security_reviewer": {
                "attempts": [
                    {"stage": "primary", "output": "z", "truncated": True},
                ]
            },
        }

        metrics = compute_quality_metrics([], [], reviewer_outputs)

        self.assertEqual(metrics["truncated_outputs"], 2)


class BuildQualityChecksTests(unittest.TestCase):
    def test_filtered_findings_produce_gate_warning(self):
        checks = build_quality_checks(
            {"filtered_findings": 3, "reviewer_context_findings": 0}
        )

        self.assertEqual(len(checks), 1)
        self.assertEqual(checks[0]["name"], "finding_gate")
        self.assertEqual(checks[0]["status"], "warning")

    def test_context_findings_produce_review_warning(self):
        checks = build_quality_checks(
            {"filtered_findings": 0, "reviewer_context_findings": 2}
        )

        self.assertEqual(len(checks), 1)
        self.assertEqual(checks[0]["name"], "finding_context")
        self.assertIn("相邻代码", checks[0]["message"])

    def test_clean_metrics_produce_no_checks(self):
        self.assertEqual(
            build_quality_checks({"filtered_findings": 0, "reviewer_context_findings": 0}),
            [],
        )


if __name__ == "__main__":
    unittest.main()
