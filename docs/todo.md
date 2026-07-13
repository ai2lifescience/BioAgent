# BioAgent TODO

## Future Upgrade: Multi-Step Biological Plans

Current planner behavior:

```text
route -> standard execution skeleton
```

The planner currently creates simple plans such as:

```text
1. execute selected skill
2. collect evidence
3. verify
4. generate response
```

The current `Planner` is therefore a plan-template factory rather than a full
biological planner. It does not use `user_request` or `model_key` to decompose
complex goals, establish dependencies between steps, or pass outputs from one
step into later steps. The `Planner` name currently describes the intended
architecture more strongly than the implemented behavior.

This works for direct tasks like sequence analysis, file inspection, database
lookup, or a single species report. Complex comparison and literature-review
requests currently route to `llm_skill_loop` instead of a dedicated multi-step
research plan.

Target behavior:

```text
goal -> multi-step biological research plan
```

Example request:

```text
Compare PhiX174 and M13 genome structure, host range, and applications.
```

Desired plan:

```text
1. Run species_report for PhiX174.
2. Run species_report for M13.
3. Compare genome structure.
4. Compare host range.
5. Compare applications.
6. Verify citations and source coverage.
7. Synthesize final comparative answer.
```

## TODO List

- [ ] Upgrade `Planner` from fixed execution templates to bounded biological goal decomposition.
- [ ] Use `user_request` when identifying entities, research objectives, and required subtasks.
- [ ] Remove the unused `model_key` planner argument unless model-assisted planning is implemented.
- [ ] Represent dependencies and prior-step output references explicitly in `TaskStep`.
- [ ] Add a dedicated multi-step biological planning mode if the runtime needs it.
- [ ] Add planner support for multiple `TaskStep(kind="skill", ...)` entries.
- [x] Add entity extraction for species/organism names in comparative requests.
- [ ] Add a comparison/synthesis skill, for example `comparative_species_analysis`.
- [ ] Allow planner to create one `species_report` step per organism.
- [ ] Add a synthesis step that consumes prior skill results instead of calling external APIs again.
- [ ] Extend `SkillExecutor` or orchestrator to pass previous step outputs into later steps.
- [ ] Track per-step evidence so final comparison can cite the correct organism/source.
- [ ] Add verifier checks for comparative answers:
  - [ ] every compared organism has evidence
  - [ ] every major claim has citations or record IDs
  - [ ] missing evidence is stated clearly
- [ ] Add response formatting for side-by-side biological comparisons.
- [ ] Add smoke tests for multi-step plans in `evals/`.
- [ ] Add golden task:

```yaml
- prompt: "Compare PhiX174 and M13 genome structure, host range, and applications."
  expected_route: llm_skill_loop
  expected_steps:
    - model_guided_skill_calls
    - collect_evidence
    - verify
    - generate_response
```

## Design Notes

Keep the planner bounded. Do not let the LLM freely invent arbitrary tool calls.
A good upgrade path is:

```text
Rule-based route detects complex biological comparison
  -> planner creates structured multi-step plan when the mode is reintroduced
  -> executor runs registered skills only
  -> synthesis skill compares structured outputs
  -> verifier checks evidence and citations
```

Until then, complex comparison requests should stay in `llm_skill_loop`.

## Architecture Cleanup TODO

- [x] Stop documenting unused permission files as enforced runtime behavior.
- [x] Enforce skill tool allowlists through `ToolExecutor`.
- [x] Remove misleading config YAML files that were comments only.
- [x] Keep verification lightweight and document it as runtime checks.

## Session and State TODO

Current API/web behavior uses app-scoped components with explicit shared state:

```python
STATE_STORE = InMemoryStateStore()
TRACE_STORE = InMemoryTraceStore()
ARTIFACT_STORE = SessionArtifactStore(STATE_STORE)
ORCHESTRATOR = BioAgentOrchestrator(
    memory=STATE_STORE,
    trace_store=TRACE_STORE,
    artifact_store=ARTIFACT_STORE,
)
```

Browser and API requests can pass `session_id`, so chat history and trace events
are shared across turns while the Python process is alive.

- [x] Make the orchestrator app-scoped for the web/API runtime.
- [x] Add a session-aware API that accepts `session_id` for follow-up requests.
- [x] Store chat history and trace events per in-memory session.
- [x] Add per-session locking so concurrent requests for the same session run serially.
- [x] Reject active-session deletion by returning `deleted: false` while a run holds the session lock.
- [x] Add session-scoped artifact directories for files that should be reused across turns.
- [ ] Return a clearer active-session delete response, for example `409` or `{"reason": "running"}`.
- [ ] Decide whether session state should remain in memory or move to a persistent store.
- [ ] Add cleanup/expiry for old sessions to avoid unbounded memory growth.
- [x] Add per-run runtime directories for concurrent requests.

Implemented MVP runtime context:

```text
runtime/runs/{run_id}/
  chroma/

runtime/sessions/{session_id}/artifacts/
  downloads/
  uploads/
  pipelines/
  reports/
```

Each orchestrator run creates a `run_id` and passes `runtime_dir` through
`SkillContext`. The folder is created lazily by tools only when they need to
write files. Reusable user-visible files are stored under `artifact_dir` and
tracked in session metadata.

## Current Known Architecture Issues

- [ ] Compact skill outputs before sending them back into the LLM skill loop.
- [ ] Validate LLM skill-call arguments against each skill JSON schema before handler execution.
- [ ] Strengthen `ToolExecutor` schema validation beyond required-field checks.
- [ ] Decide whether unused `policies/*.yaml` should be removed or loaded by a real policy checker.
- [x] Document the web Stop button as UI-only: it aborts browser waiting, but does not kill backend LLM calls or subprocesses.

## Architecture Fix Targets

- [x] Separate skill-call naming from concrete tool-call naming.
- [x] Fix NCBI layer dependency inversion.
- [x] Remove upward dependency from LLM tools to skill packages.
- [x] Move new runtime artifacts out of the source tree.
- [x] Rebuild the RAG layer around retrieval, ranking, filters, citations, and vector storage.

Remaining architecture cleanup should prioritize the tool-boundary items first.
They affect safety and correctness more than package layout.
