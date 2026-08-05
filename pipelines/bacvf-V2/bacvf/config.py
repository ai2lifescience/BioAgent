"""Configuration discovery, expansion, validation, and path resolution."""

from __future__ import annotations

import os
import re
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, MutableMapping, Optional

import yaml

from .errors import ConfigurationError, DatabaseConfigurationError


PROJECT_NAME = "bacvf"
CONFIG_ENV = "BACVF_CONFIG"
DATABASE_ENVIRON = {
    "BACVF_ABRICATE_DATADIR": ("databases", "abricate_datadir"),
    "BACVF_VFDB_METADATA": ("databases", "metadata"),
    "BACVF_VFDB_MANIFEST": ("databases", "manifest"),
}
_ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


@dataclass(frozen=True)
class PipelineConfig:
    """Fully expanded immutable view of one YAML configuration."""

    data: Mapping[str, Any]
    source: Path
    threads: int

    def section(self, name: str) -> Mapping[str, Any]:
        """Return a required top-level mapping."""
        value = self.data.get(name)
        if not isinstance(value, Mapping):
            raise ConfigurationError(f"Configuration section '{name}' must be a mapping.")
        return value

    def value(self, *keys: str, required: bool = True) -> Any:
        """Read a nested value with a clear error for absent keys."""
        current: Any = self.data
        for key in keys:
            if not isinstance(current, Mapping) or key not in current:
                if required:
                    raise ConfigurationError(
                        f"Missing configuration value: {'.'.join(keys)}"
                    )
                return None
            current = current[key]
        return current

    def database_path(self, key: str, required: bool = True) -> Optional[Path]:
        """Return a normalized database path."""
        value = self.value("databases", key, required=required)
        if value in (None, ""):
            if required:
                labels = {
                    "abricate_datadir": (
                        "VFDB ABRicate database path is not configured. "
                        "Set BACVF_ABRICATE_DATADIR or databases.abricate_datadir."
                    ),
                    "metadata": (
                        "VFDB metadata path is not configured. "
                        "Set BACVF_VFDB_METADATA or databases.metadata."
                    ),
                }
                raise DatabaseConfigurationError(labels.get(key, f"{key} is not configured."))
            return None
        return Path(str(value))


def _deep_merge(base: MutableMapping[str, Any], update: Mapping[str, Any]) -> None:
    for key, value in update.items():
        if isinstance(value, Mapping) and isinstance(base.get(key), MutableMapping):
            _deep_merge(base[key], value)
        else:
            base[key] = deepcopy(value)


def _expand_string(value: str) -> str:
    missing = sorted({name for name in _ENV_PATTERN.findall(value) if name not in os.environ})
    if missing:
        joined = ", ".join(missing)
        raise ConfigurationError(f"Unset environment variable(s) in configuration: {joined}")
    expanded = _ENV_PATTERN.sub(lambda match: os.environ[match.group(1)], value)
    if _ENV_PATTERN.search(expanded):
        raise ConfigurationError(f"Unexpanded environment variable in value: {value}")
    return os.path.expanduser(expanded)


def _expand_tree(value: Any) -> Any:
    if isinstance(value, str):
        return _expand_string(value)
    if isinstance(value, list):
        return [_expand_tree(item) for item in value]
    if isinstance(value, Mapping):
        return {key: _expand_tree(item) for key, item in value.items()}
    return value


def _set_nested(data: MutableMapping[str, Any], keys: tuple[str, ...], value: Any) -> None:
    current = data
    for key in keys[:-1]:
        child = current.setdefault(key, {})
        if not isinstance(child, MutableMapping):
            raise ConfigurationError(f"Cannot apply environment override to {'.'.join(keys)}")
        current = child
    current[keys[-1]] = value


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            loaded = yaml.safe_load(handle) or {}
    except OSError as exc:
        raise ConfigurationError(f"Cannot read configuration file: {path}") from exc
    except yaml.YAMLError as exc:
        raise ConfigurationError(f"Invalid YAML configuration: {path}: {exc}") from exc
    if not isinstance(loaded, dict):
        raise ConfigurationError(f"Configuration root must be a mapping: {path}")
    return loaded


