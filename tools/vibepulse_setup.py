#!/usr/bin/env python3
"""Install and inspect the optional local VibePulse Codex integration."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
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
MAX_COMMAND_OUTPUT_BYTES = 16 * 1024
COMMAND_TIMEOUT_SECONDS = 15
NETWORK_TIMEOUT_SECONDS = 2
_AUTO = object()

_KNOWN_ABSENT = {
    ("plugin", "marketplace", "remove", "torget"): re.compile(
        r"\AError: marketplace `torget` is not configured or installed\Z"),
}
_CODEX_VERSION = re.compile(
    r"\A(?:codex|codex-cli) [0-9]+\.[0-9]+\.[0-9]+"
    r"(?:-[0-9A-Za-z.-]+)?\n?\Z")
_PYTHON_PROBE = (
    "import sys; print('vibepulse-python-3.11+' "
    "if sys.version_info >= (3, 11) else 'unsupported')")


@dataclass(frozen=True)
class _CommandResult:
    returncode: int
    stdout: str
    stderr: str


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
         str(root)],
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


def _disabled_config(saved: VibePulseConfig, target: str) -> VibePulseConfig:
    return VibePulseConfig(
        claude_interactions=(saved.claude_interactions
                             if target == "codex" else False),
        codex_interactions=(saved.codex_interactions
                            if target == "claude" else False),
        interaction_detail=saved.interaction_detail,
    )


def _disable(path: Path, target: str) -> None:
    with config_lock(path):
        saved = load_config(path)
        save_config(path, _disabled_config(saved, target))


def _known_absent(argv: Sequence[str], stderr: str) -> bool:
    command = tuple(argv[1:])
    pattern = _KNOWN_ABSENT.get(command)
    if pattern is None:
        return False
    normalized = stderr.replace("\r\n", "\n")
    if normalized.endswith("\n"):
        normalized = normalized[:-1]
    return pattern.fullmatch(normalized) is not None


def _invoke(argv: Sequence[str], run: Callable[..., object]) -> _CommandResult | None:
    try:
        completed = run(
            [str(value) for value in argv], capture_output=True, text=True,
            timeout=COMMAND_TIMEOUT_SECONDS, check=False, shell=False)
    except (OSError, subprocess.SubprocessError):
        return None
    returncode = getattr(completed, "returncode", None)
    stdout = getattr(completed, "stdout", None)
    stderr = getattr(completed, "stderr", None)
    if (type(returncode) is not int or not isinstance(stdout, str) or
            not isinstance(stderr, str)):
        return None
    try:
        if (len(stdout.encode("utf-8")) > MAX_COMMAND_OUTPUT_BYTES or
                len(stderr.encode("utf-8")) > MAX_COMMAND_OUTPUT_BYTES):
            return None
    except UnicodeError:
        return None
    return _CommandResult(returncode, stdout, stderr)


def _run_commands(
        commands: Sequence[Sequence[str]], run: Callable[..., object],
        stdout, *, allow_absent: bool) -> bool:
    for argv_value in commands:
        argv = [str(value) for value in argv_value]
        completed = _invoke(argv, run)
        if completed is None:
            print(f"FIX Command failed: {' '.join(argv[1:])}", file=stdout)
            return False
        if completed.returncode != 0 and not (
                allow_absent and _known_absent(argv, completed.stderr)):
            print(f"FIX Command failed: {' '.join(argv[1:])}", file=stdout)
            return False
    return True


def _print_status(config: VibePulseConfig, stdout) -> None:
    def switch(value: bool) -> str:
        return "ON" if value else "OFF"

    print(f"Claude: {switch(config.claude_interactions)}", file=stdout)
    print(f"Codex: {switch(config.codex_interactions)}", file=stdout)
    print(f"Detail: {switch(config.interaction_detail)}", file=stdout)


def _reject_json_constant(value):
    raise ValueError(f"non-standard JSON constant: {value}")


def _unique_json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def _strict_json(text: str):
    if not isinstance(text, str):
        raise ValueError("JSON input must be text")
    try:
        encoded_size = len(text.encode("utf-8"))
    except UnicodeError as exc:
        raise ValueError("JSON input is not valid UTF-8") from exc
    if encoded_size > MAX_COMMAND_OUTPUT_BYTES:
        raise ValueError("JSON output is too large")
    try:
        return json.loads(
            text, parse_constant=_reject_json_constant,
            object_pairs_hook=_unique_json_object)
    except RecursionError as exc:
        raise ValueError("JSON nesting is too deep") from exc


def _expected_mcp_item(repo_root: Path, python: Path) -> dict:
    script = (Path(repo_root).resolve() / ".agents" / "plugins" / "plugins" /
              "vibepulse" / "scripts" / "mcp_server.py")
    return {
        "name": "vibepulse",
        "enabled": True,
        "disabled_reason": None,
        "transport": {
            "type": "stdio",
            "command": str(Path(python).resolve()),
            "args": [str(script)],
            "env": None,
            "env_vars": [],
            "cwd": None,
        },
        "startup_timeout_sec": None,
        "tool_timeout_sec": None,
        "auth_status": "unsupported",
    }


def _mcp_listing(text: str) -> list[dict] | None:
    try:
        value = _strict_json(text)
    except (TypeError, ValueError, json.JSONDecodeError, UnicodeError):
        return None
    if not isinstance(value, list) or any(not isinstance(item, dict)
                                          for item in value):
        return None
    return value


def _owned_mcp_state(
        text: str, repo_root: Path, python: Path) -> bool | None:
    listing = _mcp_listing(text)
    if listing is None:
        return None
    named = [item for item in listing if item.get("name") == "vibepulse"]
    if not named:
        return False
    if len(named) != 1 or named[0] != _expected_mcp_item(repo_root, python):
        return None
    return True


def _has_symlink_component(path: Path) -> bool:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        if current.is_symlink():
            return True
    return False


def _is_exact_existing_directory(value, expected: Path) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        candidate = Path(value)
        canonical_expected = Path(expected).resolve(strict=True)
        return all((
            candidate.is_absolute(),
            value == str(candidate),
            value == str(canonical_expected),
            candidate.is_dir(),
            not _has_symlink_component(candidate),
            candidate.resolve(strict=True) == canonical_expected,
        ))
    except (OSError, RuntimeError, ValueError):
        return False


def _plugin_installed(text: str, repo_root: Path) -> bool:
    try:
        value = _strict_json(text)
    except (TypeError, ValueError, json.JSONDecodeError, UnicodeError):
        return False
    if not isinstance(value, dict):
        return False
    installed = value.get("installed")
    available = value.get("available")
    if (not isinstance(installed, list) or
            not isinstance(available, list) or
            any(not isinstance(item, dict) for item in installed)):
        return False
    matches = [item for item in installed if isinstance(item, dict) and
               item.get("pluginId") == "vibepulse@torget"]
    if len(matches) != 1:
        return False
    item = matches[0]
    source = item.get("source")
    marketplace_source = item.get("marketplaceSource")
    if (item.get("name") != "vibepulse" or
            item.get("marketplaceName") != "torget" or
            item.get("installed") is not True or
            item.get("enabled") is not True or
            not isinstance(source, dict) or
            set(source) != {"source", "path"} or
            source.get("source") != "local" or
            not isinstance(marketplace_source, dict) or
            set(marketplace_source) != {"sourceType", "source"} or
            marketplace_source.get("sourceType") != "local"):
        return False
    try:
        expected_root = Path(repo_root).resolve(strict=True)
        expected_plugin = (expected_root / ".agents" / "plugins" / "plugins" /
                           "vibepulse")
        if expected_plugin.resolve(strict=True) != expected_plugin:
            return False
    except (OSError, RuntimeError, ValueError):
        return False
    return all((
        expected_root.is_dir(),
        expected_plugin.is_dir(),
        _is_exact_existing_directory(
            marketplace_source.get("source"), expected_root),
        _is_exact_existing_directory(source.get("path"), expected_plugin),
    ))


def _doctor(
        config: VibePulseConfig, *, python: Path | None, codex: Path | None,
        repo_root: Path, run: Callable[..., object],
        urlopen: Callable[..., object], stdout,
        ) -> bool:
    fixes = False

    python_ok = False
    if python is not None:
        probe = _invoke([str(Path(python).resolve()), "-c", _PYTHON_PROBE], run)
        python_ok = (probe is not None and probe.returncode == 0 and
                     probe.stdout == "vibepulse-python-3.11+\n")
    if not python_ok:
        print("FIX Python executable: install Python 3.11 or newer", file=stdout)
        fixes = True
    else:
        print("PASS Python executable", file=stdout)

    codex_ok = False
    if not config.codex_interactions:
        print("OFF Codex executable: provider intentionally disabled",
              file=stdout)
    elif codex is None:
        print("FIX Codex executable: install or expose codex on PATH", file=stdout)
        fixes = True
    else:
        probe = _invoke([str(Path(codex).resolve()), "--version"], run)
        codex_ok = (probe is not None and probe.returncode == 0 and
                    _CODEX_VERSION.fullmatch(probe.stdout) is not None)
        if codex_ok:
            print("PASS Codex executable", file=stdout)
        else:
            print("FIX Codex executable: candidate is not Codex", file=stdout)
            fixes = True

    if not config.codex_interactions:
        print("OFF Codex plugin: provider intentionally disabled", file=stdout)
        print("OFF Codex MCP: provider intentionally disabled", file=stdout)
    elif not codex_ok or codex is None or python is None:
        print("FIX Codex plugin: cannot inspect without Codex", file=stdout)
        print("FIX Codex MCP: cannot inspect without Codex", file=stdout)
        fixes = True
    else:
        codex_text = str(Path(codex).resolve())
        plugin_result = _invoke(
            [codex_text, "plugin", "list", "--json"], run)
        plugin_ok = (plugin_result is not None and
                     plugin_result.returncode == 0 and
                     _plugin_installed(plugin_result.stdout, repo_root))
        if plugin_ok:
            print("PASS Codex plugin", file=stdout)
        else:
            print("FIX Codex plugin: install vibepulse@torget", file=stdout)
            fixes = True

        mcp_result = _invoke([codex_text, "mcp", "list", "--json"], run)
        mcp_ok = (mcp_result is not None and mcp_result.returncode == 0 and
                  _owned_mcp_state(
                      mcp_result.stdout, repo_root, python) is True)
        if mcp_ok:
            print("PASS Codex MCP", file=stdout)
        else:
            print("FIX Codex MCP: register the local bridge", file=stdout)
            fixes = True

    if config.codex_interactions:
        print("FIX hooks: open /hooks and review VibePulse; trust status is "
              "not machine-readable", file=stdout)
        fixes = True
    else:
        print("OFF Hook review: provider intentionally disabled", file=stdout)

    if not (config.claude_interactions or config.codex_interactions):
        print("OFF Tokenserver: all providers intentionally disabled",
              file=stdout)
    else:
        try:
            request = urllib.request.Request(
                TOKEN_SERVER_URL, headers={"Accept": "application/json"})
            with urlopen(request, timeout=NETWORK_TIMEOUT_SECONDS) as response:
                raw = response.read(MAX_DIAGNOSTIC_BYTES + 1)
            if (not isinstance(raw, bytes) or
                    len(raw) > MAX_DIAGNOSTIC_BYTES):
                raise ValueError("oversized diagnostics")
            payload = _strict_json(raw.decode("utf-8", errors="strict"))
            if not isinstance(payload, dict):
                raise ValueError("diagnostics must be an object")
            interactions = payload.get("interactions")
            expected = {
                "claude": config.claude_interactions,
                "codex": config.codex_interactions,
                "detail": config.interaction_detail,
                "transport": "lan",
            }
            if (payload.get("service") != "torget-tokenserver" or
                    not isinstance(interactions, dict) or
                    any(interactions.get(key) is not value
                        for key, value in expected.items()
                        if key != "transport") or
                    interactions.get("transport") != "lan"):
                raise ValueError("diagnostics mismatch")
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError,
                RecursionError, TimeoutError):
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


def _install_transaction(
        *, path: Path, providers: str, detail: bool, repo_root: Path,
        python: Path, codex: Path, run: Callable[..., object], stdout) -> bool:
    """Validate state, mutate Codex, then atomically publish saved routing."""
    with config_lock(path):
        load_config(path)
        target = _chosen_config(providers, detail)
        codex_text = str(Path(codex).resolve())
        preflight_argv = [codex_text, "mcp", "list", "--json"]
        preflight = _invoke(preflight_argv, run)
        if preflight is None or preflight.returncode != 0:
            print("FIX Cannot inspect existing Codex MCP registration",
                  file=stdout)
            return False
        owned_before = _owned_mcp_state(
            preflight.stdout, repo_root, python)
        if owned_before is None:
            print("FIX Existing vibepulse MCP is foreign or unreadable; "
                  "leaving it unchanged", file=stdout)
            return False

        commands = plan_codex_install(repo_root, python, codex)
        for index, argv in enumerate(commands):
            completed = _invoke(argv, run)
            if completed is not None and completed.returncode == 0:
                continue
            if index == len(commands) - 1:
                if owned_before:
                    rollback = _invoke(argv, run)
                    if rollback is not None and rollback.returncode == 0:
                        print("FIX MCP add failed; previous owned registration "
                              "restored", file=stdout)
                    else:
                        print("FIX MCP add failed; rollback also failed",
                              file=stdout)
                else:
                    print("FIX MCP add failed; no previous registration to "
                          "restore", file=stdout)
            else:
                print(f"FIX Command failed: {' '.join(argv[1:])}", file=stdout)
            return False
        save_config(path, target)
        return True


def _uninstall_transaction(
        *, path: Path, codex: Path, run: Callable[..., object], stdout) -> bool:
    """Disable Codex only after its owned registrations are removed."""
    with config_lock(path):
        saved = load_config(path)
        target = _disabled_config(saved, "codex")
        if not _run_commands(
                plan_codex_uninstall(codex), run, stdout,
                allow_absent=True):
            return False
        save_config(path, target)
        return True


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
                config, python=python_path, codex=codex_path,
                repo_root=Path(repo_root), run=run, urlopen=urlopen,
                stdout=output) else 1

        if args.command == "disable":
            _disable(path, args.target)
            print(f"PASS Disabled {args.target} VibePulse interactions",
                  file=output)
            return 0

        if args.command == "uninstall":
            if codex_path is None:
                print("FIX Codex executable not found", file=output)
                return 1
            if not _uninstall_transaction(
                    path=path, codex=codex_path, run=run, stdout=output):
                return 1
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
        if not _install_transaction(
                path=path, providers=providers, detail=detail,
                repo_root=Path(repo_root), python=python_path,
                codex=codex_path, run=run, stdout=output):
            return 1
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
