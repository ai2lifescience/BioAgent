"""BioAgent YAML configuration entry point for bactmut-fastq."""

from __future__ import annotations

import json
import math
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml


class ConfigError(ValueError):
    """Raised when a BioAgent runtime configuration is invalid."""


_OUTPUT_DEFAULTS = {
    "matrix_path": "matrix.tsv",
    "variants_path": "variants.tsv",
    "variants_summary_path": "variants_summary.txt",
    "final_tree_path": "final_tree.nwk",
    "tree_alignment_path": "tree.fasta",
    "treefile_path": "tree.treefile",
    "iqtree_report_path": "tree.iqtree",
    "iqtree_log_path": "tree.log",
    "pipeline_log_path": "pipeline.log",
}
_REQUIRED_OUTPUT_KEYS = (
    "report_path",
    "metrics_path",
    "matrix_path",
    "variants_path",
    "variants_summary_path",
)


@dataclass(frozen=True)
class PipelineConfig:
    label: str
    input_path: Path
    reference_path: Path | None
    output_dir: Path
    output_paths: Mapping[str, Path]
    reference_mode: str
    species: str | None
    taxonid: str | None
    threads: int
    min_coverage: float
    window_size: int
    step_size: int
    sd_threshold: float
    verbose: bool

    def pipeline_arguments(self) -> dict[str, object]:
        return {
            "input": str(self.input_path),
            "output": str(self.output_dir),
            "reference": str(self.reference_path) if self.reference_mode == "local" else None,
            "species": self.species if self.reference_mode == "species" else None,
            "taxonid": self.taxonid if self.reference_mode == "taxonid" else None,
            "threads": self.threads,
            "min_coverage": self.min_coverage,
            "window_size": self.window_size,
            "step_size": self.step_size,
            "sd_threshold": self.sd_threshold,
            "verbose": self.verbose,
        }


def load_config(config_path: str | Path) -> PipelineConfig:
    path = Path(config_path).expanduser()
    if not path.is_file():
        raise ConfigError(f"configuration file not found: {path}")
    try:
        with path.open(encoding="utf-8") as stream:
            raw = yaml.safe_load(stream)
    except yaml.YAMLError as error:
        raise ConfigError(f"invalid YAML in {path}: {error}") from error
    if not isinstance(raw, Mapping):
        raise ConfigError("configuration root must be a YAML mapping")
    return parse_config(raw, base_dir=path.resolve().parent)


def parse_config(raw: Mapping[str, Any], *, base_dir: Path) -> PipelineConfig:
    base_dir = Path(base_dir).resolve()
    params = raw.get("params")
    if not isinstance(params, Mapping):
        params = {}

    def param(key: str, default: Any = None) -> Any:
        return raw.get(key, params.get(key, default))

    label = _nonempty_string(raw.get("label"), "label")
    input_path = _resolve_path(raw.get("input_path"), "input_path", base_dir)
    output_dir = _resolve_path(raw.get("output_dir"), "output_dir", base_dir)
    reference_path = _optional_path(raw.get("reference_path"), "reference_path", base_dir)
    reference_mode = _choice(
        param("reference_mode", "local"),
        "params.reference_mode",
        {"local", "species", "taxonid"},
    )
    species = _optional_string(param("species"))
    taxonid = _optional_taxonid(param("taxonid"))
    if reference_mode == "local" and reference_path is None:
        raise ConfigError("reference_mode 'local' requires reference_path")
    if reference_mode == "species" and species is None:
        raise ConfigError("reference_mode 'species' requires non-empty params.species")
    if reference_mode == "taxonid" and taxonid is None:
        raise ConfigError("reference_mode 'taxonid' requires positive params.taxonid")

    output_paths: dict[str, Path] = {
        "report_path": _resolve_path(raw.get("report_path"), "report_path", base_dir),
        "metrics_path": _resolve_path(raw.get("metrics_path"), "metrics_path", base_dir),
    }
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
        reference_path=reference_path,
        output_dir=output_dir,
        output_paths=output_paths,
        reference_mode=reference_mode,
        species=species,
        taxonid=taxonid,
        threads=_positive_integer(param("threads", 1), "params.threads"),
        min_coverage=_fraction(param("min_coverage", 0.9), "params.min_coverage"),
        window_size=_positive_integer(param("window_size", 50), "params.window_size"),
        step_size=_positive_integer(param("step_size", 10), "params.step_size"),
        sd_threshold=_nonnegative_float(
            param("sd_threshold", 3.0), "params.sd_threshold"
        ),
        verbose=_boolean(param("verbose", False), "params.verbose"),
    )


def run_config(config: PipelineConfig) -> int:
    if not config.input_path.is_dir():
        raise ConfigError(f"input_path is not a directory: {config.input_path}")
    if config.reference_mode == "local":
        assert config.reference_path is not None
        if not config.reference_path.is_file():
            raise ConfigError(f"reference_path is not a file: {config.reference_path}")
    missing_tools = [
        executable
        for executable in ("minimap2", "samtools", "bcftools")
        if shutil.which(executable) is None
    ]
    if missing_tools:
        raise ConfigError(
            "required executable(s) not found on PATH: " + ", ".join(missing_tools)
        )

    config.output_dir.mkdir(parents=True, exist_ok=True)
    from .cli import configure_logging, run_pipeline

    configure_logging(config.output_dir, config.verbose)
    result = run_pipeline(config.pipeline_arguments())
    if int(result or 0) != 0:
        raise RuntimeError(f"bactmut-fastq exited with status {result}")

    _publish_outputs(config)
    metrics = _build_metrics(config)
    _write_metrics(config.output_paths["metrics_path"], metrics)
    _write_report(config, metrics)
    _assert_required_outputs(config)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print(
            "Usage: python3 -m bactmut_fastq.config_runner CONFIG.yaml",
            file=sys.stderr,
        )
        return 2
    try:
        return run_config(load_config(args[0]))
    except (
        ConfigError,
        OSError,
        RuntimeError,
        ValueError,
        subprocess.SubprocessError,
    ) as error:
        print(f"bactmut_fastq pipeline error: {error}", file=sys.stderr)
        return 1


