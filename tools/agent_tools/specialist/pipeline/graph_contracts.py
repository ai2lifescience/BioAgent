"""Structured proposals returned by the autograph planning specialist."""
from typing import Literal

from pydantic import Field, model_validator

from tools.infrastructure.pipeline_engine.dependency_graph import MAX_STEPS, STEP_NAME
from tools.infrastructure.tool_support.results import FunctionContract


class WorkspaceSource(FunctionContract):
    path: str = Field(min_length=1)


class OutputSource(FunctionContract):
    step: str = Field(pattern=STEP_NAME.pattern)
    output: str = Field(min_length=1)


class InputBinding(FunctionContract):
    slot: str = Field(min_length=1)
    sources: list[WorkspaceSource | OutputSource] = Field(min_length=1)
    reason: str = Field(min_length=1, max_length=2000)


Scalar = str | int | float | bool | None


class Parameter(FunctionContract):
    name: str = Field(min_length=1)
    value: Scalar | list[Scalar]


class PipelineStep(FunctionContract):
    id: str = Field(pattern=STEP_NAME.pattern)
    pipeline: str = Field(min_length=1)
    inputs: list[InputBinding]
    params: list[Parameter] = Field(default_factory=list)
    cores: int = Field(default=1, ge=1, le=64)
    timeout: int | None = Field(default=None, ge=1, le=86400)
    depends_on: list[str] = Field(default_factory=list)
    reason: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def unique_slots_and_parameters(self):
        if len({item.slot for item in self.inputs}) != len(self.inputs):
            raise ValueError("Use each input slot once per step.")
        if len({item.name for item in self.params}) != len(self.params):
            raise ValueError("Use each parameter once per step.")
        return self

    def command_step(self):
        """Convert the strict output schema to the existing workflow protocol."""
        inputs = {}
        for binding in self.inputs:
            values = [source.path if isinstance(source, WorkspaceSource) else source.model_dump()
                      for source in binding.sources]
            inputs[binding.slot] = values[0] if len(values) == 1 else values
        step = {"id": self.id, "pipeline": self.pipeline, "inputs": inputs,
                "params": {item.name: item.value for item in self.params}, "cores": self.cores,
                "depends_on": self.depends_on, "reason": self.reason,
                "input_reasons": {item.slot: item.reason for item in self.inputs}}
        if self.timeout is not None:
            step["timeout"] = self.timeout
        return step


class GraphProposal(FunctionContract):
    status: Literal["ready", "needs_input"]
    summary: str = Field(min_length=1, max_length=12000)
    steps: list[PipelineStep] = Field(max_length=MAX_STEPS)
    missing_requirements: list[str]
    assumptions: list[str]

    @model_validator(mode="after")
    def proposal_state(self):
        if self.status == "ready" and (not self.steps or self.missing_requirements):
            raise ValueError("A ready proposal requires steps and resolved requirements.")
        if self.status == "needs_input" and not self.missing_requirements:
            raise ValueError("Identify the information or inputs needed to finish the plan.")
        return self
