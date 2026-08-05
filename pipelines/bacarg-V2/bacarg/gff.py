"""Prokka GFF overlap context for contig-level hits."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import unquote

from .errors import ParseError


def _attributes(value: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for part in value.split(";"):
        if "=" in part:
            key, item = part.split("=", 1)
            result[key] = unquote(item)
    return result


def load_cds(path: Path) -> dict[str, list[dict[str, Any]]]:
    """Load Prokka CDS intervals grouped by contig."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if line.startswith("##FASTA"):
                    break
                if not line.strip() or line.startswith("#"):
                    continue
                fields = line.rstrip("\n").split("\t")
                if len(fields) != 9:
                    raise ParseError(f"Malformed GFF line {line_number}: {path}")
                if fields[2] != "CDS":
                    continue
                attrs = _attributes(fields[8])
                grouped.setdefault(fields[0], []).append(
                    {
                        "start": int(fields[3]),
                        "end": int(fields[4]),
                        "locus_tag": attrs.get("locus_tag", attrs.get("ID", "")),
                        "gene": attrs.get("gene", ""),
                        "product": attrs.get("product", ""),
                    }
                )
    except OSError as exc:
        raise ParseError(f"Cannot read Prokka GFF: {path}") from exc
    for values in grouped.values():
        values.sort(key=lambda item: (item["start"], item["end"], item["locus_tag"]))
    return grouped


def add_context(
    hits: Iterable[Mapping[str, Any]], cds: Mapping[str, list[Mapping[str, Any]]]
) -> list[dict[str, Any]]:
    """Add the maximum-overlap Prokka locus context to each hit."""
    result: list[dict[str, Any]] = []
    for source in hits:
        row = dict(source)
        candidates: list[tuple[int, Mapping[str, Any]]] = []
        for feature in cds.get(str(row["contig"]), []):
            overlap = min(int(row["end"]), int(feature["end"])) - max(
                int(row["start"]), int(feature["start"])
            ) + 1
            if overlap > 0:
                candidates.append((overlap, feature))
        if candidates:
            _, best = max(
                candidates,
                key=lambda item: (
                    item[0], -int(item[1]["start"]), str(item[1]["locus_tag"])
                ),
            )
            row["locus_tag"] = best.get("locus_tag", "")
            row["prokka_gene"] = best.get("gene", "")
            row["prokka_product"] = best.get("product", "")
        result.append(row)
    return result
