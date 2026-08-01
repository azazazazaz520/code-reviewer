import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from app.engine.finding_gate import filter_findings
from app.engine.reviewers.base import ReviewerOutputError
from app.engine.reviewers.style import StyleReviewer
from app.engine.scope import build_review_plan, classify_files
from app.engine.validators.release import validate_release_manifest
from app.engine.workflow import (
    _generate_report_node,
    _reflection_node,
    _run_reviews_node,
)
from app.engine.workflow import run_workflow


class ReviewQualityTests(unittest.TestCase):
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

        import app.engine.workflow as workflow

        original_registry = workflow.REVIEWER_REGISTRY
        workflow.REVIEWER_REGISTRY = {"style_reviewer": BrokenReviewer()}
        try:
            _run_reviews_node(state)
        finally:
            workflow.REVIEWER_REGISTRY = original_registry

        report_state = _generate_report_node(_reflection_node(state))

        self.assertEqual(report_state["findings"], [])
        self.assertTrue(report_state["report"])
        self.assertEqual(report_state["report"]["review_status"], "degraded")
        self.assertIn("未完整覆盖", report_state["report"]["summary"])
        self.assertEqual(report_state["checks"][0]["status"], "error")
        self.assertEqual(report_state["checks"][0]["name"], "reviewer_style_reviewer")

    def test_invalid_reviewer_json_is_not_silently_treated_as_clean_review(self):
        with self.assertRaises(ReviewerOutputError):
            StyleReviewer()._parse_findings("这不是 JSON")

    def test_reviewer_parser_accepts_common_json_wrappers(self):
        reviewer = StyleReviewer()

        self.assertEqual(reviewer._parse_findings("```JSON\n[]\n```"), [])
        self.assertEqual(
            reviewer._parse_findings("审查结果：{\"findings\": []}"),
            [],
        )

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
