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
import threading
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


@dataclass(frozen=True)
class _ExternalState:
    mcp: bool
    plugin: bool
    marketplace: bool


@dataclass(frozen=True)
class _RollbackStep:
    argv: tuple[str, ...]
    description: str


class _ConfigPublishError(ConfigError):
    def __init__(self, message: str, *, irrecoverable: bool) -> None:
        super().__init__(message)
        self.irrecoverable = irrecoverable


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


def _bounded_process(argv: Sequence[str]) -> _CommandResult | None:
    """Run one argv while retaining only a bounded prefix of both pipes."""
    process = None
    threads: list[threading.Thread] = []
    captured = {"stdout": bytearray(), "stderr": bytearray()}
    reader_errors: list[BaseException] = []

    def drain(label: str, pipe) -> None:
        try:
            while True:
                chunk = pipe.read(8192)
                if not chunk:
                    return
                remaining = MAX_COMMAND_OUTPUT_BYTES + 1 - len(captured[label])
                if remaining > 0:
                    captured[label].extend(chunk[:remaining])
        except BaseException as exc:
            reader_errors.append(exc)

    try:
        process = subprocess.Popen(
            [str(value) for value in argv], stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False,
            close_fds=True)
        assert process.stdout is not None and process.stderr is not None
        for label, pipe in (("stdout", process.stdout),
                            ("stderr", process.stderr)):
            thread = threading.Thread(
                target=drain, args=(label, pipe),
                name=f"vibepulse-drain-{label}")
            thread.start()
            threads.append(thread)
        try:
            returncode = process.wait(timeout=COMMAND_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            return None
    except (OSError, subprocess.SubprocessError):
        return None
    except BaseException:
        if process is not None and process.poll() is None:
            process.kill()
            process.wait()
        raise
    finally:
        for thread in threads:
            thread.join()
        if process is not None:
            if process.stdout is not None:
                process.stdout.close()
            if process.stderr is not None:
                process.stderr.close()

    if (reader_errors or
            len(captured["stdout"]) > MAX_COMMAND_OUTPUT_BYTES or
            len(captured["stderr"]) > MAX_COMMAND_OUTPUT_BYTES):
        return None
    try:
        stdout = bytes(captured["stdout"]).decode("utf-8", errors="strict")
        stderr = bytes(captured["stderr"]).decode("utf-8", errors="strict")
    except UnicodeError:
        return None
    return _CommandResult(returncode, stdout, stderr)


def _invoke(argv: Sequence[str], run) -> _CommandResult | None:
    if run is _AUTO:
        return _bounded_process(argv)
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
    except (RecursionError, UnicodeError, ValueError) as exc:
        raise ValueError("invalid strict JSON") from exc


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


def _owned_plugin_item(item, repo_root: Path) -> bool:
    if not isinstance(item, dict):
        return False
    source = item.get("source")
    marketplace_source = item.get("marketplaceSource")
    if (item.get("pluginId") != "vibepulse@torget" or
            item.get("name") != "vibepulse" or
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


def _plugin_state(text: str, repo_root: Path) -> bool | None:
    try:
        value = _strict_json(text)
    except (TypeError, ValueError, json.JSONDecodeError, UnicodeError):
        return None
    if not isinstance(value, dict) or set(value) != {"installed", "available"}:
        return None
    installed = value.get("installed")
    available = value.get("available")
    if (not isinstance(installed, list) or
            not isinstance(available, list) or
            any(not isinstance(item, dict) for item in installed) or
            any(not isinstance(item, dict) for item in available)):
        return None
    matches = [item for item in installed
               if (item.get("pluginId") == "vibepulse@torget" or
                   item.get("name") == "vibepulse")]
    if not matches:
        return False
    if len(matches) != 1 or not _owned_plugin_item(matches[0], repo_root):
        return None
    return True


def _plugin_installed(text: str, repo_root: Path) -> bool:
    return _plugin_state(text, repo_root) is True


def _marketplace_state(text: str, repo_root: Path) -> bool | None:
    try:
        value = _strict_json(text)
    except (TypeError, ValueError, json.JSONDecodeError, UnicodeError):
        return None
    if (not isinstance(value, dict) or set(value) != {"marketplaces"} or
            not isinstance(value.get("marketplaces"), list) or
            any(not isinstance(item, dict)
                for item in value.get("marketplaces", []))):
        return None
    matches = [item for item in value["marketplaces"]
               if item.get("name") == MARKETPLACE_NAME]
    if not matches:
        return False
    if len(matches) != 1:
        return None
    item = matches[0]
    source = item.get("marketplaceSource")
    if (set(item) != {"name", "root", "marketplaceSource"} or
            not isinstance(source, dict) or
            set(source) != {"sourceType", "source"} or
            source.get("sourceType") != "local"):
        return None
    try:
        expected = Path(repo_root).resolve(strict=True)
    except (OSError, RuntimeError, ValueError):
        return None
    if (not _is_exact_existing_directory(item.get("root"), expected) or
            not _is_exact_existing_directory(source.get("source"), expected)):
        return None
    return True


def _python_probe_ok(python: Path | None, run) -> bool:
    if python is None:
        return False
    probe = _invoke([str(Path(python).resolve()), "-c", _PYTHON_PROBE], run)
    return (probe is not None and probe.returncode == 0 and
            probe.stdout == "vibepulse-python-3.11+\n" and
            probe.stderr == "")


def _codex_probe_ok(codex: Path | None, run) -> bool:
    if codex is None:
        return False
    probe = _invoke([str(Path(codex).resolve()), "--version"], run)
    return (probe is not None and probe.returncode == 0 and
            probe.stderr == "" and
            _CODEX_VERSION.fullmatch(probe.stdout) is not None)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _default_urlopen(request, *, timeout):
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}), _NoRedirect())
    return opener.open(request, timeout=timeout)


