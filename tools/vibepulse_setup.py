#!/usr/bin/env python3
"""Install and inspect the optional local VibePulse Codex integration."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Callable, Sequence
import urllib.request


TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from tokenserver.vibepulse_config import (  # noqa: E402
    ConfigError,
    VibePulseConfig,
    config_lock,
    load_config,
    save_config,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
MARKETPLACE_NAME = "torget"
TOKEN_SERVER_URL = "http://127.0.0.1:8737/"
MAX_DIAGNOSTIC_BYTES = 16 * 1024
COMMAND_TIMEOUT_SECONDS = 15
NETWORK_TIMEOUT_SECONDS = 2
_AUTO = object()

_KNOWN_ABSENT = {
    ("mcp", "remove"): "MCP server 'vibepulse' is not configured",
    ("plugin", "remove"): "plugin 'vibepulse@torget' is not installed",
    ("plugin", "marketplace", "remove"):
        "marketplace 'torget' is not configured",
}


def default_config_path() -> Path:
    """Return the tokenserver's existing saved interaction config path."""
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA")
        base = Path(local) if local else Path.home() / "AppData" / "Local"
        return base / "VibePulse" / "config.json"
    return (Path.home() / "Library" / "Application Support" / "VibePulse" /
            "config.json")


def plan_codex_install(
        repo_root: Path, python: Path, codex: Path,
        marketplace_name: str = MARKETPLACE_NAME) -> list[list[str]]:
    """Build the exact shell-free Codex installation plan."""
    root = Path(repo_root).resolve()
    python_path = str(Path(python).resolve())
    codex_path = str(Path(codex).resolve())
    marketplace_root = root / ".agents" / "plugins"
    mcp_server = (marketplace_root / "plugins" / "vibepulse" / "scripts" /
                  "mcp_server.py")
    return [
        [codex_path, "plugin", "marketplace", "add",
         str(marketplace_root)],
        [codex_path, "plugin", "add",
         f"vibepulse@{marketplace_name}"],
        [codex_path, "mcp", "remove", "vibepulse"],
        [codex_path, "mcp", "add", "vibepulse", "--", python_path,
         str(mcp_server)],
    ]


def plan_codex_uninstall(
        codex: Path, marketplace_name: str = MARKETPLACE_NAME,
        ) -> list[list[str]]:
    codex_path = str(Path(codex).resolve())
    return [
        [codex_path, "mcp", "remove", "vibepulse"],
        [codex_path, "plugin", "remove",
         f"vibepulse@{marketplace_name}"],
        [codex_path, "plugin", "marketplace", "remove", marketplace_name],
    ]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    install = commands.add_parser(
        "install", help="install the package and save explicit providers")
    install.add_argument(
        "--providers", choices=("off", "claude", "codex", "both"),
        help="providers to enable; omitted non-interactively means off")
    detail = install.add_mutually_exclusive_group()
    detail.add_argument(
        "--detail", dest="detail", action="store_true",
        help="send bounded question/command detail to the local panel")
    detail.add_argument(
        "--no-detail", dest="detail", action="store_false",
        help="keep question/command detail on this computer")
    install.set_defaults(detail=None)

    commands.add_parser("status", help="show saved provider switches")
    commands.add_parser("doctor", help="run read-only local diagnostics")

    disable = commands.add_parser(
        "disable", help="disable one or all provider routes")
    disable.add_argument("target", choices=("codex", "claude", "all"))

    uninstall = commands.add_parser(
        "uninstall", help="remove only the selected Codex integration")
    uninstall.add_argument("target", choices=("codex",))
    return parser


def _interactive_providers(input_fn: Callable[[str], str]) -> str:
    prompt = (
        "Choose VibePulse panel providers "
        "[off/claude/codex/both] (default off): ")
    while True:
        choice = input_fn(prompt).strip().lower() or "off"
        if choice in {"off", "claude", "codex", "both"}:
            return choice


def _interactive_detail(input_fn: Callable[[str], str]) -> bool:
    prompt = (
        "Send bounded question and command detail to the local panel? "
        "[y/N]: ")
    while True:
        choice = input_fn(prompt).strip().lower()
        if choice in {"", "n", "no"}:
            return False
        if choice in {"y", "yes"}:
            return True


def _chosen_config(providers: str, detail: bool) -> VibePulseConfig:
    return VibePulseConfig(
        claude_interactions=providers in {"claude", "both"},
        codex_interactions=providers in {"codex", "both"},
        interaction_detail=detail,
    )


