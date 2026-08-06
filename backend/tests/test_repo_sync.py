import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.services.repo_sync import resolve_remote_branch, sync_repository
from app.engine.snapshot import create_review_snapshot


class RepoSyncTests(unittest.TestCase):
    def test_remote_branch_wins_over_stale_local_branch(self):
        with TemporaryDirectory(prefix="repo-sync-test-") as temp_dir:
            root = Path(temp_dir)
            bare = root / "remote.git"
            managed = root / "managed"
            developer = root / "developer"

            self._git(root, "init", "--bare", str(bare))
            self._git(root, "clone", str(bare), str(developer))
            self._configure(developer)
            (developer / "demo.txt").write_text("A\n", encoding="utf-8")
            self._git(developer, "add", "demo.txt")
            self._git(developer, "commit", "-m", "initial")
            self._git(developer, "branch", "-M", "main")
            self._git(developer, "push", "-u", "origin", "main")
            self._git(bare, "symbolic-ref", "HEAD", "refs/heads/main")

            self._git(root, "clone", "--branch", "main", str(bare), str(managed))
            initial = self._git(managed, "rev-parse", "HEAD")

            (developer / "demo.txt").write_text("B\n", encoding="utf-8")
            self._git(developer, "add", "demo.txt")
            self._git(developer, "commit", "-m", "remote update")
            self._git(developer, "push", "origin", "main")
            remote_tip = self._git(developer, "rev-parse", "HEAD")

            result = sync_repository(str(managed))

            self.assertEqual(self._git(managed, "rev-parse", "main"), initial)
            self.assertEqual(resolve_remote_branch(str(managed), "main"), remote_tip)
            self.assertEqual(result.default_branch, "main")
            self.assertEqual(result.branches[0].head_revision, remote_tip)

            snapshot = create_review_snapshot(
                str(managed),
                review_type="local",
                source_type="remote_latest",
                branch="main",
            )
            worktree = Path(snapshot.repo_root)
            try:
                self.assertEqual(
                    (worktree / "demo.txt").read_text(encoding="utf-8"), "B\n"
                )
            finally:
                snapshot.cleanup()

    def test_sync_prunes_deleted_remote_branches(self):
        with TemporaryDirectory(prefix="repo-sync-prune-") as temp_dir:
            root = Path(temp_dir)
            bare = root / "remote.git"
            managed = root / "managed"
            developer = root / "developer"

            self._git(root, "init", "--bare", str(bare))
            self._git(root, "clone", str(bare), str(developer))
            self._configure(developer)
            (developer / "demo.txt").write_text("A\n", encoding="utf-8")
            self._git(developer, "add", "demo.txt")
            self._git(developer, "commit", "-m", "initial")
            self._git(developer, "branch", "-M", "main")
            self._git(developer, "push", "-u", "origin", "main")
            self._git(bare, "symbolic-ref", "HEAD", "refs/heads/main")
            self._git(developer, "switch", "-c", "feature/remove-me")
            (developer / "feature.txt").write_text("feature\n", encoding="utf-8")
            self._git(developer, "add", "feature.txt")
            self._git(developer, "commit", "-m", "feature")
            self._git(developer, "push", "-u", "origin", "feature/remove-me")

            self._git(root, "clone", "--branch", "main", str(bare), str(managed))
            first = sync_repository(str(managed))
            self.assertEqual(
                {branch.name for branch in first.branches}, {"main", "feature/remove-me"}
            )

            self._git(developer, "push", "origin", "--delete", "feature/remove-me")
            second = sync_repository(str(managed))
            self.assertEqual({branch.name for branch in second.branches}, {"main"})

    @staticmethod
    def _configure(repo: Path) -> None:
        RepoSyncTests._git(repo, "config", "user.email", "test@example.com")
        RepoSyncTests._git(repo, "config", "user.name", "Repo Sync Test")

    @staticmethod
    def _git(cwd: Path, *args: str) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()


if __name__ == "__main__":
    unittest.main()
