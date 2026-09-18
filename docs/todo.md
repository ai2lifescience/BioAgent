# BioAgent TODO

The follow-up list records deployment hardening and product improvements for
the current BioAgent runtime.

## Follow-up work

- Add handoffs only if a future workflow requires user-visible transfer between
  specialists; current specialists already run as SDK agent-as-tool calls.
- Add model-specific capability tests for tool calling, structured output, and
  embeddings across OpenRouter providers.
- Add redacted trace export to a selected observability backend when required.
- Add retention and cleanup policies for old SQLite sessions and workspaces.
- Expand live evaluation coverage with a temporary OpenRouter key.

## Current guarantees

- `harness.run_bioagent` is the single application entry point.
- Model resolution uses a run-scoped SDK `ModelProvider`; the harness closes
  its client on completion, failure, or approval pause.
- Biological workflows are SDK function tools; pipelines use the local
  `pipeline_shell` ShellTool.
- Conversations use SDK `SQLiteSession`.
- Session workspaces use the SDK Unix-local sandbox; file operations use
  workspace-relative paths through the workspace API.
- Input safety and output evidence checks use SDK guardrails.
- SDK lifecycle events and spans are captured by local tracing hooks.
- Deterministic biological implementations remain behind the tools.
- Pipeline execution pauses for SDK approval and can resume or reject through
  the API and HTTP `/approve` endpoint.
