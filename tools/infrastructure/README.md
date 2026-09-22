# Infrastructure

This package contains runtime implementation details shared by the agent, web
server, CLI, and pipeline workers. Model-facing tools remain under `tools/`.

- `sdk_adapters/` — SDK adapters such as the approval-aware `pipeline_shell`.
- `pipeline_engine/` — pipeline catalog, validation, job storage, workers, and
  engine adapters.
- `tool_support/` — generic guardrails, context, evidence artifact contracts,
  result envelopes, and bounded HTTP helpers used by function tools and report
  agents.
- `workspace/` — safe session paths, PDF extraction, and workspace artifact metadata.
- `knowledge/` — durable session-owned web collections. `service.py` is the
  application boundary; `repository.py` owns SQLite persistence, `jobs.py`
  owns queueing and detached workers, `indexer.py` owns chunking and hybrid
  retrieval, and `crawlers/` owns the crawler protocol plus HTTP and optional
  Scrapy adapters. Public callers use only the `knowledge_*` FunctionTools.
- `providers/` — external database clients and protocol parsers, never SDK tool registration.

Durable agent-run queueing is application runtime infrastructure in
`harness/jobs.py` (queue, worker process, status, and SSE event history); it is
not a model-facing tool category. Pipeline jobs are the separate
`pipeline_engine/` concern behind the `pipeline_shell` adapter. The Agents SDK
still owns each model run and its native tool loop; the queue only makes that
run restartable and observable for HTTP/CLI callers.

The local knowledge repository defaults to `runtime/knowledge.sqlite3` and can
be changed with `AGENT_KNOWLEDGE_DB`; `AGENT_KNOWLEDGE_WORKERS` bounds detached
crawler workers. `AGENT_KNOWLEDGE_CRAWLER=auto` uses Scrapy when the optional
dependency is installed and otherwise uses the bounded HTTP crawler;
`http` and `scrapy` force a backend. Install `requirements-scrapy.txt` to add
Scrapy. A production deployment can replace the repository with a
Postgres/pgvector adapter while retaining the same public tool contracts.

Pipeline definitions and bundled example inputs live separately under
`tools/runtime_tools/pipelines/` because they are the runtime tool catalog.

The old `tools/common/` and `tools/workspace/` implementation paths were
removed after their callers migrated. `tools/runtime_tools/pipelines/` remains
the separate runtime pipeline catalog. New shared infrastructure code should
import from `tools/infrastructure/` directly.
