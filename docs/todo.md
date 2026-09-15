# BioAgent TODO

The core Agents SDK migration on `dev/harness` is complete for the root
BioAgent runtime, public biological tools, sessions, guardrails, and tracing.
The follow-up list records the reporting-agent conversion and deployment
hardening still required before calling every model call and filesystem path
fully SDK-native and production-hardened.

## Follow-up work

- Add handoffs only if a future workflow requires user-visible transfer between
  specialists; current specialists already run as SDK agent-as-tool calls.
- Add a persistent artifact metadata database if multiple web workers need to
  share metadata across processes.
- Add model-specific capability tests for tool calling, structured output, and
  embeddings across OpenRouter providers.
- Add redacted trace export to a selected observability backend when required.
- Add retention and cleanup policies for old SQLite sessions and workspaces.
- Expand live evaluation coverage with a temporary OpenRouter key.

## Current guarantees

- `harness.run_bioagent` is the single application entry point.
- BioAgent workflows are Agents SDK function tools.
- Conversations use SDK `SQLiteSession`.
- Input safety and output evidence checks use SDK guardrails.
- SDK lifecycle events and spans are captured by local tracing hooks.
- Deterministic biological implementations remain behind the tools.
- LiteLLM is not a project dependency.
- Pipeline execution pauses for SDK approval and can resume or reject through
  the API and HTTP `/approve` endpoint.
