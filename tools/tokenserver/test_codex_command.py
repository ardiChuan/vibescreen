"""Tests for background-safe Codex CLI discovery."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

try:
    from .codex_command import resolve_codex_executable
except ImportError:
    from codex_command import resolve_codex_executable


class CodexCommandTests(unittest.TestCase):
    def test_windows_prefers_official_standalone_over_app_alias(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            expected = (Path(temp_dir) / "Programs" / "OpenAI" / "Codex" /
                        "bin" / "codex.exe")
            expected.parent.mkdir(parents=True)
            expected.touch()

            found = resolve_codex_executable(
                platform="win32", environ={"LOCALAPPDATA": temp_dir},
                which=lambda _name: (
                    r"C:\Program Files\WindowsApps\OpenAI.Codex\codex.exe"))

        self.assertEqual(found, str(expected))

    def test_windows_rejects_store_managed_alias(self):
        found = resolve_codex_executable(
            platform="win32", environ={},
            which=lambda _name: (
                r"C:\Users\Tester\AppData\Local\Microsoft\WindowsApps\codex.exe"))
        self.assertIsNone(found)

    def test_windows_rejects_packaged_app_binary(self):
        found = resolve_codex_executable(
            platform="win32", environ={},
            which=lambda _name: (
                r"C:\Program Files\WindowsApps\OpenAI.Codex_1.0\codex.exe"))
        self.assertIsNone(found)

    def test_normal_path_command_is_accepted(self):
        found = resolve_codex_executable(
            platform="linux", environ={},
            which=lambda _name: "/usr/local/bin/codex")
        self.assertEqual(found, "/usr/local/bin/codex")


if __name__ == "__main__":
    unittest.main()
