import dataclasses
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.tokenserver.vibepulse_config import (
    ConfigError,
    VibePulseConfig,
    load,
    load_config,
    save,
    save_config,
)


class SavedConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="vibepulse-config-")
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "state" / "config.json"

    def test_missing_file_is_fully_off_and_immutable(self):
        config = load_config(self.path)

        self.assertEqual(config, VibePulseConfig())
        self.assertFalse(config.claude_interactions)
        self.assertFalse(config.codex_interactions)
        self.assertFalse(config.interaction_detail)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            config.codex_interactions = True

    def test_valid_partial_and_complete_files_load_strict_booleans(self):
        self.path.parent.mkdir()
        self.path.write_text(
            '{"codex_interactions":true}', encoding="utf-8")
        self.assertEqual(load(self.path), VibePulseConfig(
            codex_interactions=True))

        self.path.write_text(json.dumps({
            "claude_interactions": True,
            "codex_interactions": False,
            "interaction_detail": True,
        }), encoding="utf-8")
        self.assertEqual(load_config(self.path), VibePulseConfig(
            claude_interactions=True, interaction_detail=True))

    def test_round_trip_uses_only_the_public_non_secret_schema(self):
        expected = VibePulseConfig(
            claude_interactions=True,
            codex_interactions=True,
            interaction_detail=True,
        )

        save_config(self.path, expected)

        self.assertEqual(load_config(self.path), expected)
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), {
            "claude_interactions": True,
            "codex_interactions": True,
            "interaction_detail": True,
        })
        self.assertNotIn("key", self.path.read_text(encoding="utf-8").lower())

    def test_unknown_duplicate_malformed_and_non_object_json_are_rejected(self):
        invalid_documents = (
            '{"unknown":false}',
            '{"codex_interactions":true,"codex_interactions":false}',
            '{',
            '[]',
            'null',
            '"off"',
        )
        self.path.parent.mkdir()
        for document in invalid_documents:
            with self.subTest(document=document):
                self.path.write_text(document, encoding="utf-8")
                with self.assertRaises(ConfigError):
                    load_config(self.path)

    def test_every_non_boolean_value_is_rejected_without_truthiness(self):
        self.path.parent.mkdir()
        for field in (
                "claude_interactions", "codex_interactions",
                "interaction_detail"):
            for value in (0, 1, "true", [], {}, None):
                with self.subTest(field=field, value=value):
                    self.path.write_text(
                        json.dumps({field: value}), encoding="utf-8")
                    with self.assertRaises(ConfigError):
                        load_config(self.path)

    def test_save_creates_private_directory_and_file_where_supported(self):
        save(self.path, VibePulseConfig(codex_interactions=True))

        if os.name == "posix":
            self.assertEqual(stat.S_IMODE(self.path.parent.stat().st_mode),
                             0o700)
            self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)

    def test_save_atomically_replaces_the_destination_from_same_directory(self):
        self.path.parent.mkdir()
        self.path.write_text("old", encoding="utf-8")
        real_replace = os.replace
        calls = []

        def observed_replace(source, destination):
            calls.append((Path(source), Path(destination)))
            self.assertTrue(Path(source).exists())
            self.assertEqual(Path(source).parent, self.path.parent)
            return real_replace(source, destination)

        with mock.patch(
                "tools.tokenserver.vibepulse_config.os.replace",
                side_effect=observed_replace):
            save_config(self.path, VibePulseConfig(
                claude_interactions=True))

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1], self.path)
        self.assertEqual(load_config(self.path), VibePulseConfig(
            claude_interactions=True))
        self.assertEqual(list(self.path.parent.glob(".config.json.*")), [])

    def test_failed_replace_preserves_old_file_and_removes_temporary_file(self):
        self.path.parent.mkdir()
        self.path.write_text(
            '{"codex_interactions":true}', encoding="utf-8")

        with mock.patch(
                "tools.tokenserver.vibepulse_config.os.replace",
                side_effect=OSError("replace failed")):
            with self.assertRaises(ConfigError):
                save_config(self.path, VibePulseConfig(
                    claude_interactions=True))

        self.assertEqual(load_config(self.path), VibePulseConfig(
            codex_interactions=True))
        self.assertEqual(list(self.path.parent.glob(".config.json.*")), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
