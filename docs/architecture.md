# Pipeline2Agent architecture

This document describes the architecture implemented in this repository. It is the
design reference for the server, the OpenAI Agents SDK integration, public tools,
durable work, knowledge ingestion, pipeline execution, and trusted website
embedding.

The system has four principles:

1. The OpenAI Agents SDK owns agent orchestration, tool calls, streaming events,
   approvals, sessions, and nested agents.
2. Public tools are small, typed SDK FunctionTools. Complex work is composed by
   the agent or by an Agent-as-tool specialist.
3. Long work is durable and observable. A run can continue after the HTTP request
   ends and can be inspected through status or event polling.
4. Host implementation details stay private. Models, browsers, and external
   websites receive workspace-relative paths and structured public results.

## System map

![Pipeline2Agent system architecture](images/system_architecture.png)

*Figure 1. Pipeline2Agent system architecture. Client interfaces feed durable
execution into the shared OpenAI Agents SDK runtime, which composes typed tools,
specialist agents, and pipeline execution services into evidence-bound outputs.*

The figure shows the request paths, SDK tool surface, durable services, and
website data flow. Arrows indicate calls or data flow; <-> indicates a request
and response exchange.

```text
  Web UI / embedded assistant                    CLI / notebook / Python API
              | HTTP                                        | direct calls
              v                                             |
  +-----------------------------------------+               |
  | interfaces/web.py -> interfaces/api.py  |               |
  | /run, /run_stream, /approve_stream      |               |
  +-------------------+---------------------+               |
                      |                                     |
                      v                                     |
  +-----------------------------------------+               |
  | AGENT JOBS: harness/jobs.py             |               |
  | SQLite RunQueue -> detached workers     |               |
  | Run status + sequenced persisted events |               |
  +-------------------+---------------------+               |
                      |                                     |
                      +------------------+------------------+
                                         |
                                         v
  +-----------------------------------------------------------------------------+
  | SHARED SDK RUNTIME: harness/runtime.py                                      |
  | AgentRunContext + RunConfig + SQLiteSession + local SDK sandbox             |
  | Runner.run / Runner.run_streamed -> Pipeline2Agent (SandboxAgent)           |
  | Guardrails, tool execution, nested agents, approval RunState, local traces  |
  |                                                                             |
  | ModelProvider -> models/openrouter_provider.py -> OpenRouter model API      |
  |                  models/local_tools_model.py adapts tool-call transport     |
  +--------------------------------------+--------------------------------------+
                                         |
                                         v
  TOOL SURFACE: tools/registry.py + SDK filesystem capabilities
    |
    +-- FunctionTools: tools/function_tools/
    |     |
    |     +-- biology / data_analysis / sources / workspace / coding
    |     |     -> deterministic operations, provider clients, workspace files
    |     |
    |     +-- knowledge
    |     |     -> KnowledgeService -> repository / indexer
    |     |     -> ingestion queue -> worker -> HTTP or Scrapy crawler
    |     |     -> chunks + embeddings -> knowledge.sqlite3 -> cited retrieval
    |     |
    |     +-- website
    |           -> harness/website.py -> authenticated host-page bridge [A]
    |
    +-- Agent.as_tool: tools/agent_tools/
    |     |
    |     +-- specialists: research, pipeline, document, data_analysis,
    |     |                coding, website_guide
    |     |     -> nested SDK Agent -> selected function/runtime tools
    |     |
    |     +-- reporting: report_review / report_synthesize
    |           -> evidence-bound SDK Agent -> structured review/report draft
    |           -> root or research agent can call report_write to save a file
    |
    +-- ShellTool: pipeline_shell
    |     -> allowlisted agent-pipeline commands
    |     -> pipeline_engine: catalog -> plan -> approval -> detached job
    |     -> shell / Snakemake / Nextflow / WDL -> verified results
    |     -> definitions: tools/runtime_tools/pipelines/
    |
    +-- SDK Filesystem -> session workspace

  +-----------------------------------------------------------------------------+
  | PRIVATE PERSISTENCE (default locations; host paths stay internal)           |
  | runtime/agent_runs.sqlite3       Agent queue, results, and event log        |
  | runtime/agent_sessions.sqlite3   SDK conversation history                   |
  | runtime/session_metadata/       Session metadata + paused approval state    |
  | runtime/knowledge.sqlite3        Collections, chunks, vectors, ingest jobs  |
  | runtime/website_bridge.sqlite3   Website bindings and correlated calls      |
  | runtime/sessions/<session-id>/   uploads/ inputs/ outputs/ runs/            |
  |                                 .pipeline/jobs.sqlite3 (pipeline jobs)      |
  +-----------------------------------------------------------------------------+

  EVENT AND RESULT DELIVERY
    SDK events -> harness/streaming.py -> worker -> persisted agent-run events
    Run status / events / results -> HTTP JSON or SSE -> browser
    Tool and API serialization -> public workspace-relative paths

  [A] TRUSTED WEBSITE DATA AND ACTIONS
    Website tools <-> harness/website.py <-> assistant iframe <-> trusted host
    Server <-> iframe: HTTP polling; iframe <-> host: checked postMessage
    Host adapter: page context, tables, figures, manual, exports, UI actions
    Explicit website_import_data -> inputs/ -> normal analysis tools
```

