import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.services.settings_service import SettingsService
from app.services.settings_store import SettingsStore


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

    def test_llm_connection_uses_fixed_short_response_budget(self):
        original_api_key = settings.deepseek_api_key
        settings.deepseek_api_key = "test-deepseek-secret"
        provider = MagicMock()
        configured_values = (1, 7, 8, 4096)
        try:
            with patch("app.api.settings.LLMProvider", return_value=provider):
                with TestClient(app) as client:
                    responses = [
                        client.post(
                            "/api/settings/test/llm",
                            json={"max_tokens": value},
                        )
                        for value in configured_values
                    ]
        finally:
            settings.deepseek_api_key = original_api_key

        self.assertEqual([response.status_code for response in responses], [200] * len(configured_values))
        self.assertEqual(
            [call.kwargs["max_tokens"] for call in provider.chat.call_args_list],
            [8] * len(configured_values),
        )

    def test_settings_endpoint_saves_user_configuration(self):
        original_model = settings.llm_model
        try:
            with TemporaryDirectory() as directory:
                service = SettingsService(SettingsStore(Path(directory) / "settings.json"))
                with patch("app.api.settings.get_settings_service", return_value=service), patch(
                    "app.api.settings.refresh_runtime_consumers"
                ):
                    with TestClient(app) as client:
                        response = client.patch(
                            "/api/settings",
                            json={
                                "expected_version": 0,
                                "settings": {"llm": {"model": "test-model"}},
                            },
                        )
        finally:
            settings.llm_model = original_model

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["config_version"], 1)
        self.assertEqual(body["snapshot"]["settings"]["llm"]["model"], "test-model")
        self.assertEqual(body["changed"][0]["path"], "llm.model")

    def test_settings_endpoint_rejects_stale_version(self):
        original_model = settings.llm_model
        try:
            with TemporaryDirectory() as directory:
                service = SettingsService(SettingsStore(Path(directory) / "settings.json"))
                with patch("app.api.settings.get_settings_service", return_value=service), patch(
                    "app.api.settings.refresh_runtime_consumers"
                ):
                    with TestClient(app) as client:
                        first = client.patch(
                            "/api/settings",
                            json={"expected_version": 0, "settings": {"llm": {"model": "one"}}},
                        )
                        stale = client.patch(
                            "/api/settings",
                            json={"expected_version": 0, "settings": {"llm": {"model": "two"}}},
                        )
        finally:
            settings.llm_model = original_model

        self.assertEqual(first.status_code, 200)
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(stale.json()["detail"]["code"], "settings_version_conflict")


if __name__ == "__main__":
    unittest.main()
