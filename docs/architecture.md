# BioAgent architecture

BioAgent uses one OpenAI Agents SDK runtime. The SDK owns model turns, tool
calling, sessions, guardrails, and tracing. BioAgent supplies typed biological
function tools and deterministic implementations for scientific operations.

![BioAgent current system architecture](images/system_architecture.png)

## Runtime flow

```text
Web / CLI / API / notebook
        |
        v
harness.run_bioagent()
        |
        v
Agents SDK Agent + Runner
        |                    \
        |                     local SDK tracing and lifecycle hooks
        v
OpenAI Chat Completions client -> OpenRouter
        |
        v
Typed BioAgent function tools
        |
        +-- biological databases and literature
        +-- sequence, BLAST, genome, and structure analysis
        +-- file inspection and report writing
        +-- RAG and OpenRouter embeddings
        +-- approved pipeline execution and result collection
        |
        v
SDK guardrails -> structured result -> user interface
```

There is no second router, planner, model loop, or agent-facing tool system.
Deterministic code remains under `biology/` and is called by the thin tools because database retrieval, file access,
sequence calculations, and pipeline execution must be reproducible.

## Components

### Agents SDK harness

- `harness/agent.py` defines the single `BioAgent` and its instructions.
- `harness/runtime.py` creates the `Runner`, supplies run context, and returns
  the application result.
- `tools/__init__.py` exposes the explicit public workflow `FunctionTool`
  list defined by the modules under `tools/`.
- `harness/specialists.py` exposes focused sequence, retrieval, and pipeline
  agents through SDK `Agent.as_tool`; they run under the same root context.
- `harness/guardrails.py` contains input safety and output evidence checks.
- `harness/tracing.py` consumes SDK lifecycle hooks and spans locally without
  sending traces to OpenAI.
- `harness/sessions.py` stores application metadata; conversation history is
  stored by the SDK `SQLiteSession`.

### OpenRouter client

`models/openrouter_client.py` is the only provider client. It constructs the
OpenAI `OpenAI` and `AsyncOpenAI` clients with:

- `OPENROUTER_API_KEY` for authentication;
- `OPENROUTER_API_BASE`, defaulting to `https://openrouter.ai/api/v1`;
- optional `HTTP-Referer` and `X-OpenRouter-Title` headers;
- HTTPX2 clients with explicit proxy selection from `BIOAGENT_PROXY`, falling
  back to `ALL_PROXY`/`all_proxy`.

SDK model runs and embeddings use this OpenRouter transport. LiteLLM is not part
of the project dependencies.

### Function tools and workflows

Every agent-facing workflow in `tools/` is an OpenAI Agents SDK
`FunctionTool`. The SDK `@function_tool` decorator owns its name, description,
argument schema, validation, invocation, and failure handling. Deterministic
implementations live under `biology/` and are called directly by workflows;
they do not create another agent loop or require a second tool registry.

Function-tool design principles:

1. **One public abstraction.** Agents receive SDK `FunctionTool` objects. Do
   not add a second router, planner, or custom agent-facing tool class.
2. **One source of input truth.** Each workflow's typed Python signature and
   annotations generate its SDK schema and validation rules.
3. **Bounded handlers.** A tool handler performs one bounded biological
   operation. Deterministic handlers contain no model loop. Species-report
   opinion and synthesis requests are SDK reporting-agent runs as well.
4. **Explicit context and permissions.** Session, artifact, and progress data
   enter through the SDK run context. High-risk operations declare
   `needs_approval=True` on their SDK function tool.
5. **Stable result envelope.** Every SDK tool returns JSON with `status`,
   `data`, `artifacts`, `evidence`, and `error`. Workflow-specific values live
   inside `data`; callers never need tool-specific error parsing.
6. **Side effects are visible.** File writes, downloads, and pipeline runs
   declare their risk and approval requirements. Read-only tools should remain
   free of hidden mutation.
7. **Small, testable contracts.** Schemas, handlers, approvals, and result
   envelopes are tested independently with deterministic SDK model fixtures.

