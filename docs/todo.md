# BioAgent TODO

The Agents SDK migration on `dev/harness` is complete. The SDK owns the agent
loop, function-tool dispatch, sessions, guardrails, and tracing. The remaining
work is incremental product improvement rather than a second orchestration
architecture.

## Follow-up work

- Add explicit interactive approval and RunState resumption for high-risk
  pipeline operations.
- Add specialist agents and handoffs only for workflows where one agent is
  insufficient.
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
