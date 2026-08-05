import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.engine.snapshot import create_review_snapshot
from app.engine.context import select_reviewer_context


class ReviewSnapshotTest(unittest.TestCase):
    def test_reviewer_context_prioritizes_changed_files_and_caps_budget(self):
        selected = select_reviewer_context(
            {"related.py": "r" * 100, "changed.py": "c" * 100},
            ["changed.py"],
            "style_reviewer",
        )

        self.assertEqual(list(selected), ["changed.py", "related.py"])
        self.assertLessEqual(sum(map(len, selected.values())), 12000)

    def test_local_commit_uses_one_revision_and_cleans_worktree(self):
        with TemporaryDirectory(prefix="snapshot-test-") as temp_dir:
            repo = Path(temp_dir)

            def git(*args: str) -> str:
                result = subprocess.run(
                    ["git", *args],
                    cwd=repo,
                    check=True,
                    capture_output=True,
                    text=True,
                )
                return result.stdout.strip()

            git("init", "-q", "-b", "main")
            git("config", "user.email", "test@example.com")
            git("config", "user.name", "Snapshot Test")
            (repo / "demo.txt").write_text("before\n", encoding="utf-8")
            git("add", "demo.txt")
            git("commit", "-qm", "initial")

            (repo / "demo.txt").write_text("after\n", encoding="utf-8")
            (repo / "new.txt").write_text("new\n", encoding="utf-8")
            git("add", ".")
            git("commit", "-qm", "change")
            revision = git("rev-parse", "HEAD")

            snapshot = create_review_snapshot(
                str(repo), review_type="local", commit_hash=revision
            )
            worktree = Path(snapshot.repo_root)
            try:
                self.assertEqual(snapshot.revision, revision)
                self.assertEqual(
                    (worktree / "demo.txt").read_text(encoding="utf-8"), "after\n"
                )
                self.assertEqual(set(snapshot.changed_files), {"demo.txt", "new.txt"})
                self.assertIn("after", snapshot.raw_diff)
            finally:
                snapshot.cleanup()

            self.assertFalse(worktree.exists())

    def test_local_branch_selects_branch_tip_when_commit_is_omitted(self):
        with TemporaryDirectory(prefix="snapshot-branch-test-") as temp_dir:
            repo = Path(temp_dir)

            def git(*args: str) -> str:
                result = subprocess.run(
                    ["git", *args],
                    cwd=repo,
                    check=True,
                    capture_output=True,
                    text=True,
                )
                return result.stdout.strip()

            git("init", "-q", "-b", "main")
            git("config", "user.email", "test@example.com")
            git("config", "user.name", "Snapshot Test")
            (repo / "demo.txt").write_text("main\n", encoding="utf-8")
            git("add", "demo.txt")
            git("commit", "-qm", "initial")
            git("switch", "-c", "feature/review")
            (repo / "demo.txt").write_text("feature\n", encoding="utf-8")
            git("add", "demo.txt")
            git("commit", "-qm", "feature change")

            snapshot = create_review_snapshot(
                str(repo), review_type="local", branch="feature/review"
            )
            worktree = Path(snapshot.repo_root)
            try:
                self.assertEqual(
                    (worktree / "demo.txt").read_text(encoding="utf-8"), "feature\n"
                )
                self.assertIn("feature", snapshot.raw_diff)
            finally:
                snapshot.cleanup()

            self.assertFalse(worktree.exists())


if __name__ == "__main__":
    unittest.main()