def _save_choice(path: Path, config: VibePulseConfig) -> None:
    with config_lock(path):
        # Strictly validate existing state before replacing the three owned
        # switches. This refuses malformed or symlinked state fail-closed.
        load_config(path)
        save_config(path, config)


def _disable(path: Path, target: str) -> None:
    with config_lock(path):
        saved = load_config(path)
        save_config(path, VibePulseConfig(
            claude_interactions=(saved.claude_interactions
                                 if target == "codex" else False),
            codex_interactions=(saved.codex_interactions
                                if target == "claude" else False),
            interaction_detail=saved.interaction_detail,
        ))


def _known_absent(argv: Sequence[str], stderr: str) -> bool:
    command = tuple(argv[1:-1])
    return _KNOWN_ABSENT.get(command) == stderr.strip()


def _run_commands(
        commands: Sequence[Sequence[str]], run: Callable[..., object],
        stdout, *, allow_absent: bool) -> bool:
    for argv_value in commands:
        argv = [str(value) for value in argv_value]
        try:
            completed = run(
                argv, capture_output=True, text=True,
                timeout=COMMAND_TIMEOUT_SECONDS, check=False, shell=False)
        except (OSError, subprocess.SubprocessError):
            print(f"FIX Command failed: {' '.join(argv[1:])}", file=stdout)
            return False
        returncode = getattr(completed, "returncode", 1)
        stderr = getattr(completed, "stderr", "") or ""
        if returncode != 0 and not (
                allow_absent and _known_absent(argv, stderr)):
            print(f"FIX Command failed: {' '.join(argv[1:])}", file=stdout)
            return False
    return True


def _print_status(config: VibePulseConfig, stdout) -> None:
    def switch(value: bool) -> str:
        return "ON" if value else "OFF"

    print(f"Claude: {switch(config.claude_interactions)}", file=stdout)
    print(f"Codex: {switch(config.codex_interactions)}", file=stdout)
    print(f"Detail: {switch(config.interaction_detail)}", file=stdout)


def _command_output(
        argv: list[str], run: Callable[..., object]) -> tuple[bool, str]:
    try:
        completed = run(
            argv, capture_output=True, text=True,
            timeout=COMMAND_TIMEOUT_SECONDS, check=False, shell=False)
    except (OSError, subprocess.SubprocessError):
        return False, ""
    if getattr(completed, "returncode", 1) != 0:
        return False, ""
    return True, getattr(completed, "stdout", "") or ""


def _doctor(
        config: VibePulseConfig, *, python: Path | None, codex: Path | None,
        run: Callable[..., object], urlopen: Callable[..., object], stdout,
        ) -> bool:
    fixes = False

    if python is None or not Path(python).is_file():
        print("FIX Python executable: install Python 3.11 or newer", file=stdout)
        fixes = True
    else:
        print("PASS Python executable", file=stdout)

    if not config.codex_interactions:
        print("OFF Codex executable: provider intentionally disabled",
              file=stdout)
    elif codex is None:
        print("FIX Codex executable: install or expose codex on PATH", file=stdout)
        fixes = True
    else:
        print("PASS Codex executable", file=stdout)

    if not config.codex_interactions:
        print("OFF Codex plugin: provider intentionally disabled", file=stdout)
        print("OFF Codex MCP: provider intentionally disabled", file=stdout)
        print("OFF Hook review: provider intentionally disabled", file=stdout)
    elif codex is None:
        print("FIX Codex plugin: cannot inspect without Codex", file=stdout)
        print("FIX Codex MCP: cannot inspect without Codex", file=stdout)
        print("FIX Hook review: cannot inspect without Codex", file=stdout)
        fixes = True
    else:
        codex_text = str(Path(codex).resolve())
        plugin_ok, plugin_output = _command_output(
            [codex_text, "plugin", "list"], run)
        if plugin_ok and "vibepulse" in plugin_output.lower():
            print("PASS Codex plugin", file=stdout)
        else:
            print("FIX Codex plugin: install vibepulse@torget", file=stdout)
            fixes = True

        mcp_ok, mcp_output = _command_output(
            [codex_text, "mcp", "list"], run)
        if mcp_ok and "vibepulse" in mcp_output.lower():
            print("PASS Codex MCP", file=stdout)
        else:
            print("FIX Codex MCP: register the local bridge", file=stdout)
            fixes = True

        if (plugin_ok and "vibepulse" in plugin_output.lower() and
                "trusted" in plugin_output.lower()):
            print("PASS Hook review", file=stdout)
        else:
            print("FIX Hook review: inspect and trust exact commands in /hooks",
                  file=stdout)
            fixes = True

    if not (config.claude_interactions or config.codex_interactions):
        print("OFF Tokenserver: all providers intentionally disabled",
              file=stdout)
    else:
        try:
            request = urllib.request.Request(
                TOKEN_SERVER_URL, headers={"Accept": "application/json"})
            with urlopen(request, timeout=NETWORK_TIMEOUT_SECONDS) as response:
                raw = response.read(MAX_DIAGNOSTIC_BYTES + 1)
            if len(raw) > MAX_DIAGNOSTIC_BYTES:
                raise ValueError("oversized diagnostics")
            payload = json.loads(raw.decode("utf-8", errors="strict"))
            interactions = payload.get("interactions")
            expected = {
                "claude": config.claude_interactions,
                "codex": config.codex_interactions,
                "detail": config.interaction_detail,
            }
            if (payload.get("service") != "torget-tokenserver" or
                    not isinstance(interactions, dict) or
                    any(interactions.get(key) is not value
                        for key, value in expected.items())):
                raise ValueError("diagnostics mismatch")
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError,
                TimeoutError):
            print("FIX Tokenserver: local diagnostics unavailable or stale",
                  file=stdout)
            fixes = True
        else:
            print("PASS Tokenserver", file=stdout)
    return not fixes


