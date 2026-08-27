"""Resolve the Codex CLI without mistaking a Windows app alias for it."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import sys
from typing import Callable, Mapping


def _is_windows_app_path(path: str | os.PathLike[str]) -> bool:
    """Return true for Store-managed paths background jobs cannot trust."""
    normalized = str(path).replace("/", "\\").casefold()
    bounded = "\\" + normalized.strip("\\") + "\\"
    return "\\windowsapps\\" in bounded


def resolve_codex_executable(
        *, platform: str | None = None,
        environ: Mapping[str, str] | None = None,
        which: Callable[[str], str | None] = shutil.which,
        is_file: Callable[[str | os.PathLike[str]], bool] = os.path.isfile,
        ) -> str | None:
    """Return a background-safe Codex CLI path for this host.

    OpenAI's standalone Windows installer owns a stable per-user path. It is
    checked before ``PATH`` because the desktop app may also register an app
    alias named ``codex``. That alias can resolve while still failing with
    Access Denied outside the interactive app environment.
    """
    current_platform = sys.platform if platform is None else platform
    current_environ = os.environ if environ is None else environ

    if current_platform == "win32":
        local_app_data = current_environ.get("LOCALAPPDATA")
        if local_app_data:
            standalone = (Path(local_app_data) / "Programs" / "OpenAI" /
                          "Codex" / "bin" / "codex.exe")
            if is_file(standalone):
                return str(standalone)

    executable = which("codex")
    if executable:
        if current_platform == "win32" and _is_windows_app_path(executable):
            return None
        return executable

    if current_platform == "darwin":
        for candidate in (
            "/Applications/ChatGPT.app/Contents/Resources/codex",
            "/Applications/Codex.app/Contents/Resources/codex",
        ):
            if is_file(candidate) and os.access(candidate, os.X_OK):
                return candidate
    return None
