"""BioAgent YAML configuration entry point for virmut."""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml


class ConfigError(ValueError):
    """Raised when a BioAgent configuration is invalid."""


_OUTPUT_DEFAULTS = {
    "matrix_path": "matrix.tsv",
    "variants_path": "variants.tsv",
    "summary_path": "variants_summary.txt",
    "tree_fasta_path": "tree.fasta",
    "treefile_path": "tree.treefile",
    "iqtree_report_path": "tree.iqtree",
    "iqtree_log_path": "tree.log",
}
_CORE_OUTPUT_KEYS = ("matrix_path", "variants_path", "summary_path")


@dataclass(frozen=True)
class PipelineConfig:
    """Validated and path-normalized pipeline configuration."""

    label: str
    input_path: Path
    output_dir: Path
    mode: str
    reference_mode: str
    threads: int
    reference_path: Path | None
    species: str | None
    taxonid: str | None
    output_paths: Mapping[str, Path]

    def cli_argv(self) -> list[str]:
        argv = [
            "--input",
            str(self.input_path),
            "--output",
            str(self.output_dir),
            "--mode",
            self.mode,
            "--threads",
            str(self.threads),
        ]
        if self.reference_mode == "local":
            assert self.reference_path is not None
            argv.extend(["--reference", str(self.reference_path)])
        elif self.reference_mode == "species":
            assert self.species is not None
            argv.extend(["--species", self.species])
        else:
            assert self.taxonid is not None
            argv.extend(["--taxonid", self.taxonid])
        return argv


def load_config(config_path: str | Path) -> PipelineConfig:
    """Load, validate, and normalize one YAML configuration file."""
    path = Path(config_path).expanduser()
    if not path.is_file():
        raise ConfigError(f"configuration file not found: {path}")

    try:
        with path.open(encoding="utf-8") as stream:
            raw = yaml.safe_load(stream)
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in {path}: {exc}") from exc
    except OSError as exc:
        raise ConfigError(f"cannot read configuration file {path}: {exc}") from exc

    if not isinstance(raw, Mapping):
        raise ConfigError("configuration root must be a YAML mapping")
    return parse_config(raw, base_dir=path.resolve().parent)


def parse_config(raw: Mapping[str, Any], *, base_dir: Path) -> PipelineConfig:
    """Validate a configuration mapping and resolve its filesystem paths."""
    base_dir = Path(base_dir).resolve()
    label = _nonempty_string(raw.get("label"), "label")
    input_path = _resolve_path(raw.get("input_path"), "input_path", base_dir)
    output_dir = _resolve_path(raw.get("output_dir"), "output_dir", base_dir)

    params = raw.get("params")
    if not isinstance(params, Mapping):
        params = {}

    def _resolve_param(key):
        return raw.get(key, params.get(key))

    mode = _normalized_choice(_resolve_param("mode"), "mode", {"fasta", "fastq"})
    reference_mode = _normalized_choice(
        _resolve_param("reference_mode"),
        "reference_mode",
        {"local", "species", "taxonid"},
    )
    threads = _positive_integer(_resolve_param("threads"), "threads")

    reference_value = raw.get("reference_path")
    reference_path = None
    if reference_value not in (None, ""):
        reference_path = _resolve_path(reference_value, "reference_path", base_dir)

    species_value = _resolve_param("species")
    if species_value is not None and not isinstance(species_value, str):
        raise ConfigError("species must be a string")
    species = species_value.strip() if isinstance(species_value, str) else ""

    taxonid_value = _resolve_param("taxonid")
    if isinstance(taxonid_value, str) and taxonid_value.lower() in ("taxonid", "none", ""):
        taxonid_value = None
    taxonid = _optional_taxonid(taxonid_value) if taxonid_value is not None else None

    supplied = {
        "local": reference_path is not None,
        "species": bool(species),
        "taxonid": taxonid is not None,
    }
    if not supplied[reference_mode]:
        required = {
            "local": "reference_path",
            "species": "non-empty params.species",
            "taxonid": "positive integer params.taxonid",
        }[reference_mode]
        raise ConfigError(f"reference_mode '{reference_mode}' requires {required}")

    output_paths: dict[str, Path] = {}
    for key, filename in _OUTPUT_DEFAULTS.items():
        value = raw.get(key)
        output_paths[key] = (
            _resolve_path(value, key, base_dir)
            if value not in (None, "")
            else output_dir / filename
        )

    return PipelineConfig(
        label=label,
        input_path=input_path,
        output_dir=output_dir,
        mode=mode,
        reference_mode=reference_mode,
        threads=threads,
        reference_path=reference_path,
        species=species or None,
        taxonid=taxonid,
        output_paths=output_paths,
    )


