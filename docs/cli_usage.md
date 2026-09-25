# Pipeline2Agent CLI

Run the command line interface with:

```bash
conda activate openaisdk
export OPENROUTER_API_KEY="..."
python -m interfaces.cli "<request>"
```

To use a SOCKS proxy for OpenRouter requests, set this once in the same terminal:

```bash
export AGENT_PROXY=socks5h://127.0.0.1:10801
```

`ALL_PROXY` is not required when `AGENT_PROXY` is set, and there is no need
to unset other proxy variables for OpenRouter. Use `AGENT_DISABLE_PROXY=1`
to force a direct OpenRouter connection; unset it before switching back to a
proxy.

The request is sent to one OpenAI Agents SDK `Agent` through `Runner`. The
agent can call registered biological workflows exposed as typed function tools.
Tool results are collected as evidence, checked by guardrails, and retained in
the SDK session when a `--session-id` is supplied.

## Options

```text
--model-key KEY          Model key from models/config.py (default: configured default)
--session-id ID          Continue a persistent SDK conversation
--max-turns N            Maximum SDK turns (default: 20; configurable through the environment)
--json                   Print the complete structured result as JSON
--verbose                Include progress messages on stderr
--approve ID             Approve a pending pipeline tool call (with --session-id)
--reject ID              Reject a pending pipeline tool call (with --session-id)
```

Examples:

```bash
python -m interfaces.cli "help"
python -m interfaces.cli --model-key gpt-oss "What is GC content?"
python -m interfaces.cli --session-id demo "Analyze the sequence ACGT"
python -m interfaces.cli --json "Fetch a trusted summary of PhiX174"
```

All model-backed requests need `OPENROUTER_API_KEY`. The key is read from the
environment and is never written to session files or output. Model IDs are
native OpenRouter IDs; configure aliases in `models/config.py` or select a
different key with `--model-key`.

## Registered workflows

Biological workflows are SDK `FunctionTool` objects exported by
`tools/function_tools`. Pipeline operations use the local `pipeline_shell`
ShellTool exported by `tools/infrastructure/sdk_adapters`.

| Workflow | Main tool or actions |
| --- | --- |
| `pipeline_shell` | `agent-pipeline plan/run/status/wait/results/cancel` |
| `ncbi_retrieval` | `ncbi_fetch` |
| `database_lookup` | database search actions |
| `pdb_download` | `pdb_download` |
| `alphafold_download` | Download an AlphaFold structure file |
| `sequence_stats` | Sequence metrics |
| `sequence_find_orfs` | ORF feature detection |
| `sequence_translate` | Translation and FASTA output |
| `genome_read_features` | Read GenBank/GFF features |
| `genome_render_map` | Prepare an interactive IGV.js genome browser artifact |
| `structure_inspect` | Structure measurements |
| `blast_search` | `blast_search` |
| `file_inspection` | `file_inspect` |
| `workspace_search` | Search uploaded text and PDF files |
| `document_read` | Read selectable PDF pages |
| `table_profile` | Profile a bounded table |
| `table_group` | Group a bounded table |
| `table_plot` | Plot one numeric table column |
| `pubmed_search` / `web_search` | Collect bounded evidence |
| `evidence_retrieve` | Rank saved evidence |
| `report_review` / `report_synthesize` / `report_write` | Review evidence, draft, and save a cited report |
| `code_inspection` | Inspect or search workspace code |
| `code_edit` / `code_test` | Bounded direct workspace changes and tests |
The model selects tools from their descriptions and schemas. Atomic capabilities
compose by passing workspace-relative artifact paths. `report_review` and
`report_synthesize` are Agents SDK nested-agent tools; deterministic calculations
remain in their owning typed FunctionTool modules.
The root and specialist agents share the run's SDK model provider. See the
[model architecture](architecture.md#models-and-provider-ownership) for model
resolution, client ownership, and reporting behavior.

Pipeline execution and cancellation pause for SDK approval. Agent requests submitted
through the web API are durable queued runs and expose status/events by run ID. The JSON result's
`approvals` list includes an `approval_id`; approve or reject it with the CLI
options above, or POST the same `session_id`, `approval_id`, and boolean
`approved` to `/approve`. Discovery, planning, status, result collection, and
supported engine dry runs do not require execution approval.

## Pipeline requests

The [pipeline architecture reference](architecture.md#pipeline-runtime) covers
the command protocol, input roles, parameters, outputs, and adding workflows.

Pipeline execution is restricted to approved folders under `tools/runtime_tools/pipelines/`. Each
folder contains a `runner.yaml` and an entrypoint such as `run.sh`. Native
workflow files are optional and remain available when an engine needs them:

```text
tools/runtime_tools/pipelines/<pipeline_name>/
  runner.yaml
  run.sh
  # optional: config.yaml, nextflow.config, inputs.json, options.json
```

### Examples

1. Discover the registered pipelines before choosing one:

   ```bash
   python -m interfaces.cli "Use pipeline_shell to list the available pipelines."
   ```

2. Run the bundled demonstration and collect its results:

   ```bash
   python -m interfaces.cli "Run the template_shell example and summarize its assignments and metrics."
   ```

   The agent stages the example inputs, creates a validated plan, requests
   approval for execution, waits for the job, and collects the output bundle.

3. Run a pipeline with files uploaded to the current session:

   ```bash
   python -m interfaces.cli --session-id demo \
     "Use my uploaded reads.fastq and metadata.tsv as the reads and metadata inputs for template_shell, run it, and return the results."
   ```

   The agent discovers workspace-relative file paths and passes them explicitly
   to `agent-pipeline plan`; it does not guess paths or substitute example
   data for missing user inputs.

Runtime configs and logs are written below the session workspace directory. An
uploaded input path is recorded in the run manifest; arbitrary script paths
are not accepted.

## Structured output and sessions

`--json` exposes the same structure returned by `harness.run_agent`:

```json
{
  "answer": "...",
  "session_id": "demo",
  "evidence": {"items": []},
  "status": "ok",
  "trace": [],
  "files": [],
  "runtime": "agents_sdk"
}
```

Conversation messages are stored by the SDK `SQLiteSession` in
`runtime/agent_sessions.sqlite3`. Session metadata is stored under
`runtime/session_metadata/`; files are managed by the SDK sandbox workspace.

## Offline checks

The repository smoke checks use scripted Agents SDK models or mock HTTP
transports and do not require network access:

```bash
python evals/smoke_architecture.py
python evals/smoke_model_provider.py
python evals/smoke_reporting.py
python evals/smoke_session_artifacts.py
python evals/smoke_pipeline_runtime.py
```

The OpenRouter check runs only when `OPENROUTER_API_KEY` is present:

```bash
python evals/smoke_openrouter.py
```
