"""Artifact classification shared by tools and the application adapter.

The SDK sandbox owns workspace execution. These small helpers describe biological
output files so FunctionTools can report files without importing the harness.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

ARTIFACT_KIND_BY_KEY = {
    "fasta_path": "fasta",
    "fasta_paths": "fasta",
    "structure_path": "structure",
    "structure_paths": "structure",
    "metadata_path": "metadata",
    "metadata_paths": "metadata",
    "report_path": "report",
    "image_path": "image",
    "image_paths": "image",
    "genome_map_path": "image",
    "session_input_path": "input",
    "upload_path": "upload",
    "runner_config_path": "config",
    "raw_config_path": "config",
    "config_path": "config",
    "metrics_path": "metrics",
    "bakta_json_path": "metadata",
    "inference_path": "metadata",
    "hypotheticals_path": "metadata",
    "plot_svg_path": "image",
    "plot_png_path": "image",
    "output_dir": "directory",
}

ARTIFACT_KIND_BY_SUFFIX = {
    ".fa": "fasta",
    ".faa": "fasta",
    ".fasta": "fasta",
    ".ffn": "fasta",
    ".fna": "fasta",
    ".fq": "sequence",
    ".fastq": "sequence",
    ".dbn": "sequence_structure",
    ".sam": "sequence_alignment",
    ".bam": "sequence_alignment",
    ".bai": "sequence_alignment_index",
    ".bed": "genomic_interval",
    ".gb": "annotation",
    ".gbk": "annotation",
    ".gff": "annotation",
    ".gff3": "annotation",
    ".vcf": "variant",
    ".newick": "phylogenetic_tree",
    ".nwk": "phylogenetic_tree",
    ".tre": "phylogenetic_tree",
    ".tree": "phylogenetic_tree",
    ".gz": "compressed",
    ".bgz": "compressed",
    ".zip": "compressed",
    ".bcif": "structure",
    ".cif": "structure",
    ".mmcif": "structure",
    ".pdb": "structure",
    ".csv": "metadata",
    ".tsv": "metadata",
    ".md": "report",
    ".markdown": "report",
    ".pdf": "document",
    ".html": "report",
    ".png": "image",
    ".svg": "image",
    ".json": "config",
    ".yaml": "config",
    ".yml": "config",
    ".txt": "text",
    ".log": "text",
}

SUFFIX_ARTIFACT_KEYS = {
    "",
    "artifact",
    "artifacts",
    "created_file",
    "created_files",
    "file",
    "files",
    "path",
    "paths",
}

ARTIFACT_CONTENT_TYPES = {
    ".bcif": "application/octet-stream",
    ".cif": "chemical/x-mmcif; charset=utf-8",
    ".mmcif": "chemical/x-mmcif; charset=utf-8",
    ".pdb": "chemical/x-pdb; charset=utf-8",
    ".svg": "image/svg+xml; charset=utf-8",
    ".csv": "text/csv; charset=utf-8",
    ".tsv": "text/tab-separated-values; charset=utf-8",
    ".fa": "text/plain; charset=utf-8",
    ".faa": "text/plain; charset=utf-8",
    ".fasta": "text/plain; charset=utf-8",
    ".ffn": "text/plain; charset=utf-8",
    ".fna": "text/plain; charset=utf-8",
    ".fq": "text/plain; charset=utf-8",
    ".fastq": "text/plain; charset=utf-8",
    ".dbn": "text/plain; charset=utf-8",
    ".sam": "text/plain; charset=utf-8",
    ".bam": "application/octet-stream",
    ".bai": "application/octet-stream",
    ".bed": "text/plain; charset=utf-8",
    ".gb": "text/plain; charset=utf-8",
    ".gbk": "text/plain; charset=utf-8",
    ".gff": "text/plain; charset=utf-8",
    ".gff3": "text/plain; charset=utf-8",
    ".vcf": "text/plain; charset=utf-8",
    ".newick": "text/plain; charset=utf-8",
    ".nwk": "text/plain; charset=utf-8",
    ".tre": "text/plain; charset=utf-8",
    ".tree": "text/plain; charset=utf-8",
    ".gz": "application/gzip",
    ".bgz": "application/gzip",
    ".zip": "application/zip",
    ".md": "text/markdown; charset=utf-8",
    ".markdown": "text/markdown; charset=utf-8",
    ".pdf": "application/pdf",
    ".html": "text/html; charset=utf-8",
    ".png": "image/png",
    ".json": "application/json; charset=utf-8",
    ".yaml": "text/yaml; charset=utf-8",
    ".yml": "text/yaml; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
    ".log": "text/plain; charset=utf-8",
}

STRUCTURE_ARTIFACT_SUFFIXES = tuple(
    suffix for suffix, kind in ARTIFACT_KIND_BY_SUFFIX.items() if kind == "structure"
)
STRUCTURE_VIEWER_SUFFIXES = (".cif", ".mmcif", ".pdb")
IMAGE_ARTIFACT_SUFFIXES = tuple(
    suffix for suffix, kind in ARTIFACT_KIND_BY_SUFFIX.items() if kind == "image"
)
SERVABLE_ARTIFACT_SUFFIXES = tuple(sorted(ARTIFACT_CONTENT_TYPES))

RESULT_COUNT_KEYS = (
    "matched_count",
    "downloaded_count",
    "record_count",
    "source_count",
    "chunk_count",
    "citation_count",
    "hit_count",
    "atom_count",
    "chain_count",
    "residue_count",
    "ligand_count",
    "model_count",
    "genome_length",
    "feature_count",
    "gene_count",
    "cds_count",
    "orf_count",
    "bytes",
    "returncode",
)
RESULT_ID_KEYS = ("collection_name", "rid", "pdb_id", "file_format")
RESULT_PATH_KEYS = tuple(ARTIFACT_KIND_BY_KEY)
COMPACT_RESULT_KEYS = (
    "job_id",
    "plan_id",
    "logs",
    "bundle_path",
    "metrics",
    "tables",
    "needs_parameters",
    "required_parameters",
    "parameter_errors",
    "tool",
    "status",
    "summary",
    "needs_input",
    "pipeline_name",
    "presentation",
    "requested_inputs",
    "output_records",
    "config_overrides",
    "staged_config_paths",
    *RESULT_COUNT_KEYS,
    *RESULT_ID_KEYS,
    *RESULT_PATH_KEYS,
)


def artifact_kind(path: str, key: str = "") -> str | None:
    """Return the artifact kind for an output key/path pair."""
    if "://" in path:
        return None
    if key in ARTIFACT_KIND_BY_KEY:
        return ARTIFACT_KIND_BY_KEY[key]
    if key not in SUFFIX_ARTIFACT_KEYS:
        return None
    return ARTIFACT_KIND_BY_SUFFIX.get(Path(path).suffix.lower())


def collect_artifact_candidates(value: Any) -> list[dict[str, str]]:
    """Find output values that should be tracked as session files."""
    candidates: list[dict[str, str]] = []

    def visit(item: Any, key: str = "") -> None:
        if isinstance(item, dict):
            for subkey, subitem in item.items():
                visit(subitem, str(subkey))
            return
        if isinstance(item, list):
            for subitem in item:
                visit(subitem, key)
            return
        if not isinstance(item, str) or not item.strip():
            return
        kind = artifact_kind(item, key)
        if kind:
            candidates.append({"path": item, "kind": kind, "key": key})

    visit(value)
    return candidates


def collect_output_paths(value: Any) -> list[str]:
    """Collect path-like output values for evidence summaries."""
    paths: list[str] = []

    def append(path: str) -> None:
        if path and path not in paths:
            paths.append(path)

    def visit(item: Any, key: str = "") -> None:
        if isinstance(item, dict):
            for subkey, subitem in item.items():
                visit(subitem, str(subkey))
            return
        if isinstance(item, list):
            for subitem in item:
                visit(subitem, key)
            return
        if not isinstance(item, str):
            return
        if key.endswith("_path") or key.endswith("_paths") or key == "output_dir":
            append(item)

    visit(value)
    return paths


def artifact_content_type(path: str | Path) -> str:
    """Return the HTTP content type for a known artifact path."""
    suffix = Path(path).suffix.lower()
    return ARTIFACT_CONTENT_TYPES.get(suffix, "application/octet-stream")


def is_structure_artifact(path: str | Path) -> bool:
    return Path(path).suffix.lower() in STRUCTURE_ARTIFACT_SUFFIXES


def can_view_structure_artifact(path: str | Path) -> bool:
    return Path(path).suffix.lower() in STRUCTURE_VIEWER_SUFFIXES


def can_serve_artifact(path: str | Path) -> bool:
    return Path(path).suffix.lower() in SERVABLE_ARTIFACT_SUFFIXES


def artifact_suffix_config() -> dict[str, list[str]]:
    return {
        "servable_suffixes": list(SERVABLE_ARTIFACT_SUFFIXES),
        "structure_artifact_suffixes": list(STRUCTURE_ARTIFACT_SUFFIXES),
        "structure_suffixes": list(STRUCTURE_VIEWER_SUFFIXES),
        "image_suffixes": list(IMAGE_ARTIFACT_SUFFIXES),
    }


def allowed_artifact_suffix_message() -> str:
    return "viewable artifact suffixes: " + ", ".join(SERVABLE_ARTIFACT_SUFFIXES)
