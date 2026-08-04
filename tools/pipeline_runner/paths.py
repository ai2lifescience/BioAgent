"""Path and naming helpers for approved pipeline folders."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PIPELINES_ROOT = PROJECT_ROOT / "pipelines"
DEFAULT_PIPELINE_NAME = "generic_shell"
PIPELINE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def assert_inside(path: Path, root: Path) -> None:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"Path must stay inside {root}: {path}") from exc


def resolve_pipeline_name(pipeline_name: str | None) -> str:
    name = pipeline_name or DEFAULT_PIPELINE_NAME
    if not PIPELINE_NAME_PATTERN.fullmatch(name):
        raise ValueError(
            "pipeline_name must be a single folder name containing only letters, "
            "numbers, underscore, hyphen, or dot."
        )
    return name


def resolve_pipeline_dir(pipeline_name: str) -> Path:
    pipeline_dir = (PIPELINES_ROOT / pipeline_name).resolve()
    assert_inside(pipeline_dir, PIPELINES_ROOT)
    if not pipeline_dir.is_dir():
        raise FileNotFoundError(f"Pipeline folder not found: {pipeline_dir}")
    return pipeline_dir


def resolve_pipeline_file(
    pipeline_dir: Path,
    relative_path: str | None,
    fallback: str,
    label: str,
) -> Path:
    value = Path(relative_path or fallback)
    if value.is_absolute():
        raise ValueError(f"{label} must be relative to the pipeline folder.")
    resolved = (pipeline_dir / value).resolve()
    assert_inside(resolved, pipeline_dir)
    if not resolved.is_file():
        raise FileNotFoundError(f"{label} not found: {resolved}")
    return resolved


def resolve_project_path(path: str | Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate.resolve()


def resolve_pipeline_input_path(path: str | Path, pipeline_dir: Path) -> Path:
    """Resolve base-config input from project root or the pipeline folder."""
    project_candidate = resolve_project_path(path)
    if project_candidate.exists():
        return project_candidate
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate.resolve()
    return (pipeline_dir / candidate).resolve()


def resolve_optional_artifact_dir(artifact_dir: str | Path | None) -> Path | None:
    if not artifact_dir:
        return None
    base = Path(artifact_dir)
    if not base.is_absolute():
        base = PROJECT_ROOT / base
    return base.resolve()


def resolve_pipeline_run_dir(
    artifact_dir: str | Path | None,
    pipeline_name: str,
    run_id: str | None = None,
) -> Path:
    base = Path(artifact_dir) if artifact_dir else PROJECT_ROOT / "runtime"
    if not base.is_absolute():
        base = PROJECT_ROOT / base
    return base.joinpath("pipelines", pipeline_name, safe_label(run_id, "run")).resolve()


def resolve_pipeline_output_path(path: str | Path, run_dir: Path) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate.resolve()
    resolved = (run_dir / candidate).resolve()
    assert_inside(resolved, run_dir)
    return resolved


def safe_label(label: str | None, fallback: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_.-]+", "_", label or fallback).strip("_")
    return value or fallback


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))