Agent runs, knowledge ingestion, and pipeline execution have separate job
lifecycles. Specialists execute inside an SDK run and can start or inspect
those jobs through their tools. The website bridge supplies host data and
actions while the embedded assistant retains the full root agent tool set.

The web server, queue, worker, and provider adapters are application
infrastructure. They are not model-facing tools. The model sees the tools
registered by tools/registry.py and the SDK filesystem capabilities.

Other callers use the same runtime boundary. interfaces/api.py provides a
programmatic API and durable enqueue helpers, interfaces/cli.py provides a
command-line session client, and interfaces/notebook.py provides synchronous
and asynchronous notebook helpers. None of these surfaces defines a separate
agent implementation.

## Core architecture responsibilities

| Responsibility | What it provides |
| --- | --- |
| Agent orchestration | One SDK root agent, model turns, tool selection, nested specialists, and final answers |
| Model access | A provider boundary for OpenRouter models, aliases, client lifetime, and tool-call transport adaptation |
| Tool composition | Small typed FunctionTools plus Agent-as-tool specialists that can be combined for multi-step work |
| Session continuity | SDK conversation history, application metadata, resumable approvals, and session-scoped state |
| Workspace isolation | A persistent SDK sandbox with validated workspace-relative paths and host-path redaction |
| Durable execution | SQLite-backed queues and detached workers for agent runs, knowledge ingestion, and pipelines |
| Streaming and observability | SDK event normalization, persisted sequence numbers, SSE delivery, polling, traces, and runtime evidence |
| Approval control | Serializable SDK RunState, explicit approval decisions, and approval-aware pipeline operations |
| Knowledge lifecycle | Crawl, normalize, deduplicate, chunk, embed, index, retrieve, and cite trusted knowledge |
| Pipeline execution | Discover, validate, plan, approve, run, monitor, cancel, and verify reproducible workflows |
| Website integration | Authenticated host-page context, structured tables and figures, manuals, imports, and UI actions |
| Public boundary protection | Guardrails, provider isolation, credential protection, structured results, and relative-path serialization |

## Key system functions

These are the main capabilities available through the root agent and its
specialists.

| Capability | Key functions |
| --- | --- |
| Sequence biology | `sequence_stats`, `sequence_find_orfs`, `sequence_translate`, and `sequence_reverse_complement` |
| Genome and structure biology | `genome_read_features`, `genome_render_map`, `structure_inspect`, `blast_search`, `alphafold_download`, and `pdb_download` |
| Biological databases | `ncbi_retrieval`, `database_lookup`, and provider-backed annotations from NCBI, UniProt, InterPro, KEGG, QuickGO, PDB, and AlphaFold |
| Data analysis | `table_profile`, `table_group`, and `table_plot` for workspace CSV, TSV, and Excel data |
| Research and sources | `pubmed_search`, `web_search`, and `web_fetch` for run-local source collection |
| Knowledge base | `knowledge_ingest`, `knowledge_status`, `knowledge_retrieve`, `evidence_index`, and `evidence_retrieve` for durable session-owned knowledge |
| Reports | `report_review`, `report_synthesize`, and `report_write` for evidence-bound review, cited drafting, and saved Markdown reports |
| Workspace and documents | `file_inspection`, `document_read`, `workspace_search`, uploads, downloads, and artifact previews |
| Coding | `code_inspection`, `code_edit`, and `code_test` inside the active workspace |
| Pipelines | `pipeline_shell` operations for catalog, files, examples, plans, runs, status, bounded waits, results, and cancellation |
| Trusted websites | `website_context`, table and figure reads, manual search/read, `website_import_data`, highlights, navigation, and approved host actions |
| User interaction | Persistent sessions, direct or queued runs, streamed events, approval prompts, status polling, and resumable event delivery |