def run_config(config: PipelineConfig) -> int:
    """Run the existing CLI and publish configured output paths."""
    if not config.input_path.exists():
        raise ConfigError(f"input_path does not exist: {config.input_path}")
    if config.reference_mode == "local" and not config.reference_path.is_file():
        raise ConfigError(f"reference_path is not a file: {config.reference_path}")
    try:
        config.output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ConfigError(f"cannot create output_dir {config.output_dir}: {exc}") from exc

    from virmut.cli import main as cli_main
    from virmut.tree import InsufficientSamplesForTreeError

    tree_status: str | None = None
    try:
        result = cli_main(config.cli_argv())
    except InsufficientSamplesForTreeError as exc:
        tree_status = f"phylogenetic tree was not generated: {exc}"
        result = 0
    except ValueError as exc:
        if str(exc) != "no variant positions":
            raise
        tree_status = "phylogenetic tree was not generated: no variant positions"
        result = 0

    _publish_outputs(config)
    missing_core = [
        str(config.output_paths[key])
        for key in _CORE_OUTPUT_KEYS
        if not config.output_paths[key].is_file()
    ]
    if missing_core:
        raise RuntimeError("pipeline did not generate core output(s): " + ", ".join(missing_core))

    missing_tree = [
        str(config.output_paths[key])
        for key in _OUTPUT_DEFAULTS
        if key not in _CORE_OUTPUT_KEYS and not config.output_paths[key].is_file()
    ]
    if tree_status:
        print(f"virmut status: {tree_status}", file=sys.stderr)
    elif missing_tree:
        print(
            "virmut status: optional IQ-TREE output(s) not present: "
            + ", ".join(missing_tree),
            file=sys.stderr,
        )
    return int(result or 0)


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print("Usage: python -m virmut.config_runner CONFIG.yaml", file=sys.stderr)
        return 2
    try:
        return run_config(load_config(args[0]))
    except (
        ConfigError,
        OSError,
        RuntimeError,
        ValueError,
        subprocess.CalledProcessError,
    ) as exc:
        print(f"virmut pipeline error: {exc}", file=sys.stderr)
        return 1


def _publish_outputs(config: PipelineConfig) -> None:
    for key, filename in _OUTPUT_DEFAULTS.items():
        source = config.output_dir / filename
        destination = config.output_paths[key]
        if not source.is_file() or source.resolve() == destination.resolve():
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def _resolve_path(value: Any, field: str, base_dir: Path) -> Path:
    text = _nonempty_string(value, field)
    path = Path(text).expanduser()
    return path.resolve() if path.is_absolute() else (base_dir / path).resolve()


def _nonempty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{field} must be a non-empty string")
    return value.strip()


def _normalized_choice(value: Any, field: str, choices: set[str]) -> str:
    text = _nonempty_string(value, field).lower()
    if text not in choices:
        raise ConfigError(f"{field} must be one of: {', '.join(sorted(choices))}")
    return text


def _positive_integer(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise ConfigError(f"{field} must be a positive integer")
    if isinstance(value, int):
        integer = value
    elif isinstance(value, str) and value.strip().isdigit():
        integer = int(value.strip())
    else:
        raise ConfigError(f"{field} must be a positive integer")
    if integer <= 0:
        raise ConfigError(f"{field} must be a positive integer")
    return integer


def _optional_taxonid(value: Any) -> str | None:
    if value is None:
        return None
    if value in (None, ""):
        return None
    return str(_positive_integer(value, "params.taxonid"))


if __name__ == "__main__":
    raise SystemExit(main())
