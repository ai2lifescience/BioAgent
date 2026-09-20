"""Shared YAML config helpers for pipeline wrappers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_yaml_config(path: str | Path) -> dict[str, Any]:
    """Load a pipeline YAML config as a mapping."""
    config_path = Path(path)
    loaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise ValueError(f"Pipeline config must be a YAML mapping: {config_path}")
    return dict(loaded)


def write_yaml_config(config: dict[str, Any], path: str | Path) -> None:
    """Write a runtime pipeline config as YAML."""
    config_path = Path(path)
    config_path.write_text(
        yaml.safe_dump(
            config,
            sort_keys=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
