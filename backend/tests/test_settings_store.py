import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.services.settings_store import (
    SETTINGS_SCHEMA_VERSION,
    SettingsStore,
    SettingsStoreError,
    SettingsVersionConflict,
)


class SettingsStoreTests(unittest.TestCase):
    def test_saves_atomically_and_increments_version(self):
        with TemporaryDirectory() as directory:
            store = SettingsStore(Path(directory) / "settings.json")
            first = store.save({"llm": {"model": "one"}}, expected_version=0)
            second = store.save({"llm": {"model": "two"}}, expected_version=first.config_version)

            self.assertEqual(first.config_version, 1)
            self.assertEqual(second.config_version, 2)
            self.assertEqual(store.load().settings["llm"]["model"], "two")

    def test_rejects_stale_version_without_overwriting_newer_configuration(self):
        with TemporaryDirectory() as directory:
            store = SettingsStore(Path(directory) / "settings.json")
            store.save({"llm": {"model": "one"}}, expected_version=0)

            with self.assertRaises(SettingsVersionConflict):
                store.save({"llm": {"model": "two"}}, expected_version=0)
            self.assertEqual(store.load().settings["llm"]["model"], "one")

    def test_rejects_corrupt_or_unsupported_file(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text(json.dumps({"schema_version": SETTINGS_SCHEMA_VERSION + 1}), encoding="utf-8")

            with self.assertRaises(SettingsStoreError):
                SettingsStore(path).load()


if __name__ == "__main__":
    unittest.main()
