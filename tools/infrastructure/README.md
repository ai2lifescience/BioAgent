# Infrastructure

This package contains runtime implementation details shared by the agent, web
server, CLI, and pipeline workers. Model-facing tools remain under `tools/`.

- `sdk_adapters/` — SDK adapters such as the approval-aware `pipeline_shell`.
- `pipeline_engine/` — pipeline catalog, validation, job storage, workers, and
  engine adapters.
- `tool_support/` — generic guardrails, context, evidence, result envelopes, and
  bounded HTTP helpers used by function tools.
- `workspace/` — safe session paths and workspace artifact metadata.

Pipeline definitions and bundled example inputs live separately under
`tools/runtime_tools/pipelines/` because they are the runtime tool catalog.

The old `tools/common/`, `tools/workspace/`, and `tools/runtime_tools/` paths
were removed after their callers migrated. New code should import from
`tools/infrastructure/` directly.
