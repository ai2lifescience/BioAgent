# Pipeline2Agent architecture

Pipeline2Agent uses one OpenAI Agents SDK runtime. The SDK owns model turns,
tool calling, sessions, guardrails, and tracing. Pipeline2Agent supplies typed biological
function tools and deterministic implementations for scientific operations.

Internal names use `agent`: the Python entry points are `run_agent`,
`async_run_agent`, `resume_agent`, and `async_resume_agent`; pipeline commands
use `agent-pipeline`, and environment variables use the `AGENT_` prefix.
The public browser embedding API is `Pipeline2AgentDrawer`.

![Pipeline2Agent current system architecture](images/system_architecture.png)

## Runtime flow

```text
Web / CLI / API / notebook
        |
        v
harness.run_agent()
        |
        v
Agents SDK Agent + Runner
        |                    \
        |                     SDK tracing and lifecycle hooks
        |                     per-session Unix-local sandbox
        v
RunConfig.model_provider -> OpenAI Chat Completions client -> OpenRouter
        |
        v
Pipeline2Agent function, specialist, and runtime tools
        |
        +-- biological databases and literature
        +-- sequence, BLAST, genome, and structure analysis
        +-- workspace documents, bounded data analysis, web research, and coding
        +-- file inspection and report writing
        +-- RAG and OpenRouter embeddings
        +-- approved pipeline execution and result collection
        |
        v
SDK guardrails -> structured result -> user interface
```

The root agent selects tools through the SDK model loop. Domain specialists
are exposed through `Agent.as_tool()`. Function-tool workflows and their
implementations live under `tools/function_tools/<tool_name>/`; pipeline
execution lives under `tools/runtime_tools/pipeline_runtime/`. Reporting agents
live under `tools/function_tools/species_report/reporting/`.

## Components

### Agents SDK harness

- `harness/agent.py` defines the single `Pipeline2Agent` and its instructions.
- `harness/runtime.py` creates the `Runner`, supplies run context, and returns
  the application result.
- `tools/function_tools/` contains the public biological `FunctionTool`
  definitions and `tools/agent_tools/` contains the `Agent.as_tool()`
  specialists.
- `tools/registry.py` assembles function, agent, hosted, and runtime tools for
  the root Agent.
- `harness/guardrails.py` contains input safety and output evidence checks.
- `harness/sandbox.py` configures the SDK Unix-local sandbox around the
  per-session workspace. The SDK supplies filesystem capabilities; the
  approval-controlled `pipeline_shell` ShellTool is the command-execution
  boundary.
- `tools/workspace/` owns safe workspace paths and small file metadata helpers
  for the SDK sandbox listing and browser adapter; the SDK sandbox remains the
  source of truth for files and their lifecycle.
- `harness/tracing.py` consumes SDK lifecycle hooks and spans locally without
  sending traces to OpenAI. The hooks provide UI progress; the SDK remains the
  source of trace/span creation.
- `harness/sessions.py` stores application metadata; conversation history is
  stored by the SDK `SQLiteSession`.

### Models and provider ownership

