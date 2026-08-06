import unittest
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi import HTTPException

from app.api.repos import create_repo
from app.engine.snapshot import SnapshotError, _fetch_revision, _resolve_revision
from app.models.schemas import RepoCreate
from app.services.repo_sync import RepoSyncError, resolve_revision


class GitArgumentSecurityTests(unittest.TestCase):
    def test_create_repo_rejects_option_like_clone_url_before_git(self):
        with TemporaryDirectory(prefix="clone-security-test-") as temp_dir:
            with patch("app.api.repos.settings.repos_dir", temp_dir), patch(
                "app.api.repos.subprocess.run"
            ) as run:
                with self.assertRaisesRegex(HTTPException, "Git 仓库地址"):
                    create_repo(
                        RepoCreate(
                            name="malicious",
                            git_url="--upload-pack=echo https://example.invalid/repo.git",
                        ),
                        db=None,
                    )

            run.assert_not_called()

    @patch("app.engine.snapshot._run_git", return_value="resolved-sha")
    def test_resolve_revision_terminates_git_options(self, run_git):
        resolved = _resolve_revision("/tmp/repository", "--help")

        self.assertEqual(resolved, "resolved-sha")
        run_git.assert_called_once_with(
            "/tmp/repository",
            ["rev-parse", "--verify", "--end-of-options", "--help^{commit}"],
        )

    @patch("app.engine.snapshot._run_git")
    def test_fetch_revision_rejects_option_like_revision_before_git(self, run_git):
        with self.assertRaisesRegex(SnapshotError, "revision"):
            _fetch_revision("/tmp/repository", "--upload-pack=echo")

        run_git.assert_not_called()

    @patch("app.services.repo_sync._run_git")
    def test_repo_sync_revision_rejects_option_like_revision_before_git(self, run_git):
        with self.assertRaisesRegex(RepoSyncError, "Commit SHA"):
            resolve_revision("/tmp/repository", "--upload-pack=echo")

        run_git.assert_not_called()


if __name__ == "__main__":
    unittest.main()
