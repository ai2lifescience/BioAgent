# SDK migration completion audit

Checked on `dev/harness` after the SDK-native refactor. The worktree is still
uncommitted; this document records what was verified rather than implying a
remote merge or a live provider test.

| Area | Status | Evidence |
| --- | --- | --- |
| Root orchestration | Complete | `harness/runtime.py` uses one `Runner` and `RunConfig`. |
| Public biological tools | Complete | `tools/function_tools/` exports 12 typed SDK `FunctionTool` objects in `FUNCTION_TOOLS`. |
| Scientific implementation layer | Complete | Workflows and deterministic implementations are co-located under each `tools/function_tools/<tool_name>/` package; deleted registry/action-dispatch modules are no longer imported. |
| Specialists | Complete | `Agent.as_tool()` is used for sequence, retrieval, and pipeline specialists. They share application context and tracing; SDK SQLite history is not implicitly copied into nested calls. |
| Guardrails | Complete | Agent input/output guardrails and common SDK tool input/output envelope guardrails are registered. |
| Sessions and sandbox files | Complete | `SQLiteSession` stores conversation items; the SDK Unix-local sandbox owns each session workspace and the API exposes workspace-relative files. |
| Tracing | Complete | SDK lifecycle hooks and local SDK spans are captured by `harness/tracing.py`. |
| Pipeline approval | Complete | `needs_approval=True`, saved SDK `RunState`, CLI/API/HTTP approval and rejection, stale-ID checks, and restart reconstruction are covered by `evals/smoke_approvals.py`. |
| Tool execution limits | Complete | Function tools have SDK timeouts; `RunConfig` caps concurrent function calls at four. Underlying subprocess timeouts remain authoritative. |
| Direct reporting model calls | Complete | `models/text_generation.py` now runs reporting requests through SDK `Agent`/`Runner`; OpenRouter remains only the SDK model transport. |
| File-path sandboxing | Development backend enabled | `harness/sandbox.py` configures the SDK Unix-local backend and filesystem capability. It shares the host OS, so use a container-backed SDK sandbox for untrusted multi-tenant deployment. |
| Live OpenRouter validation | Not run | No key is configured in this environment. Run `evals/smoke_openrouter.py` only with a separately supplied temporary key. |

Offline checks run successfully in `openaisdk`: architecture, approval,
pipeline-results, generic-bio, database-extension, Nextflow, and session-artifact
smokes, plus compileall and `pip check`. The bacterial and RNA
secondary-structure smoke checks skip because those optional pipeline folders
are absent from this checkout; the OpenRouter smoke is intentionally excluded
because it requires a live key.
