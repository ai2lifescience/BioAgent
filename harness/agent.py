"""The single BioAgent Agents SDK definition."""

from __future__ import annotations

from agents import Agent, Model, OpenAIChatCompletionsModel

from models.config import get_default_model_id
from models.openrouter_client import create_async_client

from .guardrails import INPUT_GUARDRAIL, OUTPUT_GUARDRAIL
from .tools import build_tools


INSTRUCTIONS = """You are BioAgent, a careful bioinformatics assistant.

Use the registered biological tools for sequence analysis, database retrieval,
structure work, file inspection, reports, RAG, and pipelines. Do not invent
database results, citations, measurements, or files. Explain tool errors and
state limitations. For potentially harmful biological requests, refuse
actionable procedures and offer safe, high-level information instead.
Return a concise answer with relevant evidence and artifact paths. Use the
existing session context when the user refers to a previous upload or result.
"""


def create_agent(model_key: str, model: Model | None = None) -> Agent:
    model = model or OpenAIChatCompletionsModel(
        model=get_default_model_id(model_key), openai_client=create_async_client()
    )
    return Agent(
        name="BioAgent",
        instructions=INSTRUCTIONS,
        model=model,
        tools=build_tools(),
        input_guardrails=[INPUT_GUARDRAIL],
        output_guardrails=[OUTPUT_GUARDRAIL],
    )
