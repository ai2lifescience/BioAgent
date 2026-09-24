"""Small metadata helpers for files in the SDK sandbox workspace.

The OpenAI Agents SDK sandbox owns files and their lifecycle. This module does
not register, copy, or persist artifacts; it only derives browser metadata from
file paths.
"""

from __future__ import annotations

import mimetypes
from pathlib import Path


_TEXT_SUFFIXES = frozenset(
    {
        ".bed",
        ".dbn",
        ".fa",
        ".faa",
        ".fasta",
        ".ffn",
        ".fna",
        ".fq",
        ".fastq",
        ".gb",
        ".gbk",
        ".gff",
        ".gff3",
        ".log",
        ".md",
        ".markdown",
        ".newick",
        ".nwk",
        ".sam",
        ".sizes",
        ".tre",
        ".tree",
        ".txt",
        ".vcf",
    }
)
_STRUCTURE_SUFFIXES = frozenset({".bcif", ".cif", ".mmcif", ".pdb"})
_STRUCTURE_VIEWER_SUFFIXES = frozenset({".cif", ".mmcif", ".pdb"})
_IMAGE_SUFFIXES = frozenset({".gif", ".jpeg", ".jpg", ".png", ".svg", ".webp"})
_SEQUENCE_SUFFIXES = frozenset({".dbn", ".fa", ".faa", ".fasta", ".ffn", ".fna", ".fq", ".fastq"})
_ANNOTATION_SUFFIXES = frozenset({".bed", ".gb", ".gbk", ".gff", ".gff3", ".sam", ".vcf"})
_TREE_SUFFIXES = frozenset({".newick", ".nwk", ".tre", ".tree"})
_COMPRESSED_SUFFIXES = frozenset({".bgz", ".gz", ".zip"})
_TABLE_SUFFIXES = frozenset({".csv", ".tsv"})
_CONFIG_SUFFIXES = frozenset({".json", ".yaml", ".yml"})
_DOCUMENT_SUFFIXES = frozenset({".html", ".pdf"})

# Standard mimetypes do not cover several biological formats and omit the
# charset used by the browser response contract, so only those cases are
# explicit. Common image and archive types continue to use mimetypes.guess_type.
_CONTENT_TYPE_OVERRIDES = {
    **{suffix: "text/plain; charset=utf-8" for suffix in _TEXT_SUFFIXES},
    ".bcif": "application/octet-stream",
    ".cif": "chemical/x-mmcif; charset=utf-8",
    ".mmcif": "chemical/x-mmcif; charset=utf-8",
    ".pdb": "chemical/x-pdb; charset=utf-8",
    ".csv": "text/csv; charset=utf-8",
    ".tsv": "text/tab-separated-values; charset=utf-8",
    ".gz": "application/gzip",
    ".bgz": "application/gzip",
    ".md": "text/markdown; charset=utf-8",
    ".markdown": "text/markdown; charset=utf-8",
    ".yaml": "text/yaml; charset=utf-8",
    ".yml": "text/yaml; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".pdf": "application/pdf",
    ".svg": "image/svg+xml; charset=utf-8",
}

# Output keys are hints from tool result envelopes. The file itself remains the
# source of truth when a generic workspace path is listed.
_KEY_PREFIX_KINDS = (
    ("fasta", "fasta"),
    ("structure", "structure"),
    ("metadata", "metadata"),
    ("report", "report"),
    ("image", "image"),
    ("genome_map", "genome_map"),
    ("session_input", "input"),
    ("upload", "upload"),
    ("runner_config", "config"),
    ("raw_config", "config"),
    ("config", "config"),
    ("metrics", "metrics"),
    ("bakta", "metadata"),
    ("inference", "metadata"),
    ("hypotheticals", "metadata"),
    ("plot", "image"),
    ("output_dir", "directory"),
)


def _suffix(path: str | Path) -> str:
    return Path(path).suffix.lower()


def artifact_content_type(path: str | Path) -> str:
    """Return the content type used when serving a workspace file."""

    suffix = _suffix(path)
    if suffix in _CONTENT_TYPE_OVERRIDES:
        return _CONTENT_TYPE_OVERRIDES[suffix]
    guessed, _encoding = mimetypes.guess_type(str(path), strict=False)
    return guessed or "application/octet-stream"


def artifact_kind(path: str | Path, key: str = "", *, uploaded: bool = False) -> str:
    """Return a compact display category for a workspace file."""

    if uploaded:
        return "upload"
    for prefix, kind in _KEY_PREFIX_KINDS:
        if key.startswith(prefix):
            return kind
    name = Path(path).name.lower()
    if name == "genome_map.json":
        return "genome_map"
    suffix = _suffix(path)
    if suffix in _STRUCTURE_SUFFIXES:
        return "structure"
    if suffix in _IMAGE_SUFFIXES:
        return "image"
    if suffix in _SEQUENCE_SUFFIXES:
        return "sequence"
    if suffix in _ANNOTATION_SUFFIXES:
        return "annotation"
    if suffix in _TREE_SUFFIXES:
        return "phylogenetic_tree"
    if suffix in _TABLE_SUFFIXES:
        return "metadata"
    if suffix in _CONFIG_SUFFIXES:
        return "config"
    if suffix in _DOCUMENT_SUFFIXES:
        return "document" if suffix == ".pdf" else "report"
    if suffix in _COMPRESSED_SUFFIXES:
        return "compressed"
    if suffix in _TEXT_SUFFIXES:
        return "text"
    return "file"


def can_view_structure_artifact(path: str | Path) -> bool:
    return _suffix(path) in _STRUCTURE_VIEWER_SUFFIXES


def can_serve_artifact(path: str | Path) -> bool:
    """Return whether the browser knows how to serve this file format."""

    suffix = _suffix(path)
    known = set(_CONTENT_TYPE_OVERRIDES) | {".png", ".gif", ".jpeg", ".jpg", ".webp", ".zip"}
    return suffix in known


def artifact_suffix_config() -> dict[str, list[str]]:
    """Return the format contract consumed by the browser UI."""

    servable = set(_CONTENT_TYPE_OVERRIDES) | {".png", ".gif", ".jpeg", ".jpg", ".webp", ".zip"}
    return {
        "servable_suffixes": sorted(servable),
        "structure_artifact_suffixes": sorted(_STRUCTURE_SUFFIXES),
        "structure_suffixes": sorted(_STRUCTURE_VIEWER_SUFFIXES),
        "image_suffixes": sorted(_IMAGE_SUFFIXES),
    }


def workspace_file_metadata(path: str | Path, *, uploaded: bool = False) -> dict[str, str]:
    """Build the metadata returned with an SDK sandbox file listing."""

    return {
        "kind": artifact_kind(path, uploaded=uploaded),
        "content_type": artifact_content_type(path),
    }


__all__ = [
    "artifact_content_type",
    "artifact_kind",
    "artifact_suffix_config",
    "can_serve_artifact",
    "can_view_structure_artifact",
    "workspace_file_metadata",
]
