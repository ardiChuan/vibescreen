#!/usr/bin/env python3
"""Set VibePulse's bounded Codex MCP tool timeout without touching peers."""

from __future__ import annotations

import os
from pathlib import Path
import re
import stat
import tempfile
import tomllib


TOOL_TIMEOUT_SECONDS = 130
MAX_CONFIG_BYTES = 1024 * 1024
_SECTION = re.compile(
    r"(?m)^\[mcp_servers\.vibepulse\][ \t]*(?:#[^\r\n]*)?(?:\r?\n|$)")
_NEXT_SECTION = re.compile(r"(?m)^\[")
_TIMEOUT = re.compile(
    r"(?m)^[ \t]*tool_timeout_sec[ \t]*=[^\r\n]*(?P<cr>\r?)$")


class TimeoutConfigError(ValueError):
    pass


def default_config_path() -> Path:
    root = os.environ.get("CODEX_HOME")
    return ((Path(root) if root else Path.home() / ".codex") /
            "config.toml")


def _read_regular(path: Path) -> tuple[bytes, int, os.stat_result]:
    try:
        before = os.lstat(path)
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
            raise TimeoutConfigError("config must be a regular file")
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | \
            getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        fd = os.open(path, flags)
        try:
            opened = os.fstat(fd)
            after = os.lstat(path)
            if (not stat.S_ISREG(opened.st_mode) or
                    stat.S_ISLNK(after.st_mode) or
                    not os.path.samestat(before, opened) or
                    not os.path.samestat(opened, after)):
                raise TimeoutConfigError("config changed while opening")
            raw = os.read(fd, MAX_CONFIG_BYTES + 1)
        finally:
            os.close(fd)
    except OSError as exc:
        raise TimeoutConfigError("cannot read Codex config") from exc
    if len(raw) > MAX_CONFIG_BYTES:
        raise TimeoutConfigError("Codex config is too large")
    return raw, stat.S_IMODE(before.st_mode), before


def _updated_text(text: str) -> str:
    try:
        before = tomllib.loads(text)
    except (tomllib.TOMLDecodeError, ValueError) as exc:
        raise TimeoutConfigError("Codex config is invalid TOML") from exc
    server = before.get("mcp_servers", {}).get("vibepulse")
    if not isinstance(server, dict):
        raise TimeoutConfigError("VibePulse MCP section is missing")

    sections = list(_SECTION.finditer(text))
    if len(sections) != 1:
        raise TimeoutConfigError("VibePulse MCP section is ambiguous")
    section = sections[0]
    next_section = _NEXT_SECTION.search(text, section.end())
    end = next_section.start() if next_section else len(text)
    body = text[section.end():end]
    timeouts = list(_TIMEOUT.finditer(body))
    if len(timeouts) > 1:
        raise TimeoutConfigError("VibePulse MCP timeout is ambiguous")

    line = f"tool_timeout_sec = {TOOL_TIMEOUT_SECONDS}"
    if timeouts:
        match = timeouts[0]
        start = section.end() + match.start()
        finish = section.end() + match.end()
        updated = (text[:start] + line + match.group("cr") +
                   text[finish:])
    else:
        newline = "\r\n" if "\r\n" in section.group(0) else "\n"
        if not section.group(0).endswith(("\n", "\r")):
            line = newline + line
        updated = text[:section.end()] + line + newline + text[section.end():]

    try:
        after = tomllib.loads(updated)
    except (tomllib.TOMLDecodeError, ValueError) as exc:
        raise TimeoutConfigError("updated Codex config is invalid") from exc
    configured = after.get("mcp_servers", {}).get("vibepulse", {})
    if configured.get("tool_timeout_sec") != TOOL_TIMEOUT_SECONDS:
        raise TimeoutConfigError("VibePulse MCP timeout did not persist")
    return updated


def configure(path: Path) -> None:
    path = Path(path)
    raw, mode, original = _read_regular(path)
    try:
        text = raw.decode("utf-8", "strict")
    except UnicodeError as exc:
        raise TimeoutConfigError("Codex config is not UTF-8") from exc
    updated = _updated_text(text)
    if updated == text:
        return

    temporary = None
    try:
        fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        temporary = Path(name)
        if hasattr(os, "fchmod"):
            os.fchmod(fd, mode)
        with os.fdopen(fd, "wb") as handle:
            handle.write(updated.encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        current = os.lstat(path)
        if (stat.S_ISLNK(current.st_mode) or
                not os.path.samestat(original, current)):
            raise TimeoutConfigError("Codex config changed during update")
        os.replace(temporary, path)
        temporary = None
    except OSError as exc:
        raise TimeoutConfigError("cannot save Codex config") from exc
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except OSError:
                pass


def main() -> int:
    try:
        configure(default_config_path())
    except TimeoutConfigError:
        print("FIX Codex MCP tool timeout could not be configured")
        return 1
    print("PASS Codex MCP tool timeout")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
