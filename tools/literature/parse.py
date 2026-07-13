"""PubMed XML parsing helpers."""

from __future__ import annotations

from typing import Any
import xml.etree.ElementTree as ET

from tools.literature.constants import PUBMED_BASE_URL
from tools.literature.query import normalize_text


def xml_text(element: ET.Element | None) -> str:
    if element is None:
        return ""
    return normalize_text(" ".join(element.itertext()))


def pubmed_year(article: ET.Element) -> str:
    for path in (
        ".//JournalIssue/PubDate/Year",
        ".//ArticleDate/Year",
        ".//PubMedPubDate/Year",
    ):
        value = article.findtext(path)
        if value:
            return value
    return ""


def parse_pubmed_article(article: ET.Element, species_name: str) -> dict[str, Any] | None:
    pmid = article.findtext(".//PMID")
    title = xml_text(article.find(".//ArticleTitle"))
    abstract_parts = [xml_text(node) for node in article.findall(".//AbstractText")]
    abstract = "\n".join(part for part in abstract_parts if part)
    if not pmid or not (title or abstract):
        return None

    journal = xml_text(article.find(".//Journal/Title"))
    year = pubmed_year(article)
    url = f"{PUBMED_BASE_URL}/{pmid}/"
    text_parts = [
        title,
        f"Journal: {journal}" if journal else "",
        f"Year: {year}" if year else "",
        abstract,
    ]
    return {
        "species": species_name,
        "source": "PubMed",
        "title": title or f"PubMed PMID {pmid}",
        "url": url,
        "verified": True,
        "text": "\n".join(part for part in text_parts if part),
        "metadata": {
            "source_type": "pubmed",
            "pmid": pmid,
            "journal": journal,
            "year": year,
        },
    }
