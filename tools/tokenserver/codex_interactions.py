"""Strict Codex-to-panel interaction normalization.

Codex MCP questions and permission hooks use different wire formats from the
existing Claude hooks.  This module validates their small supported subset and
separates private adapter data from the bounded panel ``view``.
"""

from __future__ import annotations

import shlex
import unicodedata
from typing import Any, Dict, Optional

if __package__:
    from .agent_status import sanitize_project
    from .interactions import approval_view, approvable_tool
else:  # direct execution, same convention as tokenserver.py
    from agent_status import sanitize_project
    from interactions import approval_view, approvable_tool


_QUESTION_FIELDS = frozenset({"question", "header", "options"})
_OPTION_FIELDS = frozenset({"label", "description", "recommended"})
_SAFE_BUILD_TARGETS = frozenset({"all", "build", "test", "check"})
_SAFE_NPM_FLAGS = frozenset({"--silent", "--if-present", "--ignore-scripts"})
_SAFE_GIT_STATUS_FLAGS = frozenset({"--short", "-s", "--branch", "-b",
                                    "--porcelain"})
_SAFE_GIT_LOG_SHOW_FLAGS = frozenset({"--oneline", "--decorate", "--graph",
                                      "--stat", "--patch", "--no-color"})
_SAFE_GIT_DIFF_FLAGS = frozenset({"--stat", "--name-only", "--name-status",
                                  "--check", "--no-color", "--cached", "--staged"})


def _is_control_free(value: str) -> bool:
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return not any(unicodedata.category(char).startswith("C")
                   for char in value)


def _text_is_valid(value: Any, maximum_bytes: Optional[int] = None) -> bool:
    """Whether a panel-bound text value needs no cleanup or truncation."""
    if not isinstance(value, str) or not value.strip():
        return False
    if not _is_control_free(value):
        return False
    encoded = value.encode("utf-8")
    return maximum_bytes is None or len(encoded) <= maximum_bytes


def _plain_arguments(arguments: list[str]) -> bool:
    return all(not argument.startswith("-") for argument in arguments)


def _make_or_ninja_is_safe(arguments: list[str]) -> bool:
    for argument in arguments:
        if argument.casefold() not in _SAFE_BUILD_TARGETS:
            return False
    return True


def _cmake_build_is_safe(arguments: list[str]) -> bool:
    if len(arguments) < 2 or arguments[0].casefold() != "--build" or \
            arguments[1].startswith("-"):
        return False
    index = 2
    while index < len(arguments):
        argument = arguments[index].casefold()
        if argument == "--verbose":
            index += 1
        elif argument in {"--parallel", "-j"}:
            index += 1
            if index < len(arguments) and not arguments[index].startswith("-"):
                if not arguments[index].isdigit():
                    return False
                index += 1
        elif argument == "--config":
            index += 1
            if index >= len(arguments) or arguments[index].startswith("-"):
                return False
            index += 1
        elif argument == "--target":
            index += 1
            targets = 0
            while index < len(arguments) and not arguments[index].startswith("-"):
                if arguments[index].casefold() not in _SAFE_BUILD_TARGETS:
                    return False
                targets += 1
                index += 1
            if not targets:
                return False
        elif argument.startswith("--target="):
            if argument.partition("=")[2] not in _SAFE_BUILD_TARGETS:
                return False
            index += 1
        else:
            return False
    return True


def _npm_is_safe(arguments: list[str]) -> bool:
    if not arguments:
        return False
    if arguments[0].casefold() == "test":
        flags = arguments[1:]
    elif len(arguments) >= 2 and arguments[0].casefold() == "run" and \
            arguments[1].casefold() in {"test", "build"}:
        flags = arguments[2:]
    else:
        return False
    return all(flag.casefold() in _SAFE_NPM_FLAGS for flag in flags)


def _git_is_safe(arguments: list[str]) -> bool:
    if not arguments:
        return False
    subcommand = arguments[0].casefold()
    tail = arguments[1:]
    if subcommand == "status":
        return all(flag.casefold() in _SAFE_GIT_STATUS_FLAGS for flag in tail)
    if subcommand == "branch":
        return not tail or tail == ["--show-current"]
    if subcommand in {"log", "show"}:
        return all(not argument.startswith("-") or
                   argument.casefold() in _SAFE_GIT_LOG_SHOW_FLAGS
                   for argument in tail)
    if subcommand != "diff":
        return False
    paths_only = False
    for argument in tail:
        if paths_only:
            continue
        if argument == "--":
            paths_only = True
        elif argument.startswith("-") and \
                argument.casefold() not in _SAFE_GIT_DIFF_FLAGS:
            return False
    return True


def _codex_shell_command_is_safe(command: Any) -> bool:
    """Permit only small, read-only shapes within the coarse base allowlist."""
    if not isinstance(command, str):
        return False
    try:
        tokens = shlex.split(command)
    except ValueError:
        return False
    if not tokens:
        return False
    if tokens[0] == "./test/run.sh":
        return len(tokens) == 1
    family = tokens[0].casefold()
    arguments = tokens[1:]
    if family in {"make", "ninja"}:
        return _make_or_ninja_is_safe(arguments)
    if family == "cmake":
        return _cmake_build_is_safe(arguments)
    if family == "npm":
        return _npm_is_safe(arguments)
    if family == "git":
        return _git_is_safe(arguments)
    if family in {"ls", "cat", "head", "tail", "wc", "grep", "rg"}:
        return _plain_arguments(arguments)
    if family == "pytest":
        return _plain_arguments(arguments)
    if family in {"python", "python3"}:
        return len(arguments) >= 2 and arguments[:2] == ["-m", "unittest"] \
            and _plain_arguments(arguments[2:])
    if family == "cargo":
        return len(arguments) >= 1 and arguments[0].casefold() in {"test", "build"} \
            and _plain_arguments(arguments[1:])
    if family == "go":
        return len(arguments) >= 1 and arguments[0].casefold() == "test" and \
            _plain_arguments(arguments[1:])
    if family == "ctest":
        return _plain_arguments(arguments)
    if family == "idf.py":
        return len(arguments) == 1 and arguments[0].casefold() == "build"
    return False