The workflow wrapper keeps the common envelope at the SDK boundary while
preserving raw action results inside `BioRunContext` for evidence collection
and artifact registration.

The SDK run context carries:

- the session identifier;
- run and artifact directories;
- user context and uploaded artifact references;
- model key;
- progress callback;
- per-run workflow results.

Deterministic implementations are called through explicit imports from each
workflow. The model can call only the public FunctionTools listed by
`tools.PUBLIC_TOOLS`.

### Sessions and artifacts

`SQLiteSession` persists user and assistant messages in
`runtime/agent_sessions.sqlite3` (configurable with `BIOAGENT_SESSION_DB`).
Application metadata is persisted in `runtime/session_metadata`.

Artifact files use the existing per-session layout:

```text
runtime/sessions/<session-id>/artifacts/uploads/
runtime/sessions/<session-id>/artifacts/<generated files>
runtime/runs/<run-id>/
```

The result contains references to files instead of copying large contents into
conversation history. The web interface continues to serve approved artifact
suffixes through its existing checks.

### Guardrails and verification

The input guardrail blocks requests asking for actionable harmful biological
procedures. The output guardrail records warnings when biological claims have no
executed evidence tool or when the answer is empty. The result verifier also
checks tool errors and evidence completeness. These checks run after SDK tool
execution and are included in the returned `verification` object.

High-risk pipeline behavior should remain explicit in tool input and output.
Pipeline execution pauses with an SDK `RunState` interruption and returns an
approval identifier. Call `interfaces.api.handle_approval` (or POST `/approve`)
to approve or reject it; approval resumes the saved state without replaying the
original model request.

### Tracing

The SDK creates traces and spans for agent, model, tool, handoff, and guardrail
operations. `LocalTraceProcessor` records redacted lifecycle metadata for the
current run. `BioAgentHooks` sends progress messages to CLI and streaming HTTP
callers. External trace export is disabled by default because OpenRouter is the
model endpoint and does not provide the OpenAI trace destination.

## Interfaces

All interfaces call the same runtime:

```python
from harness import run_bioagent

result = run_bioagent("Analyze this FASTA sequence", session_id="chat-1")
print(result["answer"])
```

The synchronous wrapper is used by CLI, HTTP, and ordinary Python callers. Use
`async_run_bioagent` in an application that already owns an asyncio event loop.

Uploads, session listing, artifact downloads, and deletion remain application
operations; they do not create a second agent runtime.

## Configuration

Create the environment and install the complete runtime:

```bash
conda activate openaisdk
python -m pip install -r requirements.txt
python -m pip check
```

Set the provider key before a live run:

```bash
export OPENROUTER_API_KEY="..."
```

For OpenRouter traffic, set `BIOAGENT_PROXY` in the terminal before starting
the server:

```bash
conda activate openaisdk
export BIOAGENT_PROXY=socks5h://127.0.0.1:10801
python -B -m interfaces.web --host 0.0.0.0 --port 8000
```

`BIOAGENT_PROXY` takes priority over `ALL_PROXY`/`all_proxy`; neither setting
requires clearing `HTTP_PROXY` or `HTTPS_PROXY` for these clients. Set
`BIOAGENT_DISABLE_PROXY=1` to force direct OpenRouter connections regardless
of proxy settings. Unset that variable before switching back to a proxy.
Database and pipeline clients retain their own proxy settings.

Choose a configured model with `BIOAGENT_AGENT_MODEL_KEY`. Set
`BIOAGENT_MAX_SKILL_STEPS` to bound the SDK run turns. Set
`BIOAGENT_SESSION_DB` and `BIOAGENT_RUNS_DIR` when the application needs
non-default storage locations.

## Testing

Offline harness tests use `agents.testing.ScriptedModel` and verify tool
selection, tool execution, guardrails, SDK spans, sessions, artifacts, and
pipeline results without an API key. Live tests should use a temporary
OpenRouter key and a model that supports Chat Completions and tool calls.

Offline migration checks and the approval-resumption regression suite pass in
the `openaisdk` environment. A controlled live OpenRouter run remains an
environment-dependent check and requires a separately supplied temporary key.
