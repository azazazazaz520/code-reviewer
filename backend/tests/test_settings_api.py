import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.services.settings_policy import ReviewSettingsPatch
from app.services.settings_service import SettingsService
from app.services.settings_store import SettingsStore


class SettingsApiTests(unittest.TestCase):
    def test_review_context_settings_reject_values_above_runtime_hard_limit(self):
        with self.assertRaises(ValueError):
            ReviewSettingsPatch(review_context_max_files=21)
        with self.assertRaises(ValueError):
            ReviewSettingsPatch(review_context_max_chars=60_001)

    def test_existing_settings_above_hard_limit_are_migrated_in_memory(self):
        original_limits = (
            settings.review_context_max_files,
            settings.review_context_max_chars,
        )
        try:
            with TemporaryDirectory() as directory:
                store = SettingsStore(Path(directory) / "settings.json")
                store.save(
                    {
                        "review": {
                            "review_context_max_files": 500,
                            "review_context_max_chars": 2_000_000,
                        }
                    },
                    expected_version=None,
                )
                snapshot = SettingsService(store).initialize()
        finally:
            (
                settings.review_context_max_files,
                settings.review_context_max_chars,
            ) = original_limits

        self.assertEqual(snapshot.settings.review.review_context_max_files, 20)
        self.assertEqual(snapshot.settings.review.review_context_max_chars, 60_000)

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
        self.assertEqual(body["schema_version"], 2)
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

    def test_legacy_review_flow_settings_are_migrated(self):
        with TemporaryDirectory() as directory:
            store = SettingsStore(Path(directory) / "settings.json")
            store.save(
                {
                    "llm": {
                        "tool_selection_max_tokens": 3000,
                        "tool_round_max_tokens": 2000,
                        "finalize_retry_max_tokens": 900,
                    },
                    "review": {
                        "review_unit_max_chars": 16000,
                        "review_context_max_files": 500,
                        "review_context_max_chars": 2_000_000,
                        "max_reflection_rounds": 3,
                        "max_tool_rounds": 2,
                    },
                },
                expected_version=None,
            )

            snapshot = SettingsService(store).initialize()

        self.assertEqual(snapshot.settings.llm.review_max_tokens, 3000)
        self.assertEqual(snapshot.settings.llm.supplement_max_tokens, 2000)
        self.assertEqual(snapshot.settings.llm.json_repair_max_tokens, 900)
        self.assertEqual(snapshot.settings.review.review_batch_max_chars, 16000)
        self.assertEqual(snapshot.settings.review.review_context_max_files, 20)
        self.assertEqual(snapshot.settings.review.review_context_max_chars, 60000)

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