def _identity(cwd: Any, session_id: Any,
              turn_id: Any) -> Optional[Dict[str, Any]]:
    if not all(_text_is_valid(value) for value in (cwd, session_id, turn_id)):
        return None
    return {
        "project": sanitize_project(cwd),
        "session_id": session_id,
        "turn_id": turn_id,
    }


def normalize_codex_question(payload: dict, *, cwd: str,
                             session_id: str,
                             turn_id: str) -> Optional[dict]:
    """Normalize a supported Codex MCP question without guessing an answer."""
    identity = _identity(cwd, session_id, turn_id)
    if identity is None or not isinstance(payload, dict):
        return None
    if set(payload) - _QUESTION_FIELDS or \
            not {"question", "options"}.issubset(payload):
        return None

    prompt = payload["question"]
    if not _text_is_valid(prompt, 96):
        return None
    if "header" in payload and not _text_is_valid(payload["header"], 64):
        return None
    raw_options = payload["options"]
    if not isinstance(raw_options, list) or len(raw_options) not in (2, 3):
        return None

    options = []
    recommended = None
    for index, raw_option in enumerate(raw_options):
        if not isinstance(raw_option, dict) or \
                set(raw_option) - _OPTION_FIELDS or \
                "label" not in raw_option:
            return None
        label = raw_option["label"]
        if not _text_is_valid(label, 64):
            return None
        normalized_option = {"label": label}
        if "description" in raw_option:
            description = raw_option["description"]
            if not _text_is_valid(description, 64):
                return None
            normalized_option["description"] = description
        if "recommended" in raw_option:
            if not isinstance(raw_option["recommended"], bool):
                return None
            normalized_option["recommended"] = raw_option["recommended"]
            if raw_option["recommended"]:
                if recommended is not None:
                    return None
                recommended = index
        options.append(normalized_option)

    view: Dict[str, Any] = {
        "kind": "question",
        "options_total": len(options),
        "marked": recommended is not None,
        "prompt": prompt,
        "can_approve": recommended is not None,
    }
    if recommended is not None:
        selected = options[recommended]
        view["title"] = selected["label"]
        view["subtitle"] = selected.get("description")

    return {
        "provider": "codex",
        "kind": "question",
        **identity,
        "options": options,
        "recommended_index": recommended,
        "view": view,
    }


def normalize_codex_permission(event: dict, *, reveal: bool) -> Optional[dict]:
    """Normalize one Codex permission hook event for the panel."""
    if not isinstance(event, dict) or \
            event.get("hook_event_name") != "PermissionRequest":
        return None
    required = ("session_id", "turn_id", "cwd", "tool_name")
    if any(not _text_is_valid(event.get(name)) for name in required) or \
            not isinstance(event.get("tool_input"), dict):
        return None

    identity = _identity(event["cwd"], event["session_id"], event["turn_id"])
    if identity is None:
        return None
    tool_name = event["tool_name"]
    tool_input = dict(event["tool_input"])
    for field in ("command", "description"):
        value = tool_input.get(field)
        if isinstance(value, str) and not _is_control_free(value):
            return None
    view = approval_view(tool_name, tool_input, reveal)
    # Keep this explicit even though approval_view currently performs the same
    # check: the adapter boundary must not make a future view change an allow
    # path for a tool outside the established narrow classifier.
    can_approve = approvable_tool(tool_name, tool_input)
    if tool_name.strip().casefold() in {"bash", "shell"}:
        can_approve = can_approve and _codex_shell_command_is_safe(
            tool_input.get("command"))
    view["can_approve"] = bool(view.get("can_approve")) and can_approve
    normalized_event = {
        "hook_event_name": "PermissionRequest",
        "session_id": event["session_id"],
        "turn_id": event["turn_id"],
        "cwd": event["cwd"],
        "tool_name": tool_name,
        "tool_input": tool_input,
    }
    return {
        "provider": "codex",
        "kind": "approval",
        **identity,
        "event": normalized_event,
        "recommended_index": None,
        "view": view,
    }


def codex_permission_response(verdict: str) -> Optional[dict]:
    """Format a documented Codex PermissionRequest hook decision."""
    if verdict == "leave_it":
        return None
    if verdict == "approve":
        decision = {"behavior": "allow"}
    elif verdict == "deny":
        decision = {"behavior": "deny", "message": "Denied from VibePulse"}
    else:
        raise ValueError("unsupported permission verdict")
    return {"hookSpecificOutput": {
        "hookEventName": "PermissionRequest", "decision": decision,
    }}


def codex_question_result(verdict: str, normalized: dict) -> dict:
    """Answer only a Codex option that was explicitly recommended."""
    index = normalized.get("recommended_index")
    if verdict != "approve" or index is None:
        return {"status": "computer", "reason": verdict}
    option = normalized["options"][index]
    return {"status": "answered", "option_index": index,
            "answer": option["label"]}