## Repository boundaries

| Area | Responsibility |
| --- | --- |
| harness | SDK runtime context, sessions, streaming, approvals, jobs, sandbox setup, guardrails, and website transport |
| models | OpenRouter model provider, model aliases, and wire-format adaptation |
| tools/function_tools | Atomic public SDK FunctionTools grouped by user capability |
| tools/agent_tools | Specialist SDK Agents and Agent-as-tool composition |
| tools/infrastructure | Workspace, providers, knowledge, pipeline engine, tool support, and SDK adapters |
| tools/runtime_tools | Pipeline definitions and domain-specific pipeline bundles |
| interfaces | HTTP API, static UI, SSE, workspace API, and website bridge endpoints |
| docs | External integration contracts, usage notes, and this architecture reference |
| evals | Smoke checks for boundaries, transport, tools, jobs, website integration, and pipelines |

The top-level legacy composite workflows and the old standalone rag package are not
runtime entry points. New features should extend the current SDK tool,
specialist, knowledge, or pipeline boundaries.

<a id="models-and-provider-ownership"></a>

## OpenAI Agents SDK integration

The SDK is the orchestration boundary. The [Agents SDK tools guide](https://openai.github.io/openai-agents-python/tools/) is the reference for the FunctionTool and Agent-as-tool primitives used here:

- harness/agent.py constructs the root Agent named Pipeline2Agent.
- tools/registry.py supplies the root agent's FunctionTools, specialist
  Agent-as-tools, hosted tools, and runtime tools.
- harness/runtime.py creates one AgentRunContext per run and invokes Runner.run
  for direct work or Runner.run_streamed for queued streaming work.
- the model is selected through the SDK ModelProvider interface in
  models/openrouter_provider.py.
- public function tools use the SDK FunctionTool contract through
  tools/infrastructure/tool_support/decorators.py.
- specialist agents are exposed with Agent.as_tool when a coordinator should
  retain control of the conversation.
- report review and report synthesis are nested SDK Agents. They receive
  evidence paths and source identifiers and do not perform searching or writing.
- pipeline_shell is a native SDK ShellTool adapter with an allowlisted
  agent-pipeline protocol.

The application adds persistence, workspace confinement, provider clients, and
HTTP transport around the SDK. It does not implement a second agent loop.

### Model ownership

models/openrouter_provider.py implements the SDK ModelProvider contract. It
creates one lazy AsyncOpenAI client per run, caches SDK Model objects by native
provider model ID, and closes clients that it owns. models/config.py owns model
aliases, default turn limits, and embedding configuration.

models/local_tools_model.py is a wire adapter for OpenRouter-compatible Chat
Completions responses that contain shell or custom tool calls. It converts those
items to the SDK response-item shape and lets the normal Runner continue the
turn. It is transport compatibility code, not a second orchestration loop.

The current dependency versions are pinned in requirements.txt. The installed
environment currently uses openai-agents 0.22.2 and openai 3.13.0. Update this
document when the supported SDK contract changes.

## Request and run lifecycle

A request is associated with a session identifier and a session-owned workspace.

Direct execution:

1. The HTTP layer validates the request and resolves a session.
2. harness/runtime.py opens the SDK SQLiteSession and the session workspace.
3. AgentRunContext records model, provider, workspace, website binding, and
   execution limits.
4. Runner.run executes Pipeline2Agent with the configured tools and guardrails.
5. The response is converted to the public API shape and persisted in the SDK
   session history.

Durable execution:

1. POST /run or POST /run_stream creates a run in the SQLite RunQueue.
2. The response contains the run identifier and queue status.
3. A detached worker process claims the run and calls the same runtime path.
4. SDK events are normalized by harness/streaming.py and persisted with a
   monotonically increasing sequence number.
5. Clients read status and events using the run endpoints.
6. The run ends as succeeded, failed, interrupted, blocked, or
   pending_approval.

The canonical queue and worker implementation is harness/jobs.py. There are no
separate job_queue.py or job_worker.py runtime services. The module contains the
SQLite queue, claim/update operations, worker entry point, and event persistence.
The default run database is runtime/agent_runs.sqlite3 and
AGENT_RUN_WORKERS defaults to two workers.

A worker failure changes the run to interrupted. The system does not silently
replay an interrupted agent run because tool calls can have side effects. A
caller can create a new run when a retry is appropriate.

## Streaming, polling, and approvals

The SDK's streamed events are converted into a stable public event vocabulary by
harness/streaming.py. It handles agent lifecycle events, tool calls, tool
results, nested Agent-as-tool events, text deltas, approvals, and errors.

Text deltas are buffered before public path redaction. Function argument deltas
are not exposed as public content. Workers batch event writes so that long
streams do not issue one database transaction for every token.

The public event API is sequence based:

- GET /runs/<run-id> returns status and metadata.
- GET /runs/<run-id>/events?after=N returns events after sequence N.
- A client reconnects by retaining the last received sequence and polling again.
- SSE is a delivery format layered over the same persisted events; the run queue
  remains the source of truth.

There is no requirement for a second streaming protocol between the model and
the application. The browser-facing SSE stream and the website postMessage
bridge are separate transports.

Approval flow:

1. A tool or pipeline operation returns an SDK approval request.
2. The run is persisted as pending_approval with serializable RunState.
3. The client receives the approval item through the run event stream.
4. POST /approve or POST /approve_stream records the decision.
5. The worker resumes the saved run state through the SDK.

Code editing and execution do not require an approval gate in the current
configuration. Pipeline execution and cancellation do require SDK approval.

## Sessions and workspace isolation

There are three related stores:

| Store | Default | Purpose |
| --- | --- | --- |
| SDK session history | runtime/agent_sessions.sqlite3 | SDK conversation items and resumable run state |
| application session metadata | runtime/session_metadata | labels, timestamps, website binding metadata, and UI state |
| session workspace | runtime/sessions/<session-id> | files, inputs, outputs, runs, and private pipeline data |

The SDK sandbox is a persistent Unix-local workspace for the session. A
NoopSnapshotSpec is used because the application manages persistence and cleanup.

Workspace directories include:

- uploads for user-provided files;
- inputs for imported website data and pipeline inputs;
- outputs for generated reports and artifacts;
- runs for run-specific material;
- .pipeline for private pipeline job metadata.

tools/infrastructure/workspace/paths.py is the path boundary. It rejects
absolute paths, traversal, hidden path components, and symlink escapes.
tools/infrastructure/workspace/sdk.py exposes regular files through the SDK
sandbox.

tools/infrastructure/workspace/public.py is the public serialization boundary.
It removes host filesystem prefixes and emits workspace-relative paths in model
messages, browser payloads, tool results, and API responses. A host path may be
used internally by a provider or worker, but it must not cross this boundary.

Files are the source of truth for artifacts. There is no second public artifact
registry that can diverge from the workspace.

## Tool architecture

See [tool definitions](tool_definitions.md) for the model-facing FunctionTool,
Agent-as-tool, website, knowledge, and runtime-tool contracts.

tools/registry.py builds the model-facing tool list:

    FUNCTION_TOOLS + specialist Agent-as-tools
                   + hosted tools
                   + runtime tools

The current hosted-tool list is empty. Runtime tools currently include the
pipeline shell adapter.

tools/function_tools/__init__.py is the explicit catalog of public tools. It
does not scan files dynamically and there is no required catalog.py discovery
layer. Each group exports its tools explicitly.

Every public function tool is a native SDK FunctionTool created through the
bio_function_tool decorator. The decorator applies strict input schemas,
timeouts, tool guardrails, and the common FunctionResult envelope. A tool owns
its public input model, deterministic operation, result model, and failure
format.

Public tools should be:

- small enough for an agent to compose;
- deterministic where their work is deterministic;
- explicit about workspace paths and provider side effects;
- safe to call repeatedly when possible;
- independent of other public tools;
- free of direct model prompting or conversation state.

A tool may call an infrastructure service or provider adapter. It should not
call another public model-facing tool to create an implicit workflow.

### Function tool groups

| Group | Current tools |
| --- | --- |
| biology | sequence_stats, sequence_find_orfs, sequence_translate, sequence_reverse_complement, alphafold_download, ncbi_retrieval, database_lookup, pdb_download, blast_search, structure_inspect, genome_read_features, genome_render_map |
| data_analysis | table_profile, table_group, table_plot |
| sources | pubmed_search, web_search, web_fetch |
| knowledge | evidence_index, evidence_retrieve, knowledge_ingest, knowledge_status, knowledge_retrieve |
| workspace | file_inspection, document_read, workspace_search, report_write |
| coding | code_inspection, code_edit, code_test |
| website | website_context, website_read_table, website_read_figure, website_search_manual, website_read_manual, website_import_data, website_highlight, website_navigate, website_action |

Data analysis is a capability group rather than a biology subtype. It can profile,
group, and plot tables from any trusted workspace domain.

## Specialist agents

Specialists are SDK Agents used for focused multi-step behavior. They are not
function tools and do not replace atomic tools.

Current specialists:

| Specialist | Responsibility |
| --- | --- |
| research_specialist | web and PubMed research, web fetching, durable knowledge, evidence, report review/synthesis, and report writing |
| pipeline_specialist | pipeline catalog, planning, execution, status, results, and cancellation |
| document_specialist | workspace search, document reading, and file inspection |
| data_analysis_specialist | table profiling, grouping, plotting, file inspection, and workspace search |
| coding_specialist | code inspection, code editing, and code tests |
| website_guide_specialist | trusted website context, tables, figures, manuals, data import, highlights, navigation, actions, and workspace inspection |

The website guide is an Agent-as-tool. It uses the website tools to inspect a
trusted host page and explains the page or guides the user through it. It does
not receive arbitrary browser pixels or private host DOM data.

The specialist files contain instructions and tool composition. Domain
operations belong in FunctionTools or infrastructure services.

## Reporting

tools/agent_tools/reporting contains:

- review.py: an SDK Agent that checks an existing evidence-backed report;
- synthesize.py: an SDK Agent that combines supplied evidence into a draft;
- runtime.py: reporting-specific shared runtime and contracts.

The reporting agents are intentionally bounded. They accept evidence artifacts
and exact source identifiers; they do not search the web, crawl pages, or write
files. report_write is a separate deterministic FunctionTool that writes the
final report artifact to the workspace.

This division keeps retrieval, reasoning, and artifact writing observable and
composable.

## Providers and infrastructure

tools/infrastructure/providers contains integration clients for external data
services. Current families include NCBI Entrez, BLAST, PDB, AlphaFold, and
database adapters for UniProt, InterPro, KEGG, QuickGO, PDB, and AlphaFold.

Providers are implementation dependencies, not model-facing tools. They:

- validate and normalize provider requests;
- apply timeout, retry, and response-size policies;
- convert provider responses into internal models;
- keep credentials and host networking out of the SDK tool schema.

A public FunctionTool calls a provider when it needs external data and then
returns a stable result model. This preserves SDK-native tool behavior while
keeping vendor-specific code out of agent prompts.

The infrastructure package also contains:

- workspace and public path serialization;
- tool decorators and guardrails;
- the knowledge service and crawler adapters;
- the pipeline engine;
- SDK adapters such as pipeline_shell.

## Knowledge and retrieval

Knowledge is a durable subsystem, separate from ordinary one-shot web search.

The flow is:

    knowledge_ingest
        -> KnowledgeService and KnowledgeRepository
        -> KnowledgeJobQueue and worker
        -> HTTP crawler or optional Scrapy subprocess
        -> normalized KnowledgePage
        -> content hash and chunking
        -> embeddings and SQLite storage
        -> knowledge_retrieve
        -> citation-ready evidence artifact

tools/infrastructure/knowledge owns the service, repository, job queue, worker,
indexer, models, storage, and crawlers. The public FunctionTools are
knowledge_ingest, knowledge_status, knowledge_retrieve, evidence_index, and
evidence_retrieve.

The default database is runtime/knowledge.sqlite3. AGENT_KNOWLEDGE_DB selects a
different path and AGENT_KNOWLEDGE_WORKERS controls the worker count.
AGENT_KNOWLEDGE_CRAWLER accepts auto, http, or scrapy.

The HTTP crawler validates HTTP(S) URLs, rejects private network targets and
credentials, bounds redirects and domains, and limits pages and depth. Scrapy
runs in an isolated subprocess so its reactor does not conflict with the SDK
event loop. Scrapy is optional at runtime but its dependency is included in
requirements.txt.

The current retrieval implementation combines lexical overlap and Python cosine
similarity over stored vectors. It does not require an external vector database
or ANN service. Collection ownership is scoped to the session.

Knowledge ingestion is a durable job. Retrieval is a normal FunctionTool over
completed indexed content. Search results and evidence citations remain
distinct from report synthesis.

## Pipeline engine

<a id="pipeline-runtime"></a>

Pipeline definitions live under tools/runtime_tools/pipelines. The execution
service lives under tools/infrastructure/pipeline_engine and includes commands,
store, service, worker, and engine adapters.

pipeline_shell is a native SDK ShellTool, but it accepts only one allowlisted
agent-pipeline command protocol. The parser uses shlex and argparse. It rejects
arbitrary shell text, pipes, redirects, command substitution, and workspace
overrides.

The protocol supports:

- catalog, files, and example for discovery;
- plan for a validated, hashed execution plan;
- run for durable execution;
- jobs and status for inspection;
- wait for bounded waiting of at most 30 seconds;
- results for verified outputs and previews;
- cancel for approved cancellation.

Pipeline run and cancellation require approval. Discovery, planning, status,
bounded wait, and result inspection do not.

Pipeline metadata is stored in .pipeline/jobs.sqlite3 within the session
workspace. Job states are planned, queued, running, succeeded, failed,
timed_out, cancelled, and interrupted.

The plan hashes the pipeline definition and input files. The worker verifies
those hashes, copies inputs into the job directory, checks output confinement,
and records output hashes. Results can include ZIP artifacts, table previews,
and metrics.

### Adding a pipeline

Add a self-contained bundle under tools/runtime_tools/pipelines with a
runner.yaml manifest, declared inputs and outputs, an engine configuration,
example data when useful, and a README. Keep execution-specific code inside
the bundle. The pipeline engine discovers bundles from this directory, validates
the manifest, and exposes the bundle through catalog, plan, run, status, and
results operations. See [pipeline manifest definitions](pipeline_definitions.md)
for the field contract and selection guidance. Add or update a pipeline smoke
check when the bundle changes.

Supported adapters include shell, Snakemake, Nextflow, and WDL. WDL execution
uses local miniwdl by default; setting `CROMWELL_URL` selects the Cromwell REST
backend. A manifest can declare a container boundary for deployment metadata,
but local execution does not automatically containerize every engine. Local
process limits include per-process memory limits; aggregate cgroup isolation is
a deployment concern.

## Trusted website embedding

The website bridge lets a trusted external website expose structured context
and actions to an embedded agent. The full external developer contract is in
[docs/web_integration.md](web_integration.md).

harness/website.py provides:

- exact origin allowlisting through AGENT_WEBSITE_SITES;
- HMAC authentication through AGENT_WEBSITE_SECRET;
- one-use demo tickets;
- session, site, and instance-scoped bindings;
- SQLite request and response records;
- an eight-hour binding lifetime;
- request timeout and context/result size limits.

The bridge uses postMessage between the host page and the embedded assistant and
HTTP polling between the assistant server and the host bridge. It is separate
from agent SSE.

The canonical local fixture is web_ui/assistant-demo.html and is served at
/assistant-demo. web_ui/assistant-embed.js and web_ui/assistant.js implement
embedding. The old examples/external-workspace page is not the runtime fixture.

The host can implement these callbacks:

- getPageContext;
- readTable;
- readFigure;
- searchManual;
- readManual;
- exportData;
- highlight;
- navigate;
- invokeAction.

Context is structured data and accessible manual text, not arbitrary DOM pixels.
The host must return only data it is willing to expose. Website data enters the
normal workspace only when the user or agent explicitly calls
website_import_data, which writes a UTF-8 export beneath inputs.

When no explicit AGENT_WEBSITE_SITES is configured, the local server can add
trusted localhost and detected LAN origins for development. An explicit
allowlist always takes precedence. Production sites should use exact origins
and a stable secret.

Website binding metadata is private session state. The website secret and
binding internals are excluded from public model and run metadata.

## HTTP interfaces

interfaces/web.py is a standard-library ThreadingHTTPServer. It serves both the
assistant UI and the JSON/SSE API.

Main read endpoints:

- GET / and GET /assistant serve the assistant UI;
- GET /assistant-demo serves the canonical embedding fixture;
- GET /health and GET /config expose health and non-secret configuration;
- GET /sessions lists sessions; GET /sessions/<id>/messages reads session messages;
- GET /runs, GET /runs/<id>, and GET /runs/<id>/events inspect durable runs;
- GET /knowledge/jobs/<id> inspects knowledge ingestion;
- GET /knowledge/jobs/<id>/events?session_id=<id>&after=N returns resumable
  ingestion events, and /knowledge/jobs/<id>/stream provides SSE;
- GET /workspace and GET /workspace/file inspect session files.

Main write endpoints:

- POST /run and POST /run_stream start durable runs;
- POST /approve and POST /approve_stream resume approved runs;
- POST /workspace/files uploads files;
- PATCH /sessions/<id> updates session metadata;
- DELETE /sessions/<id> removes session-owned state; DELETE /workspace/files/<path>
  removes one workspace file;
- POST /website/demo-token, /website/connect, /website/context,
  /website/poll, /website/respond, and /website/disconnect implement the bridge.

The UI is split into api-client.js, session-state.js, message-renderer.js,
artifact-viewers.js, app.js, and approval handling. Workspace artifacts are
rendered from public metadata and workspace-relative paths.

## Guardrails and security

harness/guardrails.py contains input and output tripwires for sensitive
biological inputs, empty answers, and biological claims that lack tool results.
Tool guardrails add the common execution envelope.

Important boundaries are:

- model tools cannot access host paths directly;
- public paths are relative to the active workspace;
- symlink and traversal escapes are rejected;
- website origins are exact and authenticated;
- website requests are scoped to a session and binding instance;
- knowledge crawlers reject credentials and private network targets;
- pipeline_shell does not expose arbitrary shell syntax;
- provider credentials stay in infrastructure;
- website secrets never enter public run metadata;
- durable workers do not automatically replay interrupted side effects.

A deployment that needs stronger isolation should run workers in containers or a
sandboxed service and configure filesystem, network, CPU, and memory limits at
that deployment boundary.

## Configuration

Important environment variables include:

| Variable | Purpose |
| --- | --- |
| OPENROUTER_API_KEY | model provider credential |
| OPENROUTER_BASE_URL | OpenRouter-compatible API base URL |
| AGENT_MODEL | model alias or provider model identifier |
| AGENT_SESSION_DB | SDK SQLiteSession database |
| AGENT_METADATA_DIR | application session metadata directory |
| AGENT_SESSIONS_DIR | session workspace root |
| AGENT_RUN_DB | durable agent run database |
| AGENT_RUN_WORKERS | run worker count |
| AGENT_KNOWLEDGE_DB | knowledge database |
| AGENT_KNOWLEDGE_WORKERS | knowledge worker count |
| AGENT_KNOWLEDGE_CRAWLER | auto, http, or scrapy |
| AGENT_WEBSITE_SITES | exact trusted website origins |
| AGENT_WEBSITE_SECRET | website bridge HMAC secret |
| AGENT_WEBSITE_DB | website bridge SQLite database |

Model aliases and the default model are defined in models/config.py. The
default model key is gpt-5.6-luna and the default maximum agent turns is five.
Environment-specific secrets should be supplied outside source control.

## Testing and operational checks

The architecture smoke suite is intentionally boundary oriented:

- evals.smoke_architecture;
- evals.smoke_function_boundary;
- evals.smoke_website_bridge;
- evals.smoke_knowledge;
- evals.smoke_session_artifacts;
- evals.smoke_session_history;
- evals.smoke_approvals;
- evals.smoke_pipeline_config;
- evals.smoke_pipeline_runtime;
- evals.smoke_atomic_tools;
- evals.smoke_model_provider;
- evals.smoke_local_transport;
- evals.smoke_reporting.

Run a focused smoke test after changing one boundary and the full suite before
changing the public contract. For HTTP or browser changes, also verify the
health endpoint, a fresh session, a durable run with event polling, and the
trusted website connect/context path.

## Extension rules

When adding a capability:

1. Decide whether it is an atomic FunctionTool, an Agent-as-tool specialist,
   a knowledge job, a pipeline definition, or infrastructure.
2. Keep the public SDK schema small and return a stable result model.
3. Keep provider clients, credentials, host paths, and retry policy below the
   public tool boundary.
4. Add the tool explicitly to its function_tools group and registry path.
5. Add a specialist only when composition needs focused instructions or nested
   reasoning.
6. Make long work durable and expose status and persisted events.
7. Preserve workspace-relative public paths.
8. Add a smoke test at the boundary that changed.
9. Update docs/web_integration.md when the website contract changes.
10. Update this document when a runtime boundary, public endpoint, or persistence
    model changes.