def _resolve_executables(python, codex):
    python_path = (Path(sys.executable) if python is _AUTO else
                   (None if python is None else Path(python)))
    if codex is _AUTO:
        found = shutil.which("codex")
        codex_path = Path(found) if found else None
    else:
        codex_path = None if codex is None else Path(codex)
    return python_path, codex_path


def main(
        argv: Sequence[str] | None = None, *, repo_root: Path = REPO_ROOT,
        config_path: Path | None = None, python=_AUTO, codex=_AUTO,
        run: Callable[..., object] = subprocess.run,
        urlopen: Callable[..., object] = urllib.request.urlopen,
        input_fn: Callable[[str], str] = input, stdout=None,
        stdin_isatty: bool | None = None) -> int:
    """Run the strict CLI with injectable process and network boundaries."""
    args = _parser().parse_args(argv)
    output = sys.stdout if stdout is None else stdout
    path = default_config_path() if config_path is None else Path(config_path)
    python_path, codex_path = _resolve_executables(python, codex)
    interactive = (sys.stdin.isatty() if stdin_isatty is None
                   else stdin_isatty)

    try:
        if args.command == "status":
            _print_status(load_config(path), output)
            return 0

        if args.command == "doctor":
            config = load_config(path)
            return 0 if _doctor(
                config, python=python_path, codex=codex_path, run=run,
                urlopen=urlopen, stdout=output) else 1

        if args.command == "disable":
            _disable(path, args.target)
            print(f"PASS Disabled {args.target} VibePulse interactions",
                  file=output)
            return 0

        if args.command == "uninstall":
            if codex_path is None:
                print("FIX Codex executable not found", file=output)
                return 1
            if not _run_commands(
                    plan_codex_uninstall(codex_path), run, output,
                    allow_absent=True):
                return 1
            _disable(path, "codex")
            print("PASS Removed only VibePulse Codex registration", file=output)
            return 0

        providers = args.providers
        if providers is None:
            providers = (_interactive_providers(input_fn)
                         if interactive else "off")
        detail = args.detail
        if detail is None:
            detail = (_interactive_detail(input_fn) if interactive else False)
        if codex_path is None or python_path is None:
            print("FIX Python or Codex executable not found", file=output)
            return 1
        commands = plan_codex_install(
            Path(repo_root), python_path, codex_path)
        if not _run_commands(commands, run, output, allow_absent=True):
            return 1
        _save_choice(path, _chosen_config(providers, detail))
        print("PASS Installed the local VibePulse package", file=output)
        print("Review and trust the exact VibePulse commands in Codex /hooks.",
              file=output)
        print("If the panel is unavailable, Codex uses computer fallback.",
              file=output)
        return 0
    except ConfigError as exc:
        print(f"FIX VibePulse configuration: {exc}", file=output)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
