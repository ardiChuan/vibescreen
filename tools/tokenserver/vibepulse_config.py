"""Strict, private saved feature switches for the VibePulse host service."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Tuple


_FIELDS = frozenset({
    "claude_interactions",
    "codex_interactions",
    "interaction_detail",
})
_MAX_CONFIG_BYTES = 16 * 1024


class ConfigError(ValueError):
    """The saved configuration could not be trusted or persisted."""


@dataclass(frozen=True)
class VibePulseConfig:
    claude_interactions: bool = False
    codex_interactions: bool = False
    interaction_detail: bool = False


def _strict_object(pairs: Iterable[Tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ConfigError(f"duplicate configuration key: {key}")
        result[key] = value
    return result


def load_config(path: Path) -> VibePulseConfig:
    """Load a strict config file; a genuinely missing file means all off."""
    path = Path(path)
    try:
        if path.stat().st_size > _MAX_CONFIG_BYTES:
            raise ConfigError("configuration file is too large")
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return VibePulseConfig()
    except ConfigError:
        raise
    except (OSError, UnicodeError) as exc:
        raise ConfigError("cannot read configuration") from exc

    try:
        payload = json.loads(raw, object_pairs_hook=_strict_object)
    except ConfigError:
        raise
    except (json.JSONDecodeError, UnicodeError, ValueError) as exc:
        raise ConfigError("malformed configuration JSON") from exc
    if not isinstance(payload, dict):
        raise ConfigError("configuration must be a JSON object")
    unknown = set(payload) - _FIELDS
    if unknown:
        raise ConfigError("unknown configuration keys")
    if any(type(value) is not bool for value in payload.values()):
        raise ConfigError("configuration values must be booleans")
    return VibePulseConfig(**payload)


def save_config(path: Path, config: VibePulseConfig) -> None:
    """Atomically write the public feature switches with private modes."""
    if not isinstance(config, VibePulseConfig):
        raise ConfigError("config must be VibePulseConfig")
    path = Path(path)
    directory = path.parent
    temporary = None
    try:
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        if os.name == "posix":
            os.chmod(directory, 0o700)
        fd, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.", dir=directory)
        temporary = Path(temporary_name)
        try:
            if hasattr(os, "fchmod"):
                os.fchmod(fd, 0o600)
            payload = json.dumps(
                asdict(config), sort_keys=True, separators=(",", ":"),
            ).encode("utf-8") + b"\n"
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
        except Exception:
            try:
                os.close(fd)
            except OSError:
                pass
            raise
        os.replace(temporary, path)
        temporary = None
        if os.name == "posix":
            os.chmod(path, 0o600)
        try:
            directory_fd = os.open(directory, os.O_RDONLY)
        except OSError:
            directory_fd = None
        if directory_fd is not None:
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    except (OSError, TypeError, ValueError) as exc:
        raise ConfigError("cannot save configuration") from exc
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                pass


# Concise aliases for callers that already name the module in their import.
load = load_config
save = save_config
