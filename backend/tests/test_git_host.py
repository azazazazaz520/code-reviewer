import unittest
from unittest.mock import Mock, patch

from app.services.git_host import (
    get_open_pulls,
    get_pull_diff,
    parse_git_repository,
    pull_sha,
)


class GitHostTest(unittest.TestCase):
    def test_parse_gitee_https_url_and_injects_token_for_clone(self):
        with patch("app.services.git_host.settings.gitee_token", "token/with+chars"):
            repository = parse_git_repository("https://gitee.com/acme/demo.git")

        self.assertEqual(repository.provider, "gitee")
        self.assertEqual(repository.owner, "acme")
        self.assertEqual(repository.name, "demo")
        self.assertEqual(
            repository.clone_url("https://gitee.com/acme/demo.git"),
            "https://oauth2:token%2Fwith%2Bchars@gitee.com/acme/demo.git",
        )

    @patch("app.services.git_host.requests.get")
    def test_gitee_open_pulls_uses_v5_api_and_access_token(self, get):
        response = Mock()
        response.status_code = 200
        response.json.return_value = [
            {
                "number": 7,
                "title": "Improve review",
                "created_at": "2026-08-03T00:00:00+08:00",
                "head": {"ref": "feature/review"},
            }
        ]
        get.return_value = response

        with patch("app.services.git_host.settings.gitee_token", "gitee-token"):
            pulls = get_open_pulls("git@gitee.com:acme/demo.git")

        self.assertEqual(pulls[0]["number"], 7)
        request = get.call_args
        self.assertEqual(request.args[0], "https://gitee.com/api/v5/repos/acme/demo/pulls")
        self.assertEqual(request.kwargs["params"]["access_token"], "gitee-token")

    @patch("app.services.git_host.get_pull_files")
    def test_gitee_diff_is_built_from_pull_file_patches(self, get_files):
        get_files.return_value = [
            {"filename": "src/app.py", "patch": "@@ -1 +1 @@\n-old\n+new"}
        ]

        diff = get_pull_diff("https://gitee.com/acme/demo", 3)

        self.assertIn("diff --git a/src/app.py b/src/app.py", diff)
        self.assertIn("+new", diff)

    def test_pull_sha_accepts_gitee_commit_id_fallback(self):
        self.assertEqual(pull_sha({"head": {"commit_id": "abc123"}}, "head"), "abc123")


if __name__ == "__main__":
    unittest.main()
