"""Task planning primitives for BioAgent."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from models.config import DEFAULT_AGENT_MODEL_KEY

from .router import IntentRoute


@dataclass(frozen=True)
class TaskStep:
    """One executable plan step."""

    kind: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TaskPlan:
    """A compact plan that the orchestrator can execute."""

    mode: str
    steps: list[TaskStep]
    rationale: str


class Planner:
    """Build an execution plan from a routed intent."""

    def plan(
        self,
        user_request: str,
        route: IntentRoute,
        model_key: str = DEFAULT_AGENT_MODEL_KEY,
    ) -> TaskPlan:
        if route.mode == "control_response":
            return TaskPlan(
                mode="control_response",
                steps=[
                    TaskStep(
                        kind="respond",
                        name="control_response",
                        arguments=route.arguments,
                    ),
                ],
                rationale=route.reason,
            )

        if route.mode == "llm_response":
            return TaskPlan(
                mode="llm_response",
                steps=[
                    TaskStep(
                        kind="llm_response",
                        name="model_direct_answer",
                        arguments=route.arguments,
                    ),
                    TaskStep(kind="verification", name="verify"),
                    TaskStep(kind="respond", name="generate_response"),
                ],
                rationale=route.reason,
            )

        if route.mode == "direct_skill" and route.skill_name:
            return TaskPlan(
                mode="direct_skill",
                steps=[
                    TaskStep(
                        kind="skill",
                        name=route.skill_name,
                        arguments=route.arguments,
                    ),
                    TaskStep(kind="evidence", name="collect_evidence"),
                    TaskStep(kind="verification", name="verify"),
                    TaskStep(kind="respond", name="generate_response"),
                ],
                rationale=route.reason,
            )

        return TaskPlan(
            mode="llm_skill_loop",
            steps=[
                TaskStep(
                    kind="llm_skill_loop",
                    name="model_guided_skill_calls",
                    arguments=route.arguments,
                ),
                TaskStep(kind="evidence", name="collect_evidence"),
                TaskStep(kind="verification", name="verify"),
                TaskStep(kind="respond", name="generate_response"),
            ],
            rationale=(
                "No deterministic route matched; ask the model to choose from "
                "registered bioinformatics skills."
            ),
        )