def discover_config(explicit: Optional[Path] = None, cwd: Optional[Path] = None) -> Path:
    """Apply the documented five-level configuration precedence."""
    project_root = Path(__file__).resolve().parents[1]
    package_default = Path(__file__).resolve().parent / "default_config.yaml"
    candidates: list[Path] = []
    if explicit is not None:
        candidates.append(Path(explicit))
    elif os.environ.get(CONFIG_ENV):
        candidates.append(Path(_expand_string(os.environ[CONFIG_ENV])))
    else:
        candidates.extend([(cwd or Path.cwd()) / "config.yaml", project_root / "config.yaml"])
        candidates.append(package_default)
    for candidate in candidates:
        expanded = Path(os.path.expanduser(str(candidate))).resolve()
        if expanded.is_file():
            return expanded
        if explicit is not None or os.environ.get(CONFIG_ENV):
            raise ConfigurationError(f"Configuration file does not exist: {expanded}")
    raise ConfigurationError("No configuration file was found.")


def _resolve_database_paths(data: MutableMapping[str, Any], source: Path) -> None:
    databases = data.setdefault("databases", {})
    if not isinstance(databases, MutableMapping):
        raise ConfigurationError("Configuration section 'databases' must be a mapping.")
    for key in ("abricate_datadir", "metadata", "manifest"):
        value = databases.get(key)
        if value in (None, ""):
            continue
        path = Path(str(value))
        if not path.is_absolute():
            path = source.parent / path
        databases[key] = str(path.resolve())


def _validate(data: Mapping[str, Any]) -> int:
    pipeline = data.get("pipeline", {})
    if not isinstance(pipeline, Mapping):
        raise ConfigurationError("Configuration section 'pipeline' must be a mapping.")
    if pipeline.get("sample_type") != "metagenome":
        raise ConfigurationError("pipeline.sample_type must be 'metagenome'.")
    raw_threads = pipeline.get("threads", "auto")
    if raw_threads == "auto":
        threads = max(1, os.cpu_count() or 1)
    else:
        try:
            threads = int(raw_threads)
        except (TypeError, ValueError) as exc:
            raise ConfigurationError("pipeline.threads must be 'auto' or a positive integer.") from exc
        if threads < 1:
            raise ConfigurationError("pipeline.threads must be at least 1.")
    tools = data.get("tools", {})
    if not isinstance(tools, Mapping):
        raise ConfigurationError("Configuration section 'tools' must be a mapping.")
    assembler = tools.get("assembler", {})
    assembler_options = [str(item) for item in assembler.get("options", [])]
    if any(item.lstrip("-").lower() == "isolate" for item in assembler_options):
        raise ConfigurationError("Metagenome assembly configuration must not enable isolate mode.")
    prokka_options = [str(item) for item in tools.get("prokka", {}).get("options", [])]
    if "--metagenome" not in prokka_options:
        raise ConfigurationError("Prokka configuration must include --metagenome.")
    return threads


def load_config(explicit: Optional[Path] = None, cwd: Optional[Path] = None) -> PipelineConfig:
    """Load, expand, normalize, and validate one configuration."""
    source = discover_config(explicit, cwd)
    data: dict[str, Any] = _read_yaml(source)
    for variable, keys in DATABASE_ENVIRON.items():
        if os.environ.get(variable):
            _set_nested(data, keys, os.environ[variable])
    data = _expand_tree(data)
    _resolve_database_paths(data, source)
    threads = _validate(data)
    data.setdefault("pipeline", {})["resolved_threads"] = threads
    return PipelineConfig(data=data, source=source, threads=threads)
