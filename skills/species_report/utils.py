"""Small helpers for the species report workflow."""

from __future__ import annotations

import re
from typing import Any


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def slugify(text: str, max_length: int = 48) -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", text.strip().lower()).strip("-._")
    return (slug or "species")[:max_length].strip("-._") or "species"


def collection_name_for(species_name: str, override: str | None = None) -> str:
    raw = override or f"species_kb_{slugify(species_name)}"
    name = re.sub(r"[^a-zA-Z0-9._-]+", "_", raw).strip("._-")
    name = re.sub(r"\.{2,}", ".", name)
    if len(name) < 3:
        name = f"kb_{name}"
    return name[:63].strip("._-") or "species_kb"


def build_research_question(
    species_name: str,
    question: str | None,
    concerns: list[str] | None,
) -> str:
    parts = [normalize_text(question or "")]
    if concerns:
        parts.append(
            "User concerns: " + ", ".join(normalize_text(c) for c in concerns if c)
        )
    detail = " ".join(part for part in parts if part).strip()
    if not detail:
        detail = (
            "Summarize trusted knowledge, taxonomy, genome structure, host range, "
            "replication, variants or mutations, applications, and uncertainty."
        )
    return f"For {species_name}, {detail}"


def build_source_query(question: str | None, concerns: list[str] | None) -> str:
    parts = [normalize_text(question or "")]
    if concerns:
        parts.extend(normalize_text(c) for c in concerns if c)
    query = " ".join(part for part in parts if part).strip()
    if not query:
        query = "genome structure host range replication variants applications"
    return query


def source_summary(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries = []
    for index, record in enumerate(records, start=1):
        meta = record.get("metadata", {})
        summaries.append(
            {
                "id": f"S{index}",
                "source": record["source"],
                "title": record["title"],
                "url": record["url"],
                "source_type": meta.get("source_type", ""),
                "pmid": meta.get("pmid", ""),
                "year": meta.get("year", ""),
            }
        )
    return summaries
