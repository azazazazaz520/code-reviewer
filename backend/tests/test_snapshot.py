import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app.engine.snapshot import (
    SnapshotError,
    _capture_workspace_state,
    create_review_snapshot,
)
from app.engine.context import select_reviewer_context


class ReviewSnapshotTest(unittest.TestCase):
    def test_workspace_state_derives_untracked_files_from_status(self):
        git_calls = []

        def run_git(repo_path, args, timeout=60):
            git_calls.append(args)
            if args[0] == "status":
                return " M demo.txt\0?? new.txt\0"
            if args[:2] == ["ls-files", "--stage"]:
                return ""
            if args[:2] == ["rev-parse", "HEAD"]:
                return "a" * 40
            raise AssertionError(f"unexpected git command: {args}")

        with patch("app.engine.snapshot._run_git", side_effect=run_git), patch(
            "app.engine.snapshot._run_git_raw", return_value="diff"
        ), patch(
            "app.engine.snapshot._hash_workspace_path", return_value="file-hash"
        ):
            state = _capture_workspace_state("/tmp/repository")

        self.assertEqual(state.untracked_files, ("new.txt",))
        self.assertFalse(any("--others" in args for args in git_calls))

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

    def test_workspace_snapshot_contains_staged_unstaged_and_untracked_changes(self):
        with TemporaryDirectory(prefix="workspace-snapshot-test-") as temp_dir:
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

            (repo / "demo.txt").write_text("staged\n", encoding="utf-8")
            git("add", "demo.txt")
            (repo / "demo.txt").write_text("staged and unstaged\n", encoding="utf-8")
            (repo / "new.txt").write_text("untracked\n", encoding="utf-8")
            before_status = git("status", "--porcelain=v1")

            snapshot = create_review_snapshot(
                str(repo),
                review_type="local",
                source_type="workspace",
                workspace_path=str(repo),
            )
            worktree = Path(snapshot.repo_root)
            try:
                self.assertEqual(
                    (worktree / "demo.txt").read_text(encoding="utf-8"),
                    "staged and unstaged\n",
                )
                self.assertEqual(
                    (worktree / "new.txt").read_text(encoding="utf-8"),
                    "untracked\n",
                )
                self.assertEqual(set(snapshot.changed_files), {"demo.txt", "new.txt"})
                self.assertIn("staged and unstaged", snapshot.raw_diff)
                self.assertEqual(snapshot.workspace_stats["staged_files"], 1)
                self.assertEqual(snapshot.workspace_stats["unstaged_files"], 1)
                self.assertEqual(snapshot.workspace_stats["untracked_files"], 1)
            finally:
                snapshot.cleanup()

            self.assertFalse(worktree.exists())
            self.assertEqual(git("status", "--porcelain=v1"), before_status)

    def test_workspace_change_during_capture_is_rejected(self):
        with TemporaryDirectory(prefix="workspace-race-test-") as temp_dir:
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
            (repo / "demo.txt").write_text("first\n", encoding="utf-8")

            from app.engine import snapshot as snapshot_module

            original_apply = snapshot_module._apply_workspace_changes

            def apply_and_change_source(repo_path, worktree, state):
                original_apply(repo_path, worktree, state)
                (repo / "demo.txt").write_text("changed during capture\n", encoding="utf-8")

            with patch.object(
                snapshot_module,
                "_apply_workspace_changes",
                side_effect=apply_and_change_source,
            ):
                with self.assertRaisesRegex(SnapshotError, "工作区在采集期间发生变化"):
                    create_review_snapshot(
                        str(repo),
                        review_type="local",
                        source_type="workspace",
                        workspace_path=str(repo),
                    )


if __name__ == "__main__":
    unittest.main()
