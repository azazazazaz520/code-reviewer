import unittest

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app


class SettingsApiTests(unittest.TestCase):
    def test_returns_versioned_effective_snapshot_without_secret_values(self):
        original_secrets = (
            settings.deepseek_api_key,
            settings.github_token,
            settings.gitee_token,
        )
        settings.deepseek_api_key = "test-deepseek-secret"
        settings.github_token = "test-github-secret"
        settings.gitee_token = "test-gitee-secret"
        try:
            with TestClient(app) as client:
                response = client.get("/api/settings")
        finally:
            (
                settings.deepseek_api_key,
                settings.github_token,
                settings.gitee_token,
            ) = original_secrets

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["schema_version"], 1)
        self.assertEqual(body["config_version"], 0)
        self.assertEqual(body["settings"]["llm"]["provider"], "deepseek-openai-compatible")
        self.assertIn("llm.model", body["sources"])
        self.assertIn(body["sources"]["llm.model"], {"default", "env", "user_file"})
        self.assertIn(body["secret_status"]["llm_api_key"], {"configured", "not_configured"})

        serialized = response.text
        for value in ("test-deepseek-secret", "test-github-secret", "test-gitee-secret"):
            self.assertNotIn(value, serialized)
        self.assertNotIn("database_url", serialized)
        self.assertNotIn("reviewer_timeout_seconds", serialized)

    def test_settings_endpoint_does_not_accept_write_operations_in_p0(self):
        with TestClient(app) as client:
            response = client.patch("/api/settings", json={"settings": {}})

        self.assertEqual(response.status_code, 405)


if __name__ == "__main__":
    unittest.main()