def _response_content_type(response) -> bool:
    headers = getattr(response, "headers", None)
    get_all = getattr(headers, "get_all", None)
    if not callable(get_all):
        return False
    values = get_all("Content-Type", [])
    if not isinstance(values, list) or len(values) != 1:
        return False
    value = values[0]
    if not isinstance(value, str):
        return False
    return re.fullmatch(
        r"application/json(?:;[ \t]*charset=[Uu][Tt][Ff]-8)?", value
    ) is not None


def _doctor(
        config: VibePulseConfig, *, python: Path | None, codex: Path | None,
        repo_root: Path, run: Callable[..., object],
        urlopen: Callable[..., object], stdout,
        ) -> bool:
    fixes = False

    python_ok = _python_probe_ok(python, run)
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
        codex_ok = _codex_probe_ok(codex, run)
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
            open_url = (_default_urlopen if urlopen is _AUTO else urlopen)
            with open_url(request, timeout=NETWORK_TIMEOUT_SECONDS) as response:
                if (getattr(response, "status", None) != 200 or
                        not _response_content_type(response)):
                    raise ValueError("untrusted diagnostic response")
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


def _setup_transaction_path(path: Path) -> Path:
    path = Path(path)
    return path.with_name(f".{path.name}.vibepulse-setup-transaction")


def _inspect_external(
        *, repo_root: Path, python: Path, codex: Path, run,
        stdout) -> _ExternalState | None:
    codex_text = str(Path(codex).resolve())
    commands = [
        [codex_text, "mcp", "list", "--json"],
        [codex_text, "plugin", "list", "--json"],
        [codex_text, "plugin", "marketplace", "list", "--json"],
    ]
    results = [_invoke(argv, run) for argv in commands]
    states: list[bool | None] = [None, None, None]
    if results[0] is not None and results[0].returncode == 0:
        states[0] = _owned_mcp_state(
            results[0].stdout, repo_root, python)
    if results[1] is not None and results[1].returncode == 0:
        states[1] = _plugin_state(results[1].stdout, repo_root)
    if results[2] is not None and results[2].returncode == 0:
        states[2] = _marketplace_state(results[2].stdout, repo_root)
    if any(state is None for state in states):
        print("FIX Codex resources are foreign or unreadable; leaving all "
              "external state unchanged", file=stdout)
        return None
    return _ExternalState(
        mcp=states[0], plugin=states[1], marketplace=states[2])


def _command_ok(
        completed: _CommandResult | None, argv: Sequence[str], *,
        absent_allowed: bool = False) -> bool:
    return (completed is not None and
            (completed.returncode == 0 or
             (absent_allowed and
              _known_absent(argv, completed.stderr))))


def _rollback(
        journal: Sequence[_RollbackStep], run, stdout,
        failed_step: str) -> bool:
    failures = []
    for step in reversed(journal):
        try:
            completed = _invoke(step.argv, run)
            if not _command_ok(
                    completed, step.argv, absent_allowed=True):
                failures.append(step.description)
        except BaseException:
            failures.append(step.description)
    if failures:
        print("FIX irrecoverable divergence after " + failed_step +
              "; rollback failed: " + ", ".join(failures), file=stdout)
        return False
    print(f"FIX Setup failed at {failed_step}; external state restored",
          file=stdout)
    return True


def _publish_config(
        path: Path, snapshot: VibePulseConfig,
        target: VibePulseConfig) -> None:
    with config_lock(path):
        if load_config(path) != snapshot:
            raise _ConfigPublishError(
                "configuration changed during setup", irrecoverable=False)
        try:
            save_config(path, target)
        except BaseException as exc:
            restored = False
            try:
                current = load_config(path)
                if current == snapshot:
                    restored = True
                elif current == target:
                    try:
                        save_config(path, snapshot)
                    except BaseException:
                        pass
                    restored = load_config(path) == snapshot
            except BaseException:
                restored = False
            raise _ConfigPublishError(
                "configuration publish failed",
                irrecoverable=not restored) from exc


