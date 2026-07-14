# BioAgent

BioAgent is a bioinformatics agent for biological question answering, public
database retrieval, sequence and structure analysis, evidence-backed reporting,
file inspection, and pipeline execution. It combines deterministic tools with
reusable skills and model-guided skill selection behind a chat-style web UI,
CLI, API, and Python interface.

## What BioAgent Does

![BioAgent functions](docs/images/system_functions.png)

BioAgent can:

- answer biology questions and explain biological concepts;
- retrieve records from NCBI, PubMed, UniProt, and PDB;
- analyze nucleotide sequences, genome maps, and protein structures;
- inspect FASTA, CSV, TSV, JSON, Markdown, and text files;
- create species reports with sources, citations, and generated files;
- run Shell, Snakemake, and WDL pipelines; and
- retain uploads and generated artifacts within a chat session.

## Quick Start

### 1. Get The Project

```bash
git clone https://github.com/ai2lifescience/BioAgent.git
cd BioAgent
```

### 2. Create An Environment

```bash
conda create -n bioagent python=3.12 -y
conda activate bioagent
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 3. Configure A Model

The default model uses OpenRouter. Set an API key before using LLM-backed chat,
planning, or report generation:

On Linux Bash:

```bash
export OPENROUTER_API_KEY="your-openrouter-api-key"
```


Replace the placeholder with your real key. The variable is available to
BioAgent commands started from the current terminal session.

Deterministic operations such as sequence analysis and some public database
requests can run without an LLM key.

### 4. Start The Web UI

```bash
python -B -m interfaces.web --host 127.0.0.1 --port 8000
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000) in a browser. Stop the
server with `Ctrl+C`.

![BioAgent web interface](docs/images/web_ui.png)

### 5. Use BioAgent

Select a model, enter a request in the message box, and send it. Example
requests:

```text
What is GC content?
```

```text
Analyze PhiX174 segment sequence GAGTTTTATCGCTTCCATGACGCAGAAGTTAACACTTTCGGATATTTCTGATGAGTCGAAAAATTATCTT
```

```text
Search UniProt for BRCA1 human
```

```text
Download PDB structure 1A3N as cif
```

```text
Run pipeline with pipeline_name: generic_snakemake
```

Use the Uploads panel for local input files. BioAgent stores uploads and outputs
under the active session so later requests in the same chat can reuse them.

To allow access from another computer on a trusted local network, run:

```bash
python -B -m interfaces.web --host 0.0.0.0 --port 8000
```

Then open `http://<SERVER_LAN_IP>:8000` from the other computer.

## Architecture

![BioAgent system architecture](docs/images/system_architecture.png)

```text
User / App
  -> Interface Layer             CLI, web UI/API, Python, notebook
  -> Agent Orchestrator          session coordination and execution loop
     -> Memory / Trace           session state, locks, and runtime events
  -> Intent Router               deterministic route rules
  -> Planner                     executable plan templates
  -> Skill Executor              reusable biological workflows
  -> Tool Executor               concrete validated actions
     -> Bio APIs                 NCBI, PubMed, UniProt, PDB
     -> Bio Tools                sequence, BLAST, structure, genome map
     -> RAG                      retrieval and evidence-backed answers
     -> Pipeline Runner          Shell, Snakemake, WDL
     -> File I/O                 uploads, inspection, and reports
  -> Evidence Collector          sources, identifiers, citations, files
  -> Verifier                    result and biosafety checks
  -> Final Answer
```

The router selects known workflows directly. When deterministic routing is not
enough, the LLM may choose from registered skills. Skills call registered tools
through the central tool executor, while the orchestrator records session state,
evidence, verification results, artifacts, and runtime trace events.

## Other Interfaces

### CLI

```bash
python -m interfaces.cli "Search UniProt for BRCA1 human"
```

### HTTP API

With the web server running:

```bash
curl -X POST http://127.0.0.1:8000/run \
  -H 'Content-Type: application/json' \
  -d '{"request": "What is GC content?"}'
```

### Python

```python
from interfaces.notebook import run_bioagent

result = run_bioagent("Analyze PhiX174")
print(result["answer"])
```

## Pipeline Notes

- Shell pipelines use the local shell environment.
- Snakemake pipelines require the `snakemake` package included in
  `requirements.txt`.
- WDL pipelines use `miniwdl` and require a working Docker daemon plus access to
  the task container images.
- Pipeline inputs should be supplied explicitly through the request or uploaded
  through the web UI.

## Documentation

- [System architecture](docs/architecture.md)
- [Web UI usage and examples](docs/web_usage.md)
- [CLI usage and examples](docs/cli_usage.md)
- [Team development workflow](docs/dev_workflow.md)
- [Planned improvements](docs/todo.md)
