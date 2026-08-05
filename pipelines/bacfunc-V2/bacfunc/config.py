"""BacFunc configuration discovery and path resolution."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, MutableMapping, Optional

import yaml

from .errors import ConfigurationError, DatabaseConfigurationError


PROJECT_NAME = "bacfunc"
CONFIG_ENV = "BACFUNC_CONFIG"
_ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


@dataclass(frozen=True)
class PipelineConfig:
    """Expanded configuration and resolved CPU count."""

    data: Mapping[str, Any]
    source: Path
    threads: int

    def value(self, *keys: str, required: bool = True) -> Any:
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

    def section(self, name: str) -> Mapping[str, Any]:
        value = self.value(name)
        if not isinstance(value, Mapping):
            raise ConfigurationError(f"Configuration section '{name}' must be a mapping.")
        return value

    def eggnog_path(self, key: str, required: bool = True) -> Optional[Path]:
        value = self.value("databases", "eggnog", key, required=required)
        if value in (None, ""):
            if required:
                if key == "data_dir":
                    raise DatabaseConfigurationError(
                        "eggNOG database path is not configured. "
                        "Set BACFUNC_EGGNOG_DATA_DIR or databases.eggnog.data_dir."
                    )
                raise DatabaseConfigurationError(f"eggNOG {key} is not configured.")
            return None
        return Path(str(value))


def _expand_string(value: str) -> str:
    missing = sorted({name for name in _ENV_PATTERN.findall(value) if name not in os.environ})
    if missing:
        raise ConfigurationError(
            "Unset environment variable(s) in configuration: " + ", ".join(missing)
        )
    expanded = _ENV_PATTERN.sub(lambda match: os.environ[match.group(1)], value)
    if _ENV_PATTERN.search(expanded):
        raise ConfigurationError(f"Unexpanded environment variable in value: {value}")
    return os.path.expanduser(expanded)


def _expand(value: Any) -> Any:
    if isinstance(value, str):
        return _expand_string(value)
    if isinstance(value, list):
        return [_expand(item) for item in value]
    if isinstance(value, Mapping):
        return {key: _expand(item) for key, item in value.items()}
    return value


def discover_config(explicit: Optional[Path] = None, cwd: Optional[Path] = None) -> Path:
    """Apply CLI, environment, CWD, project, and package-default precedence."""
    project_root = Path(__file__).resolve().parents[1]
    package_default = Path(__file__).resolve().parent / "default_config.yaml"
    if explicit is not None:
        candidates = [Path(explicit)]
    elif os.environ.get(CONFIG_ENV):
        candidates = [Path(_expand_string(os.environ[CONFIG_ENV]))]
    else:
        candidates = [(cwd or Path.cwd()) / "config.yaml", project_root / "config.yaml", package_default]
    for candidate in candidates:
        path = Path(os.path.expanduser(str(candidate))).resolve()
        if path.is_file():
            return path
        if explicit is not None or os.environ.get(CONFIG_ENV):
            raise ConfigurationError(f"Configuration file does not exist: {path}")
    raise ConfigurationError("No configuration file was found.")


def _read(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
    except OSError as exc:
        raise ConfigurationError(f"Cannot read configuration file: {path}") from exc
    except yaml.YAMLError as exc:
        raise ConfigurationError(f"Invalid YAML configuration: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigurationError(f"Configuration root must be a mapping: {path}")
    return data


def _set_database_environment(data: MutableMapping[str, Any]) -> None:
    databases = data.setdefault("databases", {})
    if not isinstance(databases, MutableMapping):
        raise ConfigurationError("Configuration section 'databases' must be a mapping.")
    eggnog = databases.setdefault("eggnog", {})
    if not isinstance(eggnog, MutableMapping):
        raise ConfigurationError("databases.eggnog must be a mapping.")
    if os.environ.get("BACFUNC_EGGNOG_DATA_DIR"):
        eggnog["data_dir"] = os.environ["BACFUNC_EGGNOG_DATA_DIR"]
    if os.environ.get("BACFUNC_EGGNOG_MANIFEST"):
        eggnog["manifest"] = os.environ["BACFUNC_EGGNOG_MANIFEST"]


def _resolve_paths(data: MutableMapping[str, Any], source: Path) -> None:
    eggnog = data.setdefault("databases", {}).setdefault("eggnog", {})
    for key in ("data_dir", "manifest"):
        value = eggnog.get(key)
        if value in (None, ""):
            continue
        path = Path(str(value))
        if not path.is_absolute():
            path = source.parent / path
        eggnog[key] = str(path.resolve())


def _validate(data: Mapping[str, Any]) -> int:
    pipeline = data.get("pipeline", {})
    if pipeline.get("sample_type") != "metagenome":
        raise ConfigurationError("pipeline.sample_type must be 'metagenome'.")
    raw_threads = pipeline.get("threads", "auto")
    if raw_threads == "auto":
        threads = max(1, os.cpu_count() or 1)
    else:
        try:
            threads = int(raw_threads)
        except (TypeError, ValueError) as exc:
            raise ConfigurationError("pipeline.threads must be 'auto' or an integer.") from exc
        if threads < 1:
            raise ConfigurationError("pipeline.threads must be at least 1.")
    tools = data.get("tools", {})
    assembler_options = [str(item) for item in tools.get("assembler", {}).get("options", [])]
    if any(item.lstrip("-").lower() == "isolate" for item in assembler_options):
        raise ConfigurationError("Metagenome assembly must not enable isolate mode.")
    prokka_options = [str(item) for item in tools.get("prokka", {}).get("options", [])]
    if "--metagenome" not in prokka_options:
        raise ConfigurationError("Prokka configuration must include --metagenome.")
    eggnog = tools.get("eggnog", {})
    if str(eggnog.get("version")) != "2.1.15":
        raise ConfigurationError("tools.eggnog.version must be 2.1.15.")
    if str(eggnog.get("search_mode")).lower() != "diamond":
        raise ConfigurationError("tools.eggnog.search_mode must be diamond.")
    options = [str(item) for item in eggnog.get("options", [])]
    if "--itype" not in options or "proteins" not in options:
        raise ConfigurationError("eggNOG options must declare --itype proteins.")
    return threads


def load_config(explicit: Optional[Path] = None, cwd: Optional[Path] = None) -> PipelineConfig:
    """Load, expand, normalize, and validate configuration."""
    source = discover_config(explicit, cwd)
    data = _read(source)
    _set_database_environment(data)
    data = _expand(data)
    _resolve_paths(data, source)
    threads = _validate(data)
    data.setdefault("pipeline", {})["resolved_threads"] = threads
    return PipelineConfig(data=data, source=source, threads=threads)
