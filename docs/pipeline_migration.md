# Local pipeline runtime

BioAgent runs registered shell, Snakemake, Nextflow, and miniwdl workflows
through one Agents SDK `ShellTool`, named `pipeline_shell`. The local executor
accepts the `bioagent-pipeline` command protocol. It parses arguments without
evaluating them in Bash. Bash expressions, pipes, redirects, arbitrary programs,
and workspace overrides are not accepted.

The root agent can use this tool for a single operation. For a multi-step
workflow, `pipeline_specialist` uses the same local tool via `Agent.as_tool()`.
The retired function-tool wrappers and modules have been removed. Engine
adapters now live under `pipeline_runtime/engine`.

## SDK and provider integration

`tools/runtime_tools/pipeline_tool.py` implements `ShellCommandRequest` to
`ShellResult`, with conditional SDK approval for execution and cancellation.
Read operations and engine dry runs do not require approval. The SDK owns
interruptions, `RunState`, approval resume, tracing, and tool-call history.

The application uses OpenRouter Chat Completions. The SDK's unmodified
Chat Completions converter rejects native ShellTools.
`models/local_shell.py` translates the shell schema and history on that
transport, then returns native shell-call items to the SDK Runner. Thus
execution and approvals still use the SDK's local ShellTool lifecycle.
Injected Responses models can use the native tool directly.

Official reference: [Agents SDK tools](https://openai.github.io/openai-agents-python/tools/).

## Commands

Issue exactly one command per shell call. Input paths are relative to the
current session workspace.

| Command | Purpose |
| --- | --- |
| `bioagent-pipeline catalog` | Inspect registered manifests and input/output slots |
| `bioagent-pipeline files` | Discover session files |
| `bioagent-pipeline example --pipeline NAME` | Stage explicitly requested sample data |
| `bioagent-pipeline plan --pipeline NAME --input SLOT=PATH` | Validate and save a plan |
| `bioagent-pipeline run --plan-id ID` | Approve and launch that plan |
| `bioagent-pipeline jobs` | List jobs in this session |
| `bioagent-pipeline status --job-id ID` | Read state and log paths |
| `bioagent-pipeline wait --job-id ID --seconds 5` | Wait for at most 30 seconds |
| `bioagent-pipeline results --job-id ID` | Verify outputs, preview tables, and build a ZIP |
| `bioagent-pipeline cancel --job-id ID` | Approve cancellation of the local process group |

Planning also accepts repeated `--input` and `--param NAME=VALUE`,
`--cores`, `--timeout` (seconds), and `--dry-run` for engine validation.
Values may be JSON, including arrays of input paths. Quote tokens containing
spaces. The shell action's `timeout_ms` is distinct from the job deadline:
long pipelines use the persisted job timeout rather than keeping a tool call
open. For wait commands, the executor also checks the shell action budget.

A standalone administrative CLI is available:

```bash
python -m tools.runtime_tools.pipeline_runtime --workspace /path/to/workspace catalog
python -m tools.runtime_tools.pipeline_runtime --workspace /path/to/workspace example --pipeline example_sequence_qc
```

Subsequent CLI calls accept the same subcommands. The CLI is a local operator
interface; SDK approval controls apply to agent calls.

## Manifests and planning

`runner.yaml` is the primary manifest. It declares the engine, entrypoint,
input slots, output paths, parameters, and timeout. Put ordinary engine
defaults under `params` (or under `defaults` for nested native settings).
Optional native files remain available when a workflow needs them: declare a
YAML base with `config`, or WDL inputs/options files with `inputs_json` and
`options_json`. The loader merges native file values, `defaults`, and then
manifest `params`; an explicitly named missing file is an error. A legacy
`config.yaml` is still discovered when present, so existing external pipelines
can migrate incrementally. Optional `resources.max_cores` and
`resources.max_memory_mb` limit requested resources.

The smallest shell manifest is therefore:

```yaml
name: my_pipeline
engine: shell
entrypoint: run.sh
params:
  mode: example
inputs:
  reads: {config_key: input_path, required: true, accepts: [.fastq]}
outputs:
  report: {config_key: report_path, default: report.md, kind: report}
```

A plan records selected inputs and SHA-256 hashes, supplied parameters, engine,
output declarations, resource limits, and a fingerprint of pipeline definitions.
Required inputs must be selected explicitly; sample data is never substituted
for missing user data. Input and definition hashes are checked again before
execution. Workers copy inputs to the job directory and verify those copies.
Changed inputs or definitions require a new plan.

## Durable jobs

```text
runtime/sessions/<session-id>/
├── .pipeline/jobs.sqlite3     # authoritative private job state
└── runs/<job-id>/
    ├── job.json              # readable state snapshot
    ├── plan.json
    ├── inputs.json
    ├── inputs/               # verified input copies
    ├── stdout.log
    ├── stderr.log
    ├── outputs/              # engine files and declared outputs
    ├── output-manifest.json
    └── results.zip           # created by results
```

State progresses from `planned` to `queued` to `running`, then
`succeeded`, `failed`, `cancelled`, `timed_out`, or `interrupted`.
Approval state belongs to the SDK's saved RunState, separately from job state.

SQLite serializes launches. Running the same plan again returns the existing
job instead of creating another process. A detached local worker continues
after the HTTP request or agent process exits. A later process can inspect
the same database and files. If the worker disappears, status reports
`interrupted`; it does not restart a non-resumable pipeline automatically.
This is process persistence, not recovery across a host reboot.

Cancellation terminates the local process group. A worker deadline also
terminates the group. Resource limits include inherited per-process address
space limits and engine/thread core settings. These are not aggregate cgroup
CPU/memory quotas. The Unix-local backend runs trusted registered definitions;
it is not an OS security sandbox or a network isolation boundary. Use a
container backend for untrusted pipeline code.

Results require a succeeded job and recheck output hashes and confinement.
Collection never executes the pipeline. Logs and the plan are included in the
result archive. Table previews are bounded.

## Example

`tools/runtime_tools/pipelines/example_sequence_qc/` contains a Bash entrypoint,
Python workflow, one manifest, four artificial FASTQ records, and a metadata TSV.

Ask BioAgent:

> Use the example_sequence_qc example data, run it, and summarize the results.

The agent stages data, selects the returned paths, plans, requests approval,
starts the worker, waits briefly, and collects outputs. With default parameters,
4 reads / 28 bases become 2 reads / 16 retained bases. Outputs are
`filtered.fastq`, `assignments.tsv`, `metrics.json`, and `report.md`.

## Verification and compatibility

Relevant offline checks:

```bash
python evals/smoke_architecture.py
python evals/smoke_local_transport.py
python evals/smoke_approvals.py
python evals/smoke_pipeline_config.py
python evals/smoke_pipeline_runtime.py
python evals/smoke_generic_bio.py
python evals/smoke_nextflow_runner.py
```

The sample shell workflow runs without external bioinformatics programs.
Snakemake, Nextflow/Java, and miniwdl plus its configured container runtime
must be installed to execute their respective workflows. The Nextflow smoke
uses a test double. Remote Cromwell workflows remain in the legacy Python
backend and are rejected by this local protocol.

Internal engine adapters remain under `pipeline_runtime/engine`; pipeline
definitions and optional native workflow files live under `pipelines/`.
