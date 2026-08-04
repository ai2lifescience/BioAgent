"""Helpers for runner-declared dotted configuration paths."""

from __future__ import annotations

from typing import Any


def get_config_value(config: dict[str, Any], key: str, default: Any = None) -> Any:
    """Read a top-level or dotted mapping key without mutating the config."""
    current: Any = config
    for part in _key_parts(key):
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    return current


def set_config_value(config: dict[str, Any], key: str, value: Any) -> None:
    """Set a top-level or dotted mapping key, creating intermediate mappings."""
    parts = _key_parts(key)
    current: dict[str, Any] = config
    for part in parts[:-1]:
        child = current.get(part)
        if child is None:
            child = {}
            current[part] = child
        if not isinstance(child, dict):
            raise ValueError(
                f"Cannot set dotted config key '{key}': '{part}' is not a mapping."
            )
        current = child
    current[parts[-1]] = value


def _key_parts(key: str) -> list[str]:
    parts = [part.strip() for part in str(key or "").split(".")]
    if not parts or any(not part for part in parts):
        raise ValueError(f"Invalid config key: {key!r}")
    return parts
