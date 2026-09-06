"""审查代码数据库的 revision 绑定和提取状态测试。"""

import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from app.engine.code_database import build_review_code_database


class CodeDatabaseTests(unittest.TestCase):
    def _git(self, repo: Path, *args: str) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=repo,
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()

    def test_build_binds_database_to_snapshot_revision(self):
        with tempfile.TemporaryDirectory(prefix="code-database-test-") as temp_dir:
            repo = Path(temp_dir)
            self._git(repo, "init", "-q", "-b", "main")
            self._git(repo, "config", "user.email", "test@example.com")
            self._git(repo, "config", "user.name", "Code Database Test")
            (repo / "app.py").write_text(
                "def load_value():\n    return 1\n",
                encoding="utf-8",
            )
            self._git(repo, "add", ".")
            self._git(repo, "commit", "-qm", "initial")
            revision = self._git(repo, "rev-parse", "HEAD")
            base_revision = revision

            database = build_review_code_database(
                str(repo),
                revision,
                base_revision,
            )

            self.assertTrue(database.ready)
            self.assertEqual(database.revision, revision)
            self.assertEqual(database.base_revision, base_revision)
            self.assertTrue(database.database_id.startswith(f"crg-{revision[:12]}-"))
            self.assertTrue(Path(database.database_path).is_file())
            self.assertGreaterEqual(database.extracted_files, 1)
            database.verify()
            context = database.get_review_context(["app.py"])

            self.assertEqual(context["status"], "ok")

    def test_database_failure_is_observable(self):
        with mock.patch(
            "code_review_graph.tools.build.build_or_update_graph",
            side_effect=RuntimeError("parser unavailable"),
        ):
            database = build_review_code_database(".", "revision", "base")

        self.assertEqual(database.database_status, "failed")
        self.assertEqual(database.extraction_status, "failed")
        self.assertTrue(database.extraction_errors)

    def test_empty_repository_is_ready_with_zero_extracted_files(self):
        with tempfile.TemporaryDirectory(prefix="code-database-empty-test-") as temp_dir:
            repo = Path(temp_dir)
            self._git(repo, "init", "-q", "-b", "main")

            database = build_review_code_database(repo, "revision", "base")

        self.assertTrue(database.ready)
        self.assertEqual(database.planned_files, 0)
        self.assertEqual(database.extracted_files, 0)
        self.assertEqual(database.extraction_status, "complete")
        self.assertEqual(database.extraction_errors, [])

    def test_failed_files_are_not_counted_twice_in_planned_files(self):
        with tempfile.TemporaryDirectory(prefix="code-database-count-test-") as temp_dir:
            database_path = Path(temp_dir) / "graph.db"
            database_path.touch()
            fake_store = mock.MagicMock()
            fake_store.__enter__.return_value = fake_store
            fake_store.get_stats.return_value = SimpleNamespace(
                files_count=1,
                total_nodes=1,
                total_edges=0,
                nodes_by_kind={},
                edges_by_kind={},
                languages={},
            )
            fake_store.get_all_files.return_value = ["ok.py"]

            with (
                mock.patch(
                    "code_review_graph.incremental.get_db_path",
                    return_value=database_path,
                ),
                mock.patch(
                    "code_review_graph.tools.build.build_or_update_graph",
                    return_value={
                        "files_parsed": 2,
                        "errors": [{"file": "broken.py", "error": "parse failed"}],
                    },
                ),
                mock.patch("code_review_graph.graph.GraphStore", return_value=fake_store),
            ):
                database = build_review_code_database(temp_dir, "revision", "base")

        self.assertEqual(database.planned_files, 2)
        self.assertEqual(database.extracted_files, 1)
        self.assertEqual(database.extraction_status, "partial")
        self.assertEqual(len(database.extraction_errors), 1)


if __name__ == "__main__":
    unittest.main()
