"""Typed boundaries for model-backed specialist tools."""
from __future__ import annotations

from typing import Annotated

from pydantic import Field

from tools.infrastructure.tool_support.results import FunctionContract


class SpecialistInput(FunctionContract):
    """Bounded natural-language task delegated by the root agent."""

    task: Annotated[
        str,
        Field(
            min_length=1,
            max_length=12_000,
            description="Complete delegated goal with known workspace paths, constraints, and requested output.",
        ),
    ]


class SpecialistResult(FunctionContract):
    """Stable summary returned by an agent-as-tool specialist."""

    summary: Annotated[str, Field(min_length=1, max_length=100_000)]
    workspace_paths: list[str] = Field(default_factory=list)


__all__ = ["SpecialistInput", "SpecialistResult"]
