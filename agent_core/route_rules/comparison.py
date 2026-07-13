"""Biological comparison route rules."""

from __future__ import annotations

import re

from agent_core.router import IntentRoute


COMPARISON_FOCUS_PHRASES = (
    "genome structure",
    "host range",
    "applications",
    "application",
    "replication biology",
    "replication",
    "biology",
    "taxonomy",
    "evolution",
    "pathogenicity",
    "virulence",
    "diagnostics",
    "therapy",
    "treatment",
    "delivery methods",
    "risks",
    "safety",
)
COMPARISON_ENTITY_STOP_WORDS = (
    "genome",
    "host",
    "application",
    "applications",
    "biology",
    "structure",
    "range",
    "replication",
    "taxonomy",
    "evolution",
    "pathogenicity",
    "virulence",
    "diagnostics",
    "therapy",
    "treatment",
    "delivery",
    "risks",
    "risk",
    "safety",
    "using",
    "from",
    "based",
)


def route_comparison_research(user_request: str) -> IntentRoute | None:
    if not re.search(
        r"\b(compare|contrast|versus|vs\.?|differences?|similarities?|different|differ|differentiate)\b",
        user_request,
        re.IGNORECASE,
    ):
        return None

    entities = extract_compared_entities(user_request)
    if len(entities) < 2:
        return None

    return IntentRoute(
        mode="llm_skill_loop",
        arguments={
            "task_type": "comparison",
            "question": user_request,
            "entities": entities[:4],
            "focus": extract_comparison_focus(user_request),
        },
        reason="Matched a biological comparison request for model-guided skill selection.",
    )


def extract_compared_entities(text: str) -> list[str]:
    stop = "|".join(re.escape(word) for word in COMPARISON_ENTITY_STOP_WORDS)
    patterns = [
        rf"\b(?:compare|contrast|differentiate)\s+(.+?)(?=\s+(?:{stop})\b|[?.!]|$)",
        rf"\b(?:differences?|similarities?)\s+(?:between|among)\s+(.+?)(?=\s+(?:{stop})\b|[?.!]|$)",
        r"\bhow\s+(?:are|do|does)\s+(.+?)\s+(?:differ|different|compare)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            entities = split_entity_list(match.group(1))
            if len(entities) >= 2:
                return entities

    versus_match = re.search(
        rf"(.+?)\s+(?:vs\.?|versus)\s+(.+?)(?=\s+(?:{stop})\b|[?.!]|$)",
        text,
        re.IGNORECASE,
    )
    if not versus_match:
        return []
    entities = [
        clean_bio_entity_candidate(versus_match.group(1)),
        clean_bio_entity_candidate(versus_match.group(2)),
    ]
    return [entity for entity in entities if entity]


def split_entity_list(segment: str) -> list[str]:
    parts = re.split(r"\s+(?:and|with|versus|vs\.?)\s+|,\s*", segment, flags=re.IGNORECASE)
    entities: list[str] = []
    for part in parts:
        entity = clean_bio_entity_candidate(part)
        if entity and entity not in entities:
            entities.append(entity)
    return entities


def clean_bio_entity_candidate(value: str | None) -> str | None:
    if not value:
        return None
    candidate = value.strip(" .,:;()[]")
    candidate = re.sub(r"^(?:a|an|the)\s+", "", candidate, flags=re.IGNORECASE)
    candidate = re.sub(
        r"^(?:compare|contrast|differentiate|between|among|how are|how do|how does)\s+",
        "",
        candidate,
        flags=re.IGNORECASE,
    )
    focus = "|".join(re.escape(phrase) for phrase in COMPARISON_FOCUS_PHRASES)
    candidate = re.split(rf"\b(?:{focus})\b", candidate, maxsplit=1, flags=re.IGNORECASE)[0]
    candidate = candidate.strip(" .,:;()[]")
    if not candidate:
        return None
    if candidate.lower() in {"and", "or", "biology", "organisms", "species", "viruses", "genes"}:
        return None
    if re.fullmatch(r"phi\s*x\s*174|phix174", candidate, flags=re.IGNORECASE):
        return "PhiX174"
    return candidate


def extract_comparison_focus(text: str) -> list[str]:
    focus: list[str] = []
    for phrase in COMPARISON_FOCUS_PHRASES:
        if re.search(rf"\b{re.escape(phrase)}\b", text, re.IGNORECASE):
            normalized = "applications" if phrase == "application" else phrase
            if normalized not in focus:
                focus.append(normalized)
    return focus
