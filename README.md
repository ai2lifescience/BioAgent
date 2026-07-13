# BioAgent

BioAgent is a layered bioinformatics agent with deterministic biological tools,
workflow skills, model-guided skill selection, retrieval support, evidence
collection, a CLI, and a chat-style web UI.

For the full system design, see [docs/architecture.md](docs/architecture.md).
For command-line examples, see [docs/cli_usage.md](docs/cli_usage.md).
For planned architecture upgrades, see [docs/todo.md](docs/todo.md).

## Architecture

```text
User / App
  -> interfaces/                 CLI, web UI/API, Python API, notebook helpers
  -> agent_core/orchestrator.py   request coordination, planning, skill loop
     -> memory.py                 in-memory session state and locking
     -> artifacts.py              artifact rules, workspaces, and uploads
     -> trace.py                  structured trace events
  -> agent_core/router.py         ordered dispatch over route_rules/
     -> route_rules/              deterministic route matchers
  -> agent_core/planner.py        deterministic executable plan templates
  -> execution/skill_executor.py  skill workflow execution
  -> execution/tool_executor.py   concrete tool execution
     -> registries/skill_registry.py
     -> skills/                   workflows, rules, SKILL.md files
     -> registries/tool_registry.py
     -> tools/                    concrete actions with execution metadata
     -> bio_data/                 public bio API adapters
     -> rag/                      Chroma retrieval and RAG answering
  -> agent_core/evidence.py       IDs, URLs, citations, query terms, files
  -> agent_core/verifier.py       missing evidence and biosafety warnings
  -> agent_core/orchestrator.py   final result assembly
  -> User / App
```

The LLM chooses from registered skills when deterministic routing is not enough.
Python controls skill execution through `registries/skill_registry.py`; skills
call concrete tools through `execution/tool_executor.py`. Every run returns
`answer`, `session_id`, `messages`, `evidence`, `verification`, `route`,
`plan`, and `trace`.

## CLI

```bash
python -m interfaces.cli "Please test skill calling by running the example skill with message hello and tag smoke."
```

## Web UI / API

```bash
python -m interfaces.web --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000` for the chat-style browser UI.
The UI files live in `web_ui/`; `interfaces/web.py` only serves HTTP routes.
Protein structure analysis results include a collapsible 3D viewer for local `.cif`,
`.mmcif`, and `.pdb` artifacts.
The Stop button stops browser waiting, but the current backend does not forcibly
kill in-flight LLM calls or pipeline subprocesses.

```bash
curl -X POST http://127.0.0.1:8000/run \
  -H 'Content-Type: application/json' \
  -d '{"request": "Analyze PhiX174 segment sequence GAGTTTTATCGCTTCCATGACGCAGAAGTTAACACTTTCGGATATTTCTGATGAGTCGAAAAATTATCTT"}'
```

## Notebook / Python

```python
from interfaces.notebook import run_bioagent

result = run_bioagent("Analyze PhiX174 segment sequence GAGTTTTATCGCTTCCATGACGCAGAAGTTAACACTTTCGGATATTTCTGATGAGTCGAAAAATTATCTT")
result["answer"]
```

## Direct Deterministic Examples

```bash
python -m interfaces.cli "Analyze PhiX174 segment sequence GAGTTTTATCGCTTCCATGACGCAGAAGTTAACACTTTCGGATATTTCTGATGAGTCGAAAAATTATCTT"
python -m interfaces.cli "Search UniProt for BRCA1 human"
python -m interfaces.cli "Download PDB structure 1A3N as cif"
python -m interfaces.cli "Analyze protein structure file runtime/sessions/demo/artifacts/structures/1A3N.cif"
python -m interfaces.cli "Inspect file data/ncbi_downloads_phix174/phix174_A.fasta"
```

LLM-backed requests require:

```bash
export OPENROUTER_API_KEY="..."
```

Simple NCBI and example-skill requests can route directly through Python before
using the model.