Pipeline2Agent uses the SDK's per-run `ModelProvider` integration: agents declare a
model alias, and `RunConfig(model_provider=provider)` resolves it to an SDK
`Model`. This follows the [SDK model integration guide](https://openai.github.io/openai-agents-python/models/#non-openai-models).
The application owns the provider's lifetime and closes it after the run, as
specified by the [SDK provider interface](https://openai.github.io/openai-agents-python/ref/models/interface/).

```text
models/
├── config.py             # model aliases, native IDs, labels, environment defaults
├── openrouter_provider.py           # OpenRouterProvider: SDK ModelProvider and client lifetime
├── openrouter_transport.py  # OpenAI / AsyncOpenAI transport configuration
└── local_tools_model.py   # local shell/custom-tool wire adapter

harness/agent.py          # root Agent definition and specialist assembly
tools/function_tools/species_report/reporting/
├── agents.py             # reporting Agent + Runner invocation
├── opinions.py           # concurrent model opinions
├── synthesis.py          # report synthesis and ordered fallback
└── prompts.py            # scientific reporting instructions

rag/embeddings.py         # embeddings for retrieval records and queries
```

`harness/runtime.py` creates an `OpenRouterProvider` for each run or approval
resume. The provider creates one `AsyncOpenAI` client lazily when the SDK first
resolves a model. It caches model instances by native model ID. Root and
specialist agents share this provider through the nested SDK run configuration;
agent construction itself opens no network client. Explicitly injected SDK
`Model` instances, including offline `ScriptedModel` fixtures, need no provider
credentials.

On completion, failure, or approval pause, the harness closes the provider and
its owned client. Resuming a saved `RunState` builds agent definitions and a
fresh provider. An explicitly injected client remains owned by its caller.
Pipeline2Agent supplies the model provider on each run without changing the SDK's
global default model API or client.

`models/config.py` maps UI/CLI keys such as `gpt-oss` to native OpenRouter IDs.
The provider also accepts an explicit native ID; prefixes such as `openai/` and
`openrouter/` are preserved. Change a catalog entry's `model` value or its
documented environment override to select a deployment. Adding a catalog
entry exposes it in the model selector and the default report opinion set;
check that the selected model supports the tools used by its agents.

`models/openrouter_transport.py` constructs the official OpenAI `OpenAI` and
`AsyncOpenAI` clients with:

- `OPENROUTER_API_KEY` for authentication;
- `OPENROUTER_API_BASE`, defaulting to `https://openrouter.ai/api/v1`;
- optional `HTTP-Referer` and `X-OpenRouter-Title` headers;
- HTTPX2 clients with explicit proxy selection from `AGENT_PROXY`, falling
  back to `ALL_PROXY`/`all_proxy`.

SDK model runs and embeddings use this OpenRouter transport. Credentials are
read when a client is created. Embeddings use `client.embeddings.create()` in
`rag/embeddings.py`, which closes the client after each batch and matches
returned vectors to inputs by their provider indexes.

### Reporting agents

The species-report workflow runs in the function tool's worker thread. Its
reporting services run SDK agents with `asyncio.run()` at that synchronous
boundary. Opinion requests use `asyncio.gather()` and share one provider per
batch; a failed request is recorded alongside successful opinions. Synthesis
tries the requested or configured synthesis model, then the remaining catalog
models in order. An empty response counts as a failure, and exhaustion raises
an error containing the attempted models' failures.

Reporting instructions and prompts belong to the species-report package.
`Agent`, `ModelSettings`, `Runner`, and `RunConfig` control each reporting call.
The reporting provider closes after the batch, and SDK spans are recorded
locally in the calling run's trace when its `AgentRunContext` is supplied.

### Tool categories

The SDK tool surface is organized by execution semantics:

- `tools/function_tools/` — local Python `FunctionTool` wrappers for biological
  and general assistant workflows. This is Pipeline2Agent's primary category.
- `tools/agent_tools/` — focused agents exposed through `Agent.as_tool()`.
- `tools/hosted_tools/` — extension point for tools executed by OpenAI-hosted
  infrastructure. It is empty until the configured model/runtime supports one.
- `tools/runtime_tools/` — the SDK local `pipeline_shell` tool and its
  allowlisted command protocol. It runs all declared pipeline engines locally.
- `tools/runtime_tools/pipeline_runtime/` — declarative pipeline planning, durable jobs,
  bounded waiting, cancellation, and result collection behind `pipeline_shell`.
- `tools/common/` — shared context, result envelopes,
  evidence and generic result-path handling, guardrails, FunctionTool setup,
  and generic bounded HTTP transport. These are implementation helpers, not
  model-facing tools. Domain parsers, external-service allowlists, web
  collection policy stay in the owning package. Workspace file metadata lives
  under `tools/workspace/`; the SDK sandbox remains the file owner.

`harness/agent.py` calls `tools.registry.build_all_tools(model)` so the root
agent receives one SDK tool list assembled from these categories.

Import tools and helpers directly from their category packages:

```python
from tools.function_tools.file_inspection import file_inspection
from tools.agent_tools import build_specialist_tools
from tools.common.results import ToolResult
```

Function-tool packages use a consistent layout:

```text
tools/function_tools/<tool_name>/
├── __init__.py       # public SDK FunctionTool
├── workflow.py       # run-context and result presentation
├── analysis.py       # deterministic domain implementation
└── adapters/         # optional external database clients
```

Each function tool is a self-contained plug-in. Its package owns the public
schema, workflow, domain implementation, external adapters, and tool-specific
validation. It may use generic services from `tools/common/`, but it must not
import another public FunctionTool or depend on another tool's biological
implementation. Adding or removing a tool should require only its package and
the explicit registry entry; unrelated tools must continue to work unchanged.

Small tools keep one descriptive implementation module, such as `analysis.py`
or `inspection.py`, and `workflow.py` only when they need
run context or result presentation. A
package should add a subpackage only for a real subsystem, such as NCBI
Entrez or species-report literature/web/RAG collection. Pipeline engine adapters
live separately under `tools/runtime_tools/pipeline_runtime/engine/`.
Shared context, result envelopes, guardrails, generic result-path handling, and
generic HTTP transport belong under `tools/common/`. Workspace path safety and
file metadata belong under `tools/workspace/`. The HTTP layer supplies
bounded transport only; every adapter passes its own HTTPS host allowlist.
HTML/search parsers, endpoint policies, biological implementations, and the
host's file-serving policy stay outside `tools/common/` under
`tools/workspace/`. There is no central sequence or biology adapter. Public
FunctionTool wrappers are never imported as implementation dependencies, so a
tool can be added, removed, or tested independently.

### Function tools and workflows

Every agent-facing workflow in `tools/function_tools/` is an OpenAI Agents SDK
`FunctionTool`. The SDK `@function_tool` decorator owns its name, description,
argument schema, validation, invocation, and failure handling. The same
function-tool package contains the workflow and its deterministic adapters,
clients, and domain code. Scientific calculations run in those implementations;
workflows that synthesize reports call SDK reporting agents through
`tools/function_tools/species_report/reporting/agents.py`.

The general assistant tools follow the same boundary. `workspace_search` reads
only listed session files and returns bounded excerpts with file or PDF-page
sources. `data_analysis` accepts bounded pandas operations and writes plots into
the session output directory. `web_research` uses bounded HTTP requests,
preserves source URLs, and rejects local or private fetched hosts. The coding
tools keep inspection read-only; `code_edit` and `code_test` are SDK approval
tools, restrict paths to the active workspace, and allow only fixed test
commands.

### Tool routing contract

The root agent does not use a separate keyword router. When a request arrives,
the Agents SDK presents the model with the registered tool names, descriptions,
and JSON schemas. The model selects the tool whose documented purpose best
matches the user's intent and emits arguments that conform to that schema. The
SDK validates those arguments, invokes the Python function, and gives the
result back to the model for the final response.

Routing-critical information belongs in five places:

1. **Function names** — name one clear operation.
2. **Function docstrings** — explain what the tool does, when to use it, and
   when another tool is more appropriate.
3. **Parameter descriptions** — explain ambiguous inputs and side effects.
4. **Type constraints** — use annotations, `Literal`, and `pydantic.Field` to
   constrain the arguments the model can generate.
5. **Agent instructions** — define cross-tool policy, safety rules, and how
   the agent should use the available tools.

The SDK derives function-tool schemas from these definitions, validates the
model's arguments, and returns the invoked function's result to the model.
Biological function tools return the common
`status`/`data`/`files`/`evidence`/`error` envelope. The local ShellTool returns
command JSON inside an SDK `ShellResult`.

The local `pipeline_shell` ShellTool accepts the `agent-pipeline` command
protocol. Its executor parses the command and dispatches validated operations
to the pipeline service. SDK filesystem capabilities provide workspace file
inspection and editing; biological command execution uses `pipeline_shell`.

For example, a request to search AlphaFold metadata should select
`database_lookup` with `database="alphafold"`, while a request to download an
AlphaFold structure should select `alphafold_download`. A request for sequence
similarity should select `blast_search`. This is model-based semantic routing,
so overlapping tool descriptions make selection less reliable; deterministic routing should be
implemented in code when a workflow requires predictable dispatch.

The primary intent boundaries are:

| User intent | Direct route |
| --- | --- |
| Raw nucleotide or protein records | `ncbi_retrieval` |
| Cited organism research or Markdown report | `species_report` |
| Database annotations or metadata | `database_lookup` |
| Download an RCSB PDB file | `pdb_download` |
| Download an AlphaFold structure | `alphafold_download` |
| Analyze an existing structure file | `protein_structure_analysis` |
| Sequence metrics or ORFs | `sequence_analysis` |
| File metadata or previews | `file_inspection` |
| Sequence similarity | `blast_search` |
| Genome feature image | `genome_map` |
| Search uploaded documents | `workspace_search` |
| Read or summarize a workspace PDF | `document_read` |
| Profile or plot a table | `data_analysis` |
| Current multi-source web question | `web_research` |
| Read-only workspace code question | `code_inspection` |
| Biopython transformation or GenBank feature read | `biology_analysis` |
| Multi-step biology work | `biology_specialist` |
| Multi-step document work | `document_specialist` |
| Multi-step data analysis | `data_analysis_specialist` |
| Multi-source web research | `web_research_specialist` |
| Multi-step coding task | `coding_specialist` |
| Execute or monitor a pipeline | `pipeline_shell` (`agent-pipeline` protocol) |
| Review completed pipeline outputs | `pipeline_shell` with `agent-pipeline results --job-id ID` |

Use a specialist only when the request combines multiple routes in one domain;
use the direct route for a single operation.

See [Pipeline runtime](#pipeline-runtime) for pipeline discovery, input mapping,
execution, result collection, and adding new pipelines.

Routing information that the model must see belongs in the FunctionTool name,
docstring, schema descriptions, or agent instructions. Executable workflows
live under `tools/function_tools/`. Developer guidance lives in this architecture
reference; user examples are in the [web usage guide](web_usage.md#usage-examples)
and [CLI guide](cli_usage.md).

### Specialist agents

`tools/agent_tools/specialist/` defines focused agents for biology, retrieval,
pipeline, document, data-analysis, web-research, and coding domains. Each
domain module owns its instructions and smaller tool set; the parent
`registry.py` assembles them and exposes each one to the root agent with
`Agent.as_tool()`. This keeps domain changes and tests isolated while the root
agent retains control of the user-facing answer.

```text
tools/agent_tools/
├── __init__.py             # root-agent integration
├── registry.py             # ordered specialist registry
└── specialist/
    ├── __init__.py         # specialist builders
    ├── biology.py          # sequence, Biopython, genome, BLAST, and structure tasks
    ├── retrieval.py        # NCBI, database, and species-report tasks
    ├── pipeline.py         # pipeline planning, execution, and collection
    ├── document.py         # uploaded document search and reading
    ├── data_analysis.py    # bounded table analysis and plots
    ├── web_research.py     # current public web research
    └── coding.py           # workspace inspection, edits, and tests
```

The root agent exposes direct tools and specialist tools. The pipeline
specialist uses the same `pipeline_shell` tool as the root. Specialists share
application context and tracing, but do not automatically receive the root's
SQLite conversation history; the root supplies the goal, paths, constraints,
and relevant prior results in the delegated request.

The workflow wrapper keeps the common envelope at the SDK boundary while
preserving raw action results inside `AgentRunContext` for evidence collection
and workspace file discovery.

The SDK run context carries:

- the session identifier;
- run and workspace directories;
- user context and workspace file references;
- model key;
- progress callback;
- per-run workflow results.

The direct public FunctionTools are listed by `tools.function_tools.FUNCTION_TOOLS`;
the complete root surface is assembled by `tools.registry.build_all_tools`.

### Sessions and workspace files

`SQLiteSession` persists user and assistant messages in
`runtime/agent_sessions.sqlite3` (configurable with `AGENT_SESSION_DB`).
Application metadata is persisted in `runtime/session_metadata`.

The SDK session is the single source of truth for conversation history. The
browser stores only the active session identifier in `localStorage`; it does
not cache messages or maintain a second conversation database. `GET
/sessions/<session-id>/messages` reads displayable user and assistant items
from `SQLiteSession`, while `Runner.run(..., session=sdk_session)` continues
to append new items. Application metadata remains separate because titles,
locks, resumable approval snapshots, and workspace lifecycle are application
concerns rather than conversation history.

The history endpoint returns conversation text and current approval controls.
Per-run evidence and diagnostic cards remain in memory while the page is open;
workspace files remain available after reload through the sandbox listing.

The SDK Unix-local sandbox uses the session directory as its workspace. This
keeps host-side FunctionTools and SDK filesystem capabilities pointed at the
same files:

```text
runtime/sessions/<session-id>/
├── uploads/
├── outputs/
└── runs/
```

The sandbox is the file owner. The API exposes workspace-relative file paths;
there is no artifact registry or generated artifact ID. The local Unix backend
shares the host OS, so it is a development workspace rather than a strong
security boundary. Use a container-backed SDK sandbox when process isolation is
needed.

The web Workspace panel is a thin view over this sandbox listing. Uploads are
written to `uploads/`, generated files are grouped as outputs, and the panel
offers search, download, and removal. It does not assign pipeline slot labels
or copy paths into chat messages; the agent uses `agent-pipeline files` and
the workspace-relative paths already returned by the sandbox.

PDF uploads can be summarized through the `document_read` FunctionTool. The
tool validates the requested path against the active workspace, extracts
selectable text page by page with `pypdf`, and returns bounded text with page
markers. The agent uses those markers when answering questions about the paper.
Scanned PDFs that contain no selectable text return an OCR-required result;
they are not treated as empty or summarized from invented content. Large
documents are read in page ranges so the complete PDF is not copied into one
model message.

Run-specific temporary files use the same workspace:

```text
runtime/sessions/<session-id>/uploads/
runtime/sessions/<session-id>/outputs/<generated files>
runtime/sessions/<session-id>/runs/<run-id>/
```

The result contains references to files instead of copying large contents into
conversation history. The web interface can download any regular workspace
file; the structure viewer is an optional format-specific presentation.

### Guardrails and run status

The input guardrail blocks requests asking for actionable harmful biological
procedures. Tool guardrails validate each FunctionTool envelope, and the output
guardrail checks the final answer. The API returns the run `status` directly
(`ok`, `pending_approval`, `blocked`, or `error`).

Evidence collection lives in `tools/common/evidence.py` beside tool result
semantics. The harness calls it after a run so the UI can receive citations,
record IDs, URLs, and workspace file paths without making tools import the harness.

Pipeline execution and cancellation use SDK approval. A request pauses with an
SDK `RunState` interruption and returns an approval identifier. Call
`interfaces.api.handle_approval` (or POST `/approve`)
to approve or reject it; approval resumes the saved state without replaying the
original model request.

### Tracing

The SDK creates traces and spans for agent, model, tool, handoff, and guardrail
operations. `LocalTraceProcessor` records redacted lifecycle metadata for the
current run. `AgentHooks` sends progress messages to CLI and streaming HTTP
callers. External trace export is disabled by default because OpenRouter is the
model endpoint and does not provide the OpenAI trace destination.

## Pipeline runtime

Pipeline2Agent runs registered Shell, Snakemake, Nextflow, and WDL workflows
through the SDK local ShellTool named `pipeline_shell`. Pipeline definitions
live under `tools/runtime_tools/pipelines/<pipeline_name>/`. The service scans
folders containing `runner.yaml` whenever the agent requests the catalog.
Pipeline bundles own their execution dependencies and declare a container
boundary in the manifest; the agent environment does not install workflow
dependencies. The human-readable bundle index is in
[`tools/runtime_tools/pipelines/README.md`](../tools/runtime_tools/pipelines/README.md).

| Component | Responsibility |
| --- | --- |
| [Agent instructions](../harness/agent.py) | Interpret the user's goal and choose direct tools or a specialist. |
| [Pipeline tool](../tools/runtime_tools/pipeline_tool.py) | Teach the command protocol, resolve the session workspace, handle SDK approval, and return command results. |
| [Command parser](../tools/runtime_tools/pipeline_runtime/commands.py) | Parse allowed commands and dispatch operations to the service. |
| [Service](../tools/runtime_tools/pipeline_runtime/service.py) | Discover pipelines, validate plans, start jobs, and collect results. |
| [Job store](../tools/runtime_tools/pipeline_runtime/store.py) | Persist plans and job state in SQLite and write job snapshots. |
| [Worker](../tools/runtime_tools/pipeline_runtime/worker.py) | Execute a job independently of the agent request and record its outcome. |
| [Engine adapters](../tools/runtime_tools/pipeline_runtime/engine/) | Prepare runtime configurations and invoke the selected engine. |

### From user intent to pipeline selection

The model receives the request, conversation history, agent instructions, and
registered tool descriptions. The instructions distinguish explanations,
planning requests, execution requests, and review of existing results. The
model chooses `pipeline_shell` directly or delegates a multi-step task to
`pipeline_specialist`, which uses the same tool.

For execution, the instructed sequence is:

```text
user request and conversation
    -> catalog: inspect descriptions, inputs, parameters, outputs, and engine
    -> files: discover uploaded, downloaded, or previously generated inputs
       (or example: stage explicitly requested demonstration data)
    -> model selects a pipeline, maps input slots, and supplies parameter overrides
    -> plan: validate and save the proposed job
    -> SDK approval for execution
    -> run: start the saved plan
    -> wait/status: inspect progress
    -> results: collect verified outputs and summarize them
```

The catalog contains manifest metadata; the model does not automatically read
all workflow source files or pipeline READMEs. Every manifest therefore gives
the agent a display name, a user-intent description, `use_when` and
`avoid_when` guidance, input and output summaries, limitations, examples, and
the execution boundary. Accurate input labels and descriptions help selection.
An explicit pipeline name and known input paths reduce ambiguity. The agent is
instructed to ask when missing information materially changes the result.

Pipeline selection is a model decision. Runtime checks establish that inputs
and settings satisfy the implemented execution contract; they do not prove
that the pipeline is scientifically appropriate for the user's question.
For example, `template_bio` describes an educational positional-comparison demo,
not a validated alignment or variant-calling workflow.

### The agent-pipeline command protocol

`agent-pipeline` is the project-defined command prefix accepted by
`pipeline_shell`. In the agent flow it is a string parsed by Python using
`shlex` and `argparse`, rather than a command evaluated by Bash. Each tool call
accepts exactly one command; arbitrary programs, pipes, redirects, and
workspace overrides are not supported.

```text
pipeline_shell receives "agent-pipeline catalog"
    -> execute_local_pipeline_command()
    -> parse_command() / dispatch()
    -> service.catalog()
    -> JSON result returned to the model
```

| Command | Purpose |
| --- | --- |
| `agent-pipeline catalog` | Discover manifest descriptions, input/output slots, parameters, and engines. |
| `agent-pipeline files` | List workspace-relative file paths, names, and sizes. |
| `agent-pipeline example --pipeline NAME` | Copy bundled `data/input/` files into the workspace for a requested demonstration. |
| `agent-pipeline plan --pipeline NAME --input SLOT=PATH` | Validate inputs and settings and save a plan without executing it. |
| `agent-pipeline run --plan-id ID` | Start the exact saved plan, subject to SDK approval. |
| `agent-pipeline jobs` | List jobs in the current session. |
| `agent-pipeline status --job-id ID` | Read the job state and log paths. |
| `agent-pipeline wait --job-id ID --seconds 5` | Wait for a bounded interval, at most 30 seconds. |
| `agent-pipeline results --job-id ID` | Verify outputs and return file records, metrics, table previews, and a ZIP bundle. |
| `agent-pipeline cancel --job-id ID` | Cancel a job and stop its local process group, subject to SDK approval. |

`plan` supports repeated `--input` and `--param NAME=VALUE` arguments, `--cores`,
`--timeout` in seconds, and `--dry-run` for Snakemake, Nextflow, or WDL. Shell
pipelines use `plan` for pre-execution validation and do not support dry runs.
The ShellTool action's `timeout_ms` is in milliseconds and is separate from the
pipeline deadline. Use returned plan and job IDs in subsequent calls.

Terminal users invoke the same service through its administrative CLI from the
project root:

```bash
python -m tools.runtime_tools.pipeline_runtime --workspace /path/to/workspace catalog
python -m tools.runtime_tools.pipeline_runtime --workspace /path/to/workspace example --pipeline template_shell
```

This module constructs the `agent-pipeline` prefix internally. SDK approval
controls apply to agent calls; this direct operator CLI executes requested
operations without that approval UI. Agent calls obtain the workspace from the
active session and cannot supply `--workspace`.

The OpenRouter transport adapter in `models/local_tools_model.py` presents local
shell and custom tools as function schemas to Chat Completions. It converts
returned calls into native SDK shell/custom items and translates their history
for later requests. Streaming calls are converted once their arguments are
complete. The SDK owns execution, approval interruptions, tracing, and saved
`RunState` resumption; the adapter only translates transport representations.

### Input files and their roles

The agent discovers files through `files`, workspace inspection, and prior tool
results. Uploads have unique filename prefixes under `uploads/`; downloaded
files and earlier outputs can also be selected when they are in the session
workspace. It must reuse actual returned paths. Bundled examples are staged
only for an explicitly requested example.

The catalog exposes named slots with `label`, `description`, `config_key`,
`required`, `accepts`, and `multiple`. The model maps selected files to these
slots, for example `--input reads=uploads/abc_reads.fastq`. The runtime checks
required slots, file existence, accepted filename suffixes, cardinality, and
workspace confinement. It returns `needs_input` with `requested_inputs` when a
required slot is missing. Once the plan is saved, it records input hashes and
verifies them again before execution and while staging copies into the job.

**There is no built-in R1/R2 or metadata-role classifier.** The model can infer
roles from names such as `sample_R1.fastq`, user-provided mappings, and manifest
descriptions. File inspection can supply text previews and table columns, but
it does not provide a paired-read validator. A `.tsv` suffix establishes neither
metadata semantics nor the presence of the columns a workflow needs.

`template_shell` declares `reads` and `metadata` slots. `template_bio` declares
`reads`, `reference`, and `metadata`; neither template declares a paired-end interface. A workflow designed for two mates can
expose the following slots, provided its implementation consumes both paths:

```yaml
inputs:
  reads_r1:
    label: Read 1 FASTQ
    description: First mate file for the selected sample.
    config_key: reads_r1_path
    required: true
    accepts: [.fastq, .fq, .fastq.gz, .fq.gz]
  reads_r2:
    label: Read 2 FASTQ
    description: Second mate file for the same sample.
    config_key: reads_r2_path
    required: true
    accepts: [.fastq, .fq, .fastq.gz, .fq.gz]
  metadata:
    label: Sample metadata
    description: TSV or CSV table with a sample_id column.
    config_key: metadata_path
    required: true
    accepts: [.tsv, .csv]
```

These declarations describe the interface; the workflow must implement gzip
reading, pair consistency checks, metadata-column checks, and other content
validation it requires. The runtime does not interpret proposed fields such as
`role`, `mate`, or `required_columns`. In the bundled shell template, metadata columns and sequence record structure are
checked by `run.sh` during execution.

For a slot whose workflow accepts several files, declare `multiple: true` and
pass a JSON array:

```text
--input 'reads=["uploads/a.fastq","uploads/b.fastq"]'
```

An array does not establish pairing or resolve uncertain assignments. When
several files could fill the same role, the agent needs evidence or a user
mapping before it can choose reliably.

### Parameters and runtime configuration

`runner.yaml` defines ordinary parameter defaults under `params`. Optional
native configuration can be declared with `config` (or `config_file`); a
`config.yaml` in the pipeline directory is also loaded when present. Precedence
is native configuration, then manifest `defaults`, then manifest `params`,
followed by explicit input and parameter overrides for the job. Declared native
files must exist.

The model can translate a request such as "minimum length 8" into
`--param min_length=8`; omitted values retain their configured defaults. The
runtime accepts declared parameter names and performs basic value coercion
using configured defaults. This is not a complete parameter-schema validator;
workflows must check types, scientific ranges, and relationships, such as a
fraction being between zero and one.

For top-level or engine-specific config fields, manifests can use
`param_overrides` to map parameter names to `config_key` or `wdl_key`. When that
mapping is present it defines the allowed override names. A missing parameter
marked `required: true` returns `needs_parameters`. Manifests can also declare
`preset_param` and `presets` for named bundles of settings.

For shell jobs the engine writes `config.runtime.yaml` and calls
`bash <entrypoint> <runtime-config-path>`. Inputs are mapped through their
`config_key`; ordinary parameters remain under `config["params"]`; declared
output keys contain paths in the job's output directory. The workflow reads
this generated configuration instead of hardcoding session paths.

### Plans, approvals, and jobs

A valid plan stores the selected pipeline, input paths and hashes, supplied
parameter overrides, engine, output declarations, timeout, resource limits,
and a fingerprint of the pipeline definition. Planning does not run the
workflow or perform every content check that the workflow will perform.
Changed input files or definitions require a new plan before execution.

The SDK pauses real `run` and `cancel` calls for approval. Planning, reading
status, and collecting outputs do not require approval; supported engine dry
runs also skip execution approval. Approved execution starts a detached worker.
The worker copies and verifies inputs, invokes the engine, checks required
outputs, and records a terminal state.

```text
planned -> queued -> running -> succeeded / failed / timed_out / interrupted
    cancellation can end an unfinished job as cancelled
```

An already-started plan returns its existing state instead of launching a
second worker. Jobs can continue after the originating HTTP request ends. If a
worker disappears, status becomes `interrupted`; the runtime does not
restart jobs after a host reboot or automatically retry failed jobs. For long
jobs the agent returns the job ID and current status so later requests can
inspect them. It does not promise unsolicited completion messages.

The local worker enforces a deadline and an inherited per-process address-space
limit; core settings are passed to supported engines and thread environments.
Manifest `resources.max_cores` and `resources.max_memory_mb` bound resources,
and `timeout` bounds the requested deadline. These are not aggregate cgroup
quotas. The local backend runs trusted registered code on the host OS.

### Output files and result collection

Each output declaration specifies a `config_key` or an engine output mapping,
a relative filename (`default` or `target`), a `kind`, and optionally
`required: false`. Outputs are required by default. The runtime allocates paths
under the job's `outputs/` directory and verifies the declared files after
execution. A normal run missing a required output fails; optional outputs may
be absent.

```text
runtime/sessions/<session-id>/
├── uploads/
├── .pipeline/jobs.sqlite3     # authoritative job state
└── runs/<job-id>/
    ├── job.json
    ├── plan.json
    ├── inputs.json
    ├── inputs/               # verified input copies
    ├── stdout.log
    ├── stderr.log
    ├── outputs/              # runtime configuration and workflow outputs
    ├── output-manifest.json  # paths, kinds, sizes, and hashes
    └── results.zip           # created by results
```

`results` requires `succeeded` and rechecks output hashes, file existence, and
confinement to the job directory. It returns file records, small JSON metrics,
and bounded CSV/TSV previews (10 rows by default, configurable up to 50 with
`--max-table-rows`). It builds `results.zip` with declared outputs, logs, the
plan, and the output manifest. Reviewing outputs never launches another run.

### Adding a pipeline

A new definition is discovered on the next `catalog` call when its folder and
`runner.yaml` are present on the running server. For an existing engine, no
changes to the tool registry or command parser are needed. Discovery does not
install dependencies or prove that the workflow executes successfully.

1. Create a uniquely named folder under `tools/runtime_tools/pipelines/`. Use
   letters, numbers, underscores, hyphens, or dots, beginning with a letter or
   number. Keep the manifest name consistent with the folder name.
2. Declare a clear user-intent description, `display_name`, `use_when`,
   `avoid_when`, input and output summaries, limitations, engine entrypoint,
   input slots, parameter defaults, output files, timeout, and resource limits
   in `runner.yaml`.
3. Implement the workflow against the generated configuration. Validate input
   contents and parameter ranges, write the declared outputs, and fail with an
   informative error when a requirement is not met.
4. Declare `execution.boundary: container`. Keep workflow tools, databases,
   and engine dependencies inside the pipeline container; do not add them to
   the Pipeline2Agent environment. Add a README describing the bundle and
   optional `data/input/` examples.
5. Verify discovery, then plan and execute the new workflow with representative
   inputs and collect its results. Check missing or malformed inputs as well as
   successful execution.

A shell pipeline can follow this layout:

```text
tools/runtime_tools/pipelines/my_pipeline/
├── runner.yaml
├── run.sh
├── workflow.py             # if run.sh invokes Python
├── README.md
└── data/input/              # optional demonstration files
```

Example manifest (the analysis itself must be implemented in the workflow):

```yaml
name: my_pipeline
display_name: Sequence length summary
description: Calculate a length summary for a single FASTQ file.
use_when:
  - the user wants a quick length summary for FASTQ reads
avoid_when:
  - the user needs alignment or variant calling
input_summary: One FASTQ file.
output_summary: A report and metrics JSON file.
limitations: This example does not perform alignment.
execution:
  boundary: container
  dependency_scope: pipeline
engine: shell
entrypoint: run.sh
timeout: 120
resources:
  max_cores: 1
  max_memory_mb: 1024
params:
  min_length: 10
inputs:
  reads:
    label: FASTQ reads
    description: One uncompressed FASTQ file.
    config_key: input_path
    required: true
    accepts: [.fastq, .fq]
outputs:
  report:
    config_key: report_path
    default: report.md
    kind: report
  metrics:
    config_key: metrics_path
    default: metrics.json
    kind: metrics
```

A Bash entrypoint can pass the configuration to Python:

```bash
#!/usr/bin/env bash
set -euo pipefail
config_path="${1:?Usage: bash run.sh CONFIG_YAML}"
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "${script_dir}/workflow.py" "${config_path}"
```

The shell entrypoint loads the generated YAML, reads `input_path`,
`metadata_path`, and `params.normalize_mode`, and writes the four declared output
paths. Choose accepted suffixes and output kinds that the implementation actually
supports. The [shell metadata template](../tools/runtime_tools/pipelines/template_shell/)
provides a complete minimal implementation.

| Engine | Manifest entrypoint | Runtime requirements and output mapping |
| --- | --- | --- |
| `shell` | `entrypoint: run.sh` | Bash and programs invoked by the script; write configured output paths. |
| `snakemake` | `snakefile: Snakefile` | Snakemake and rule dependencies; consume the generated config. |
| `nextflow` | `workflow: main.nf`, optional `nextflow_config` | Nextflow and its Java runtime; consume the generated params file and map published names with `nextflow_output`. |
| `wdl` | `workflow: workflow.wdl`, optional `inputs_json` | miniwdl and its configured container runtime; use `wdl_key` for inputs and `wdl_output` for outputs. |

The local WDL protocol uses miniwdl. Optional `options_json` produces an
`options.runtime.json` record; miniwdl does not consume that file. Shell dry
runs are unsupported; Snakemake uses its dry-run mode, Nextflow uses preview,
and WDL uses `miniwdl check`. Adding a different engine requires runtime code
changes in addition to a manifest.

For a runnable demonstration of the full protocol, ask Pipeline2Agent:

> Use the template_shell example data, run it, and summarize the results.

The agent stages the bundled synthetic data, plans, requests approval, runs,
and collects `normalized.txt`, `subtypes.tsv`, `metrics.json`, and `report.md`.
The shell template assigns all three bundled sequence IDs. To exercise your own
pipeline, request its name and supply its declared inputs, or explicitly ask
for its bundled examples. Use the [offline checks](#testing) for shared runtime
regressions; they do not replace an execution test of the new workflow.

## Interfaces

All interfaces call the same runtime:

```python
from harness import run_agent

result = run_agent("Analyze this FASTA sequence", session_id="chat-1")
print(result["answer"])
```

The synchronous wrapper is used by CLI, HTTP, and ordinary Python callers. Use
`async_run_agent` in an application that already owns an asyncio event loop.

The web workspace is a thin adapter over the SDK sandbox session. It exposes
one session-scoped workspace resource for listing, upload, read/download, and
delete operations; it does not create a second file registry or agent runtime.

The HTTP contract is deliberately path-based and workspace-root-relative:

| Request | Purpose |
| --- | --- |
| `GET /workspace?session_id=...` | List every regular file in the session workspace. |
| `POST /workspace/files` | Upload multipart files into `uploads/`. |
| `GET /workspace/file?session_id=...&path=...` | Read or download one workspace file. |
| `DELETE /workspace/files/<path>?session_id=...` | Delete one workspace file. |

Session history uses the SDK session contract:

| Request | Purpose |
| --- | --- |
| `GET /sessions` | List application session metadata and message counts. |
| `GET /sessions/<session-id>/messages` | Read conversation messages from the SDK `SQLiteSession`. |

The browser receives file metadata from the sandbox listing and uses the
workspace-relative path for later operations. There are no upload-only APIs,
generated file IDs, or host-path reads in the web contract.

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

For OpenRouter traffic, set `AGENT_PROXY` in the terminal before starting
the server:

```bash
conda activate openaisdk
export AGENT_PROXY=socks5h://127.0.0.1:10801
python -B -m interfaces.web --host 0.0.0.0 --port 8000
```

`AGENT_PROXY` takes priority over `ALL_PROXY`/`all_proxy`; neither setting
requires clearing `HTTP_PROXY` or `HTTPS_PROXY` for these clients. Set
`AGENT_DISABLE_PROXY=1` to force direct OpenRouter connections regardless
of proxy settings. Unset that variable before switching back to a proxy.
Database and pipeline clients retain their own proxy settings.

Choose a configured model with `AGENT_MODEL_KEY`. Set
`AGENT_MAX_TURNS` to bound the SDK run turns. Set
`AGENT_SESSION_DB` for the conversation database and `AGENT_SESSIONS_DIR`
for session workspaces, including their per-run directories.

## Testing

Offline harness tests use `agents.testing.ScriptedModel` and mock HTTP
transports to verify tool execution, guardrails, SDK spans, sessions,
workspace files, and pipeline results without an API key. Provider and reporting
checks cover client ownership, nested approval resumption, concurrent opinions,
synthesis fallback, and embedding order. Live tests should use a temporary
OpenRouter key and a model that supports Chat Completions and tool calls.

Run the relevant offline checks from the project root:

```bash
python evals/smoke_architecture.py
python evals/smoke_local_transport.py
python evals/smoke_model_provider.py
python evals/smoke_reporting.py
python evals/smoke_approvals.py
python evals/smoke_session_artifacts.py
python evals/smoke_session_history.py
python evals/smoke_pipeline_config.py
python evals/smoke_pipeline_runtime.py
python evals/smoke_template_bio.py
python evals/smoke_nextflow_runner.py
```

The Nextflow smoke check uses a test double. These checks do not establish that
external engines or a newly added pipeline work in the deployment environment;
exercise those workflows with representative inputs. Live provider checks use
`evals/smoke_openrouter.py` with a configured API key.
