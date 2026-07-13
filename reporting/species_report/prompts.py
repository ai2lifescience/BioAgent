"""Prompt builders for species report generation."""

from __future__ import annotations

from typing import Any


def sources_block(sources: list[dict[str, Any]]) -> str:
    lines = []
    for source in sources:
        detail = source["source"]
        if source.get("pmid"):
            detail += f", PMID {source['pmid']}"
        if source.get("year"):
            detail += f", {source['year']}"
        lines.append(
            f"[{source['id']}] {source['title']} | {detail} | {source['url']}"
        )
    return "\n".join(lines)


def model_answers_block(
    model_answers: dict[str, str],
    model_labels: dict[str, str],
) -> str:
    return "\n\n".join(
        f"## {model_labels.get(key, key)} ({key})\n{answer}"
        for key, answer in model_answers.items()
    )


def build_model_opinion_messages(
    species_name: str,
    question: str,
    model_label: str,
) -> list[dict[str, str]]:
    prompt = f"""
Give a concise direct scientific opinion about this species or organism question.
Use cautious wording and say when information is uncertain.

Species or organism:
{species_name}

Question:
{question}
"""
    return [
        {
            "role": "system",
            "content": f"You are {model_label}, a species bioinformatics assistant.",
        },
        {"role": "user", "content": prompt},
    ]


def build_report_synthesis_messages(
    species_name: str,
    question: str,
    retrieval_context: str,
    model_answers: dict[str, str],
    sources: list[dict[str, Any]],
    model_labels: dict[str, str],
) -> list[dict[str, str]]:
    prompt = f"""
Create a Markdown report for this species or organism knowledge request.

Species or organism:
{species_name}

User question:
{question}

Retrieved trusted-source evidence:
{retrieval_context}

Direct LLM opinions:
{model_answers_block(model_answers, model_labels)}

Trusted sources:
{sources_block(sources)}

Rules:
- Return only the final Markdown report.
- Use these sections: Executive Summary, Evidence-Based Findings,
  Genome or Biology Notes, Public Health or Practical Relevance,
  Conflicts and Uncertainty, References.
- Ground the report in the retrieved trusted-source evidence first.
- Use direct LLM opinions only as secondary synthesis, not as primary evidence.
- Cite sources inline with [S1], [S2], etc. when making evidence-backed claims.
- If CDC, WHO, PubMed, or other authority sources did not provide enough
  evidence for a point, say that explicitly.
- Keep the report concise but complete.
"""
    return [
        {
            "role": "system",
            "content": "You synthesize species evidence into Markdown reports.",
        },
        {"role": "user", "content": prompt},
    ]