def _failed_step_with_publish_state(
        failed_step: str, exc: BaseException) -> str:
    if isinstance(exc, _ConfigPublishError) and exc.irrecoverable:
        return failed_step + " (irrecoverable configuration divergence)"
    return failed_step


def _install_transaction(
        *, path: Path, providers: str, detail: bool, repo_root: Path,
        python: Path, codex: Path, run, stdout) -> bool:
    """Mutate owned Codex resources and publish routing transactionally."""
    with config_lock(_setup_transaction_path(path)):
        with config_lock(path):
            snapshot = load_config(path)
        target = _chosen_config(providers, detail)
        journal: list[_RollbackStep] = []
        failed_step = "runtime preflight"
        try:
            if not _python_probe_ok(python, run):
                print("FIX Python executable: install Python 3.11 or newer",
                      file=stdout)
                return False
            if not _codex_probe_ok(codex, run):
                print("FIX Codex executable: candidate is not Codex",
                      file=stdout)
                return False
            failed_step = "resource ownership preflight"
            before = _inspect_external(
                repo_root=repo_root, python=python, codex=codex, run=run,
                stdout=stdout)
            if before is None:
                return False

            install = plan_codex_install(repo_root, python, codex)
            uninstall = plan_codex_uninstall(codex)
            steps = (
                ("marketplace add", install[0], not before.marketplace,
                 _RollbackStep(tuple(uninstall[2]), "marketplace remove")),
                ("plugin add", install[1], not before.plugin,
                 _RollbackStep(tuple(uninstall[1]), "plugin remove")),
                ("MCP remove", install[2], before.mcp,
                 _RollbackStep(tuple(install[3]), "MCP restore")),
                ("MCP add", install[3], True,
                 _RollbackStep(tuple(uninstall[0]), "MCP remove")),
            )
            for failed_step, argv, changes_state, compensation in steps:
                completed = _invoke(argv, run)
                if not _command_ok(completed, argv):
                    _rollback(journal, run, stdout, failed_step)
                    return False
                if changes_state:
                    journal.append(compensation)

            failed_step = "configuration publish"
            _publish_config(path, snapshot, target)
            return True
        except BaseException as exc:
            _rollback(
                journal, run, stdout,
                _failed_step_with_publish_state(failed_step, exc))
            return False


def _uninstall_transaction(
        *, path: Path, repo_root: Path, python: Path, codex: Path,
        run, stdout) -> bool:
    """Remove only proven-owned resources and compensate every failure."""
    with config_lock(_setup_transaction_path(path)):
        with config_lock(path):
            snapshot = load_config(path)
        target = _disabled_config(snapshot, "codex")
        journal: list[_RollbackStep] = []
        failed_step = "resource ownership preflight"
        try:
            before = _inspect_external(
                repo_root=repo_root, python=python, codex=codex, run=run,
                stdout=stdout)
            if before is None:
                return False
            install = plan_codex_install(repo_root, python, codex)
            uninstall = plan_codex_uninstall(codex)
            steps = (
                ("MCP remove", uninstall[0], before.mcp,
                 _RollbackStep(tuple(install[3]), "MCP restore")),
                ("plugin remove", uninstall[1], before.plugin,
                 _RollbackStep(tuple(install[1]), "plugin restore")),
                ("marketplace remove", uninstall[2], before.marketplace,
                 _RollbackStep(tuple(install[0]), "marketplace restore")),
            )
            for failed_step, argv, changes_state, compensation in steps:
                completed = _invoke(argv, run)
                if not _command_ok(
                        completed, argv, absent_allowed=not changes_state):
                    _rollback(journal, run, stdout, failed_step)
                    return False
                if changes_state:
                    journal.append(compensation)
            failed_step = "configuration publish"
            _publish_config(path, snapshot, target)
            return True
        except BaseException as exc:
            _rollback(
                journal, run, stdout,
                _failed_step_with_publish_state(failed_step, exc))
            return False


def main(
        argv: Sequence[str] | None = None, *, repo_root: Path = REPO_ROOT,
        config_path: Path | None = None, python=_AUTO, codex=_AUTO,
        run=_AUTO, urlopen=_AUTO,
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
            if codex_path is None or python_path is None:
                print("FIX Python or Codex executable not found", file=output)
                return 1
            if not _uninstall_transaction(
                    path=path, repo_root=Path(repo_root), python=python_path,
                    codex=codex_path, run=run, stdout=output):
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
