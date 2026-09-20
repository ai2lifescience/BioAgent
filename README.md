# Pipeline2Agent

Pipeline2Agent is a bioinformatics agent for biological question answering, public
database retrieval, sequence and structure analysis, evidence-backed reporting,
file inspection, and pipeline execution. It exposes deterministic biological operations as typed Agents SDK function tools behind a chat-style web UI, CLI, API, and Python interface.

The Python entry point is `harness.run_agent`; pipeline tools use the
`agent-pipeline` command protocol and configuration uses `AGENT_*` variables.

## What Pipeline2Agent Does

![Pipeline2Agent functions](docs/images/system_functions.png)

Pipeline2Agent can:

- answer biology questions and explain biological concepts;
- retrieve records from NCBI, PubMed, UniProt, InterPro, KEGG, QuickGO, PDB,
  and AlphaFold DB;
- analyze nucleotide sequences, genome maps, and protein structures;
- inspect FASTA, CSV, TSV, JSON, Markdown, and text files;
- read and summarize selectable-text PDF documents with page references;
- create species reports with sources, citations, and generated files;
- run Shell, Snakemake, Nextflow, and WDL pipelines; and
- retain uploads and generated files within a chat session.



## Quick Start



### 1. Get The Project

```bash
git clone https://github.com/ai2lifescience/BioAgent.git Pipeline2Agent
cd Pipeline2Agent
```



### 2. Create An Environment

```bash
conda create -n openaisdk python=3.11 -y
conda activate openaisdk
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```



### 3. Configure A Model

The harness uses OpenRouter through the OpenAI Python client. Set an API key before running the agent or model-backed reports:

On Linux Bash:

```bash
export OPENROUTER_API_KEY="your-openrouter-api-key"
```

Replace the placeholder with your real key. The variable is available to
Pipeline2Agent commands started from the current terminal session.

Every natural-language request is handled by the Agents SDK; deterministic functions run after the agent selects their registered tools. Offline smoke tests use a scripted model and do not need an API key.

### 4. Start The Web UI

```bash
conda activate openaisdk
python -B -m interfaces.web --host 127.0.0.1 --port 8000
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000) in a browser. Stop the
server with `Ctrl+C`.

If OpenRouter needs a SOCKS proxy, set it in the same terminal before starting
the server:

```bash
export AGENT_PROXY=socks5h://127.0.0.1:10801
```

`ALL_PROXY` is not required when `AGENT_PROXY` is set. See the
[web usage guide](docs/web_usage.md#start-for-local-network-access) for the
complete launch command and direct-connection option.

![Pipeline2Agent web interface](docs/images/web_ui.png)

### 5. Use Pipeline2Agent

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
Run sequence_normalization_snakemake_demo with its bundled example data and summarize the results.
```

```text
Run sequence_normalization_nextflow_demo with its bundled example data and summarize the results.
```

```text
Run dna_analysis_demo with its bundled example data and summarize the results.
```

```text
Run the sequence_qc_demo example and summarize its metrics.
```

```text
Search InterPro domains for P0A7V8
```

```text
Find QuickGO annotations for UniProtKB:P0A7V8 taxid 562
```

```text
Get KEGG query: eco:b0002
```

```text
Download AlphaFold structure for P0A7V8 as cif
```

Use the Uploads panel for local input files. Pipeline2Agent stores uploads and outputs
under the active session so later requests in the same chat can reuse them.

To allow access from another computer on a trusted local network, run:

```bash
python -B -m interfaces.web --host 0.0.0.0 --port 8000
```

Then open `http://<SERVER_LAN_IP>:8000` from the other computer.

## Architecture

Pipeline2Agent is implemented as a single OpenAI Agents SDK harness. The SDK owns the
agent loop, function-tool dispatch, guardrails, sessions, and tracing. The tools
call deterministic biological libraries and registered external APIs.

```text
User / App
  -> Agent + Runner (OpenAI Agents SDK)
     -> RunConfig.model_provider -> OpenAI Python client -> OpenRouter
     -> Pipeline2Agent function tools
        -> databases, sequence/structure tools, files, RAG, pipelines
     -> SDK sessions (SQLite)
     -> SDK guardrails, tracing, and per-session Unix-local sandbox
  -> structured answer, evidence, status, and workspace files
```

The public entry point is `harness.run_agent`. Each run returns the answer,
SDK session ID, tool evidence, run status, trace events, and workspace file
paths. Uploads and generated files remain in per-session sandboxes.

OpenRouter model IDs are configured in `models/config.py`. A run-scoped SDK
`ModelProvider` resolves these aliases and owns the shared client for root and
specialist agents. Reporting agents live with the species-report tool;
embeddings live in `rag/`. See the
[model architecture](docs/architecture.md#models-and-provider-ownership) for
configuration and client lifecycle details.

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
from interfaces.notebook import run_agent

result = run_agent("Analyze PhiX174")
print(result["answer"])
```



## Pipeline Notes

- Shell pipelines use the local shell environment.
- Snakemake pipelines require the `snakemake` package included in
`requirements.txt`.
- Nextflow pipelines require a local `nextflow` executable, Java 17 or newer,
  and a POSIX shell. On Windows, run Pipeline2Agent and Nextflow inside WSL.
- WDL pipelines use `miniwdl` and require a working Docker daemon plus access to
the task container images.
- Pipeline inputs should be supplied explicitly through the request or uploaded
through the web UI.
- Use the pipeline catalog to discover the workflows available in this checkout.
  See [pipeline architecture](docs/architecture.md#pipeline-runtime) for file
  handling, execution, and adding pipelines.



## Documentation

- [System architecture](docs/architecture.md)
- [Web UI usage and examples](docs/web_usage.md)
- [Pipeline runtime, file handling, and adding pipelines](docs/architecture.md#pipeline-runtime)
- [CLI usage and examples](docs/cli_usage.md)
- [Team development workflow](docs/dev_workflow.md)
- [Planned improvements](docs/todo.md)
