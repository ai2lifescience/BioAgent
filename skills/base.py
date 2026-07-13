"""Common skill workflow definition objects."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class SkillDefinition:
    """Registered high-level skill workflow metadata."""

    skill_spec: dict[str, Any]
    handler: Callable[..., dict[str, Any]]
    category: str = "general"
    tools: tuple[str, ...] = ()
    instruction_path: str | None = None

    @property
    def name(self) -> str:
        return str(self.skill_spec["function"]["name"])