def _publish_outputs(config: PipelineConfig) -> None:
    for key, filename in _OUTPUT_DEFAULTS.items():
        source = config.output_dir / filename
        destination = config.output_paths[key]
        if not source.is_file() or source.resolve() == destination.resolve():
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def _build_metrics(config: PipelineConfig) -> dict[str, object]:
    summary = _read_key_value_file(config.output_dir / "variants_summary.txt")
    matrix_path = config.output_dir / "matrix.tsv"
    sample_count = None
    if matrix_path.is_file():
        with matrix_path.open(encoding="utf-8") as handle:
            header = handle.readline().rstrip("\n").split("\t")
        sample_count = max(0, len(header) - 1)

    final_positions = _as_integer(summary.get("after_recombination_filter"))
    final_tree = config.output_dir / "final_tree.nwk"
    if final_tree.is_file():
        tree_status = "completed"
    elif final_positions == 0:
        tree_status = "skipped: no SNPs remained after filtering"
    else:
        tree_status = "not generated (IQ-TREE unavailable or failed)"
    return {
        "pipeline": "bactmut_fastq",
        "label": config.label,
        "status": "completed",
        "reference_mode": config.reference_mode,
        "sample_count": sample_count,
        "initial_variant_positions": _as_integer(
            summary.get("initial_variant_positions")
        ),
        "after_coverage_filter": _as_integer(summary.get("after_coverage_filter")),
        "final_snp_positions": final_positions,
        "coverage_removed": _as_integer(summary.get("coverage_removed")),
        "recombination_removed": _as_integer(summary.get("recombination_removed")),
        "tree_status": tree_status,
    }


def _read_key_value_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        if "\t" in line:
            key, value = line.split("\t", 1)
            values[key] = value
    return values


def _as_integer(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _write_metrics(path: Path, metrics: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_report(config: PipelineConfig, metrics: Mapping[str, object]) -> None:
    summary_path = config.output_dir / "variants_summary.txt"
    summary = (
        summary_path.read_text(encoding="utf-8").strip()
        if summary_path.is_file()
        else "Variant summary was not available."
    )
    lines = [
        f"# {config.label}",
        "",
        "BactMut FASTQ completed successfully.",
        "",
        "## Key metrics",
        "",
        f"- Samples: {metrics.get('sample_count')}",
        f"- Initial variant positions: {metrics.get('initial_variant_positions')}",
        f"- Final SNP positions: {metrics.get('final_snp_positions')}",
        f"- Tree: {metrics.get('tree_status')}",
        "",
        "## Variant summary",
        "",
        "```text",
        summary,
        "```",
        "",
        "The SNP matrix, annotated variant table, per-sample calling files, and "
        "optional IQ-TREE files are available in the configured output directory.",
        "",
    ]
    path = config.output_paths["report_path"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def _assert_required_outputs(config: PipelineConfig) -> None:
    missing = [
        str(config.output_paths[key])
        for key in _REQUIRED_OUTPUT_KEYS
        if not config.output_paths[key].is_file()
    ]
    if missing:
        raise RuntimeError("pipeline did not generate required output(s): " + ", ".join(missing))


def _resolve_path(value: Any, field: str, base_dir: Path) -> Path:
    text = _nonempty_string(value, field)
    path = Path(text).expanduser()
    return path.resolve() if path.is_absolute() else (base_dir / path).resolve()


def _optional_path(value: Any, field: str, base_dir: Path) -> Path | None:
    if value in (None, ""):
        return None
    return _resolve_path(value, field, base_dir)


def _nonempty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{field} must be a non-empty string")
    return value.strip()


def _optional_string(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise ConfigError("optional text parameters must be strings")
    return value.strip() or None


def _choice(value: Any, field: str, choices: set[str]) -> str:
    text = _nonempty_string(value, field).lower()
    if text not in choices:
        raise ConfigError(f"{field} must be one of: {', '.join(sorted(choices))}")
    return text


def _integer(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise ConfigError(f"{field} must be an integer")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError as error:
            raise ConfigError(f"{field} must be an integer") from error
    raise ConfigError(f"{field} must be an integer")


def _positive_integer(value: Any, field: str) -> int:
    integer = _integer(value, field)
    if integer < 1:
        raise ConfigError(f"{field} must be a positive integer")
    return integer


def _float(value: Any, field: str) -> float:
    if isinstance(value, bool):
        raise ConfigError(f"{field} must be numeric")
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ConfigError(f"{field} must be numeric") from error
    if not math.isfinite(number):
        raise ConfigError(f"{field} must be finite")
    return number


def _fraction(value: Any, field: str) -> float:
    number = _float(value, field)
    if not 0 < number <= 1:
        raise ConfigError(f"{field} must be greater than 0 and at most 1")
    return number


def _nonnegative_float(value: Any, field: str) -> float:
    number = _float(value, field)
    if number < 0:
        raise ConfigError(f"{field} must be non-negative")
    return number


def _boolean(value: Any, field: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in {"true", "false"}:
        return value.strip().lower() == "true"
    raise ConfigError(f"{field} must be true or false")


def _optional_taxonid(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(_positive_integer(value, "params.taxonid"))


if __name__ == "__main__":
    raise SystemExit(main())
