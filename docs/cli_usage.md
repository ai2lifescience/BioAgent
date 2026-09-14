# BioAgent CLI

Run the command line interface with:

```bash
conda activate openaisdk
export OPENROUTER_API_KEY="..."
python -m interfaces.cli "<request>"
```

To use a SOCKS proxy for OpenRouter requests, set this once in the same terminal:

```bash
export BIOAGENT_PROXY=socks5h://127.0.0.1:10801
```

`ALL_PROXY` is not required when `BIOAGENT_PROXY` is set, and there is no need
to unset other proxy variables for OpenRouter. Use `BIOAGENT_DISABLE_PROXY=1`
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
--max-skill-steps N      Compatibility name; limits SDK turns (default: 8)
--json                   Print the complete structured result as JSON
--verbose                Include progress messages on stderr
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

Each row is a function tool generated from the workflow registry. Workflows
use the shared `WorkflowContext` to call their deterministic actions.

| Workflow | Main tool or actions |
| --- | --- |
| `example_skill` | `echo` |
| `pipeline_runner` | `pipeline_runner` |
| `ncbi_retrieval` | `ncbi_fetch` |
| `bio_database_search` | database search actions |
| `pdb_download` | `pdb_download` |
| `sequence_analysis` | `sequence_analyze` |
| `genome_map` | `genome_map` |
| `protein_structure_analysis` | `protein_structure_analyze` |
| `blast_search` | `blast_search` |
| `file_inspection` | `file_inspect` |
| `species_report` | literature retrieval, RAG, and report actions |

The SDK chooses tools from their JSON schemas. Workflows remain deterministic
and do not make model calls themselves.

## Pipeline requests

Pipeline execution is restricted to approved folders under `pipelines/`. Each
folder contains a `runner.yaml`, a base config, and an entrypoint such as
`run.sh`:

```text
pipelines/<pipeline_name>/
  runner.yaml
  config.yaml
  run.sh
```

For example:

```bash
python -m interfaces.cli "Run the shell pipeline with pipeline_name: generic_shell."
```

Runtime configs and logs are written below the session artifact directory. An
uploaded input path is recorded in the run manifest; arbitrary script paths
are not accepted.

## Structured output and sessions

`--json` exposes the same structure returned by `harness.run_bioagent`:

```json
{
  "answer": "...",
  "session_id": "demo",
  "evidence": {"items": []},
  "verification": {"status": "ok"},
  "trace": {"events": []},
  "artifacts": [],
  "runtime": "agents_sdk"
}
```

Conversation messages are stored by the SDK `SQLiteSession` in
`runtime/agent_sessions.sqlite3`. Application metadata and artifact manifests
are stored under `runtime/session_metadata/`. Use the API or Python interface
to list and delete sessions; deletion clears both stores.

## Offline checks

The repository smoke checks use a scripted Agents SDK model and do not require
network access:

```bash
python evals/smoke_architecture.py
python evals/smoke_session_artifacts.py
python evals/smoke_pipeline_results.py
```

The OpenRouter check runs only when `OPENROUTER_API_KEY` is present:

```bash
python evals/smoke_openrouter.py
```
