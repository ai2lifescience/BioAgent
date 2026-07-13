"""PubMed query construction helpers."""

from __future__ import annotations

import re

from tools.literature.constants import STOPWORDS


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def species_aliases(species_name: str) -> list[str]:
    aliases = [species_name.strip()]
    compact = re.sub(r"[^a-z0-9]+", "", species_name.lower())
    if compact in {"phix174", "x174"}:
        aliases.extend(
            [
                "PhiX174",
                "phiX174",
                "phi X 174",
                "phiX 174",
                "bacteriophage phi X174",
                "Escherichia phage phiX174",
            ]
        )
    seen: set[str] = set()
    result = []
    for alias in aliases:
        key = alias.lower()
        if alias and key not in seen:
            seen.add(key)
            result.append(alias)
    return result


def significant_terms(text: str, max_terms: int = 8) -> list[str]:
    terms: list[str] = []
    for token in re.findall(r"[A-Za-z][A-Za-z0-9-]{2,}", text.lower()):
        if token in STOPWORDS or len(token) < 4:
            continue
        if token not in terms:
            terms.append(token)
        if len(terms) >= max_terms:
            break
    return terms


def pubmed_species_query(species_name: str) -> str:
    aliases = species_aliases(species_name)
    return "(" + " OR ".join(f'"{alias}"[Title/Abstract]' for alias in aliases) + ")"


def pubmed_query(species_name: str, question: str) -> tuple[str, str]:
    species_query = pubmed_species_query(species_name)
    terms = significant_terms(question)
    if not terms:
        return species_query, species_query
    topic_query = "(" + " OR ".join(f"{term}[Title/Abstract]" for term in terms) + ")"
    return f"{species_query} AND {topic_query}", species_query
