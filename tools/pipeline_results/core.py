"""Collect and summarize artifacts from the latest completed pipeline run."""

from __future__ import annotations

import csv
import json
from pathlib import Path
import shutil
from typing import Any
import zipfile


PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXCLUDED_KINDS = {"config", "directory", "input", "upload"}


def _project_file(path_value: str) -> Path | None:
    raw = Path(path_value)
    candidate = raw if raw.is_absolute() else PROJECT_ROOT / raw
    resolved = candidate.resolve()
    try:
        resolved.relative_to(PROJECT_ROOT)
    except ValueError:
        return None
    return resolved if resolved.is_file() else None


def _project_directory(path_value: str) -> Path:
    raw = Path(path_value)
    candidate = raw if raw.is_absolute() else PROJECT_ROOT / raw
    resolved = candidate.resolve()
    try:
        resolved.relative_to(PROJECT_ROOT)
    except ValueError as exc:
        raise ValueError("collection_dir must be inside the BioAgent project") from exc
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def _pipeline_name(path: Path) -> str:
    parts = path.parts
    for index in range(len(parts) - 1):
        if parts[index] == "pipelines":
            return parts[index + 1]
    return "pipeline"


def _selected_artifacts(
    artifacts: list[dict[str, Any]],
    requested_pipeline: str,
) -> tuple[str, str, list[dict[str, Any]]]:
    eligible: list[dict[str, Any]] = []
    for artifact in artifacts:
        if artifact.get("source_skill") != "pipeline_runner":
            continue
        if str(artifact.get("kind") or "") in EXCLUDED_KINDS:
            continue
        path = _project_file(str(artifact.get("path") or ""))
        if path is None:
            continue
        pipeline_name = _pipeline_name(path)
        if requested_pipeline and pipeline_name != requested_pipeline:
            continue
        eligible.append({**artifact, "resolved_path": path, "pipeline_name": pipeline_name})

    if not eligible:
        return "", "", []
    latest = eligible[-1]
    run_id = str(latest.get("run_id") or "")
    pipeline_name = str(latest["pipeline_name"])
    selected = [
        artifact
        for artifact in eligible
        if str(artifact.get("run_id") or "") == run_id
        and artifact["pipeline_name"] == pipeline_name
    ]
    deduplicated: list[dict[str, Any]] = []
    seen: set[Path] = set()
    for artifact in selected:
        path = artifact["resolved_path"]
        if path in seen:
            continue
        seen.add(path)
        deduplicated.append(artifact)
    return pipeline_name, run_id, deduplicated


def _read_metrics(paths: list[Path]) -> dict[str, Any]:
    metrics_path = next((path for path in paths if path.name == "metrics.json"), None)
    if metrics_path is None:
        return {}
    try:
        value = json.loads(metrics_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _read_tables(paths: list[Path], max_rows: int) -> list[dict[str, Any]]:
    tables: list[dict[str, Any]] = []
    for path in paths:
        if path.suffix.lower() != ".tsv":
            continue
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            columns = [str(column) for column in (reader.fieldnames or [])]
            rows: list[dict[str, str]] = []
            row_count = 0
            for row in reader:
                row_count += 1
                if len(rows) < max_rows:
                    rows.append({column: str(row.get(column) or "") for column in columns})
        tables.append(
            {
                "name": path.name,
                "columns": columns,
                "row_count": row_count,
                "rows": rows,
                "truncated": row_count > len(rows),
            }
        )
    return tables


def _archive_name(path: Path, used: set[str]) -> str:
    name = path.name
    if name not in used:
        used.add(name)
        return name
    index = 2
    while f"{path.stem}-{index}{path.suffix}" in used:
        index += 1
    name = f"{path.stem}-{index}{path.suffix}"
    used.add(name)
    return name


def collect_pipeline_results(
    artifacts: list[dict[str, Any]],
    collection_dir: str,
    pipeline_name: str = "",
    max_table_rows: int = 10,
) -> dict[str, Any]:
    """Collect the latest matching pipeline outputs into a bundle and previews."""
    requested_pipeline = str(pipeline_name or "").strip()
    row_limit = max(1, min(50, int(max_table_rows)))
    selected_name, run_id, selected = _selected_artifacts(artifacts, requested_pipeline)
    if not selected:
        return {
            "status": "no_results",
            "pipeline_name": requested_pipeline,
            "output_count": 0,
            "outputs": [],
            "metrics": {},
            "tables": [],
            "files": [],
            "image_paths": [],
        }

    paths = [artifact["resolved_path"] for artifact in selected]
    destination = _project_directory(collection_dir)
    archive_path = destination / f"{selected_name}-results.zip"
    used_names: set[str] = set()
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in paths:
            archive.write(path, arcname=_archive_name(path, used_names))

    copied_images: list[str] = []
    for path in paths:
        if path.suffix.lower() != ".png":
            continue
        copied_path = destination / path.name
        shutil.copy2(path, copied_path)
        copied_images.append(str(copied_path))

    outputs = [
        {
            "name": path.name,
            "kind": str(artifact.get("kind") or "file"),
            "bytes": path.stat().st_size,
        }
        for artifact, path in zip(selected, paths)
    ]
    collection_files = [str(archive_path), *copied_images]
    return {
        "status": "ok",
        "pipeline_name": selected_name,
        "pipeline_run_id": run_id,
        "output_count": len(paths),
        "outputs": outputs,
        "metrics": _read_metrics(paths),
        "tables": _read_tables(paths, row_limit),
        "bundle_path": str(archive_path),
        "image_paths": copied_images,
        "files": collection_files,
    }
