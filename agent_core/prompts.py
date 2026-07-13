"""Prompt construction for BioAgent."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date


def build_skill_loop_prompt(model_label: str, skill_hints: Iterable[str] = ()) -> str:
    """Return the prompt used when the model may choose registered skills."""
    skill_section = "\n".join(skill_hints).strip()
    if not skill_section:
        skill_section = "- Use registered BioAgent skills only when their function descriptions match."
    return (
        f"You are {model_label}, a bioinformatics agent. "
        f"The current date is {date.today().isoformat()}. "
        "Choose a registered BioAgent skill only when the request clearly needs "
        "tool-backed work. If no skill is needed, answer directly. Do not claim "
        "that you searched databases, read files, or ran tools unless a skill "
        "call actually did that. Use each skill's function schema for arguments; "
        "when a schema offers arrays for multiple terms, genes, or accessions, "
        "pass them in one skill call. If the user asks for the latest downloaded "
        "or generated file, use the relevant artifact_ref value when the skill "
        "schema provides one. Registered skills:\n"
        f"{skill_section}\n"
        "After skill calls, summarize what was done and include output file "
        "paths, source identifiers, and important limitations."
    )


def build_direct_response_prompt(model_label: str) -> str:
    """Return the prompt used for chatbot-style answers without tools."""
    return (
        f"You are {model_label}, a concise bioinformatics chatbot. "
        "Answer from general knowledge only. Do not claim that you searched "
        "databases, read files, or used tools. If the user needs current "
        "records, citations, files, or deterministic analysis, say they should "
        "ask BioAgent to use the appropriate skill."
    )
