# BioAgent System Architecture

BioAgent is a layered bioinformatics agent system. It receives a user goal,
routes or plans the work, executes registered biological skills, collects
evidence, verifies the result, and returns a structured answer.

The key design principle is:

```text
LLM for fallback skill selection and synthesis.
Deterministic tools and public databases for biological facts.
Evidence and verification before final response.
```

## System Overview

```text
User / App
   |
   v
[Interface Layer]
CLI / Web / API / Notebook
   |
   v
[Agent Orchestrator]
Session control, routing, skill loop
   |
   |---- [Memory / State Store]
   |---- [Trace Store]
   |
   v
[Intent Router]
Direct answer? NCBI? Sequence analysis? Bio DB? Report? LLM skill loop?
   |
   v
[Planner]
Build executable steps
   |
   v
[Execution Layer]
   |          |             |              |
   v          v             v              v
Bio APIs   Bio Tools     Retrieval      File I/O
NCBI       BLAST         PubMed/RAG     FASTA/CSV
UniProt    sequence      Vector DB      reports
PDB        analysis
   |
   v
[Evidence Collector]
Record IDs, URLs, citations, query terms, files
   |
   v
[Verifier]
Check missing evidence, tool errors, biosafety-sensitive requests
   |
   v
[Final Result Assembly]
Answer with citations, files, limitations
   |
   v
User / App
```

Every run returns a structured result:

```python
{
    "answer": "...",
    "session_id": "...",
    "messages": [...],
    "evidence": {...},
    "verification": {...},
    "route": {...},
    "plan": {...},
    "trace": [...]
}
```

## 1. Interface Layer

The interface layer is where requests enter the system.

Implemented interfaces:

```text
interfaces/cli.py       Command-line interface
interfaces/api.py       Python application API
interfaces/notebook.py  Notebook-friendly helpers
interfaces/web.py       Small HTTP server for web UI and JSON API
web_ui/                 Static HTML, CSS, and JavaScript for the browser UI
```

CLI example:

```bash
python -m interfaces.cli "Analyze PhiX174 segment sequence GAGTTTTATCGCTTCCATGACGCAGAAGTTAACACTTTCGGATATTTCTGATGAGTCGAAAAATTATCTT"
```

Python API example:

```python
from interfaces.api import handle_request

result = handle_request("Search UniProt for BRCA1 human")
print(result["answer"])
```

Notebook example:

```python
from interfaces.notebook import run_bioagent

result = run_bioagent("Analyze PhiX174 segment sequence GAGTTTTATCGCTTCCATGACGCAGAAGTTAACACTTTCGGATATTTCTGATGAGTCGAAAAATTATCTT")
result["evidence"]
```

Web UI / API example:

```bash
python -m interfaces.web --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000` in a browser to use the chat-style UI.
The browser assets live in `web_ui/`. The same server exposes JSON endpoints
for application use:

```bash
curl -X POST http://127.0.0.1:8000/run \
  -H 'Content-Type: application/json' \
  -d '{"request": "Analyze PhiX174 segment sequence GAGTTTTATCGCTTCCATGACGCAGAAGTTAACACTTTCGGATATTTCTGATGAGTCGAAAAATTATCTT"}'
```

The interface layer should stay thin. It should collect input, pass it to the
orchestrator, and display the structured result.

## 2. Agent Orchestrator

The orchestrator is the manager of the agent run.

Main module:

```text
agent_core/orchestrator.py
```

Responsibilities:

```text
Create a session
Record trace events
Run intent routing
Build a plan
Execute direct skill plans
Run LLM skill loops when needed
Collect evidence
Run verification
Assemble the final answer and structured result
Return the full structured result
```

The orchestrator coordinates these modules:

```text
agent_core/memory.py       In-memory session state
agent_core/artifacts.py    Artifact rules, run workspaces, registration, and uploads
agent_core/trace.py        Structured execution trace
agent_core/router.py       Intent routing
agent_core/planner.py      Deterministic plan construction and plan types
execution/skill_executor.py   Skill execution
execution/tool_executor.py    Concrete tool execution
execution/skill_context.py    Runtime context passed to skills
agent_core/evidence.py     Evidence extraction
agent_core/verifier.py     Verification checks
agent_core/orchestrator.py Final result assembly
```

The orchestrator supports four execution modes:

```text
control_response   Static interface requests like "help" or "hello"
llm_response       Chatbot-style explanation without tools
direct_skill       A deterministic route matched one registered skill
llm_skill_loop     Unknown or complex requests where the LLM chooses skill calls step by step
```

## 3. Memory and Trace

BioAgent separates short-term state from trace events.

Short-term state:

```text
agent_core/memory.py
```

The session stores:

```text
session_id
user_request
messages
metadata
```

`skill_results` are treated as per-run working state on the active session and
are reset at the start of each run. Chat `messages` and trace events are the
durable in-process session history for the current Python process.

Trace store:

```text
agent_core/trace.py
```

Trace events include:

```text
session_started
intent_routed
plan_created
skill_started
skill_finished
model_requested
model_responded
llm_skill_call_executed
run_finalized
```

This makes debugging easier because the final response contains `trace`.

## 4. Intent Router

The router decides whether a request can be handled deterministically or should
fall back to the LLM skill loop.

Main modules:

```text
agent_core/router.py        IntentRoute type and ordered dispatcher
agent_core/route_rules/     Small deterministic route matchers
```

`router.py` owns route order and fallback behavior. Individual route-rule
modules own domain-specific matching and argument extraction.

Current routes:

```text
help / hello                    -> control_response
conceptual explanation          -> llm_response
NCBI download/search request    -> ncbi_retrieval
example skill test              -> example_skill
PDB/mmCIF structure analysis    -> protein_structure_analysis
file inspection request         -> file_inspection
BLAST request                   -> blast_search
sequence analysis request       -> sequence_analysis
UniProt / PDB lookup            -> database_lookup
PDB structure download          -> pdb_download
trusted-source species report   -> species_report
complex biological comparison   -> llm_skill_loop
literature/gene-disease review  -> llm_skill_loop
otherwise                       -> llm_skill_loop
```

Example:

```text
User: Analyze PhiX174 segment sequence GAGTTTTATCGCTTCCATGACGCAGAAGTTAACACTTTCGGATATTTCTGATGAGTCGAAAAATTATCTT
Route: direct_skill -> sequence_analysis
```

Example:

```text
User: Search UniProt for BRCA1 human
Route: direct_skill -> database_lookup
```

This bounded routing is important for biology tasks because deterministic
database/tool paths are more reliable than asking the LLM to infer everything.

## 5. Planner

The planner converts a route into executable steps.

Main module:

```text
agent_core/planner.py
```

For direct skills, it creates a plan like:

```text
1. execute skill
2. collect evidence
3. verify
4. generate response
```

For LLM skill-loop tasks, it creates a plan like:

```text
1. ask model to select skill
2. execute selected skill
3. collect evidence
4. verify
5. generate response
Complex comparison and literature-review requests also use `llm_skill_loop`.
The router may attach metadata such as compared entities and focus topics, but
the planner does not build multi-step biological research plans.
```

## 6. Skill and Tool Executors

The skill executor runs registered skill workflows. It is the boundary between
the LLM and local workflow code. The tool executor runs concrete tools for a
skill and performs lightweight architecture checks.

Main module:

```text
execution/skill_executor.py
execution/tool_executor.py
execution/skill_context.py
```

The skill executor:

```text
Parses LLM tool calls
Validates requested skill names against the skill registry
Runs only registered skill workflows
Passes SkillContext into workflows that accept it
Captures errors as structured results
Adds execution category and branch metadata
```

The tool executor:

```text
Validates concrete tool names against the tool registry
Checks the calling skill's declared tool allowlist
Checks required tool input fields
Runs the concrete ToolDefinition
Returns a standardized tool-call record
```

Execution branches:

```text
bio_api      UniProt, PDB, NCBI-like API access
bio_data     NCBI Entrez retrieval
bio_tool     BLAST and deterministic sequence tools
retrieval    PubMed/RAG species report workflow
file_io      FASTA/CSV/TSV/text inspection
diagnostics  Example test skill
```

The LLM can request a skill call, but Python decides whether that skill is
registered and how the workflow executes. Skills then call concrete tools through
`SkillContext`, which delegates to `ToolExecutor`.

## 7. Skills and Tools

BioAgent keeps skills and tools separate.

```text
Skill = workflow + rules + judgment
Tool  = concrete, validated action
```

Examples:

```text
Skill: ncbi_retrieval
  Uses tool: ncbi_fetch

Skill: sequence_analysis
  Uses tool: sequence_analyze

Skill: database_lookup
  Uses tool: bio_database_search

Skill: pdb_download
  Uses tool: pdb_download

Skill: protein_structure_analysis
  Uses tools: pdb_download when a PDB ID is provided, then protein_structure_analyze
```

Tools should stay small and concrete. Skills decide when and how to use them.

### How to organize tools

Put concrete actions under `tools/`. A tool should be narrow, validated, and
easy to test in isolation.

Current tool layout:

```text
tools/
├── base.py                  ToolDefinition dataclass
├── diagnostics/
│   ├── core.py              echo implementation
│   └── tool.py              echo ToolDefinition
├── bio_database/
│   ├── core.py              UniProt/PDB search implementation
│   └── tool.py              bio_database_search ToolDefinition
├── blast/
│   ├── core.py              BLAST implementation adapter
│   └── tool.py              blast_search ToolDefinition
├── pdb/
│   ├── core.py              RCSB PDB structure download wrapper
│   └── tool.py              pdb_download ToolDefinition
├── ncbi/
│   ├── core.py              public facade for fetch_ncbi and text requests
│   ├── spec.py              schema constants and default values
│   ├── query.py             Entrez query construction
│   ├── request_parser.py    simple text request parsing
│   ├── http.py              E-utilities HTTP calls
│   ├── download.py          FASTA and metadata download workflow
│   ├── metadata.py          GenBank metadata parsing and CSV writing
│   ├── naming.py            output names and directory resolution
│   ├── filters.py           Entrez date filters
│   ├── format.py            user-facing result formatting
│   └── tool.py              ncbi_fetch ToolDefinition
├── sequence/
│   ├── core.py              FASTA parsing, GC content, ORFs, alignment score
│   └── tool.py              sequence_analyze ToolDefinition
├── protein_structure/
│   ├── core.py              Biopython-backed PDB/mmCIF protein structure statistics
│   └── tool.py              protein_structure_analyze ToolDefinition
├── file_io/
│   ├── core.py              file inspection and Markdown writing
│   └── tool.py              file_inspect and markdown_report_writer definitions
├── literature/
│   ├── core.py              public facade for PubMed collection
│   ├── constants.py         PubMed/E-utilities constants
│   ├── query.py             PubMed query construction
│   ├── client.py            PubMed ESearch/EFetch calls
│   ├── parse.py             PubMed XML parsing
│   ├── http.py              HTTP/retry helpers
│   └── tool.py              pubmed_collect ToolDefinition
├── web/
│   ├── core.py              public facade for trusted web collection
│   ├── constants.py         trusted domains and request defaults
│   ├── trust.py             trusted-host checks
│   ├── search.py            DuckDuckGo search result extraction
│   ├── fetch.py             trusted page fetch workflow
│   ├── parse.py             HTML text extraction
│   ├── http.py              HTTP/retry helpers
│   └── tool.py              trusted_web_collect ToolDefinition
├── rag/
│   ├── core.py              public facade for RAG tool handlers
│   ├── chunk.py             rag_chunk implementation
│   ├── store.py             rag_store implementation
│   ├── retrieve.py          rag_retrieve implementation
│   ├── cite.py              rag_citations implementation
│   └── tool.py              RAG ToolDefinition objects
└── reporting/
    ├── core.py              agent-callable reporting wrappers
    └── tool.py              species_model_opinions and species_report_synthesis definitions
```

Each tool package follows the same convention:

```text
core.py       public facade for implementation functions
tool.py       ToolDefinition objects only
__init__.py   public exports
```

For simple domains, `core.py` can contain the implementation directly. For
complex domains, `core.py` should stay small and delegate to functional modules
such as `query.py`, `parse.py`, `http.py`, `download.py`, or operation-specific
modules like `chunk.py`, `store.py`, `retrieve.py`, and `cite.py`.

Each `tool.py` should define or expose a `ToolDefinition`:

```python
ToolDefinition(
    name="sequence_analyze",
    description="Analyze sequence length, GC content, counts, and ORFs.",
    handler=run_sequence_analysis,
    input_schema={...},
    output_schema={...},
    category="bio_tool",
    risk_level="low",
    requires_confirmation=False,
)
```

Tool rules:

```text
Tools do one concrete action.
Tools validate required inputs.
Tools return structured dictionaries.
Tools do not decide user intent.
Tools do not contain workflow rules or biological interpretation.
Tools include lightweight risk, auth, and confirmation metadata.
Tools are registered once in registries/tool_registry.py.
```

Good tool examples:

```text
ncbi_fetch(term, genes, db, max_records)
sequence_analyze(sequence, fasta_path, min_orf_length)
bio_database_search(database, query, max_results)
file_inspect(path)
```

Bad tool examples:

```text
answer_user_question()
decide_best_database()
write_final_report()
research_species_and_summarize_everything()
```

Those are workflows, so they belong in `skills/`.

### How to organize skills

Put workflows under `skills/`. A skill should describe when to use a workflow,
which tools it may use, and how to turn tool outputs into a reliable answer.

Current skill layout:

```text
skills/
├── base.py
├── example_skill/
│   ├── SKILL.md
│   └── workflow.py
├── ncbi_retrieval/
│   ├── SKILL.md
│   └── workflow.py
├── bio_database_search/
│   ├── SKILL.md
│   └── workflow.py
├── pdb_download/
│   ├── SKILL.md
│   └── workflow.py
├── sequence_analysis/
│   ├── SKILL.md
│   └── workflow.py
├── protein_structure_analysis/
│   ├── SKILL.md
│   └── workflow.py
├── blast_search/
│   ├── SKILL.md
│   └── workflow.py
├── file_inspection/
│   ├── SKILL.md
│   └── workflow.py
└── species_report/
    ├── SKILL.md
    ├── workflow.py
    └── utils.py
```

The registry skill name is canonical. A folder may keep an older descriptive
name during refactors, but new folders should normally match the skill name.

`SKILL.md` is the human-readable workflow contract:

```text
Purpose
When to use
When not to use
Available tools
Workflow steps
Rules
Failure handling
Output expectations
Examples
```

`workflow.py` is the executable workflow:

```python
from execution.skill_context import SkillContext, ensure_skill_context


def sequence_analysis(
    sequence=None,
    fasta_path=None,
    min_orf_length=90,
    context: SkillContext | None = None,
):
    context = ensure_skill_context(context, "sequence_analysis")
    tool_record = context.run_tool(
        "sequence_analyze",
        {
            "sequence": sequence,
            "fasta_path": fasta_path,
            "min_orf_length": min_orf_length,
        }
    )
    result = tool_record["result"]
    return {
        "skill": "sequence_analysis",
        "tool": "sequence_analyze",
        **result,
    }
```

Skill rules:

```text
Skills decide which tools to call.
Skills enforce workflow order.
Skills handle ambiguity and missing context.
Skills attach biological interpretation when appropriate.
Skills call tools through SkillContext and ToolExecutor.
Skills expose SKILL_SPEC for LLM selection.
Skills are registered once in registries/skill_registry.py.
```

### Naming convention

Use action-oriented names for tools and workflow-oriented names for skills:

```text
Tool names:
  ncbi_fetch
  sequence_analyze
  file_inspect
  bio_database_search
  pubmed_collect
  trusted_web_collect
  rag_store
  rag_retrieve
  rag_citations
  species_model_opinions
  species_report_synthesis
  markdown_report_writer

Skill names:
  ncbi_retrieval
  sequence_analysis
  file_inspection
  database_lookup
  species_report
```

This makes call traces readable:

```text
skill: sequence_analysis
tool:  sequence_analyze
```

### Request flow example

For this request:

```text
Analyze PhiX174 segment sequence GAGTTTTATCGCTTCCATGACGCAGAAGTTAACACTTTCGGATATTTCTGATGAGTCGAAAAATTATCTT
```

The system flow is:

```text
IntentRouter
  -> route_rules/sequence.py
  -> route to skill sequence_analysis
Planner
  -> create direct_skill plan
SkillExecutor
  -> execute sequence_analysis workflow
sequence_analysis workflow
  -> context.run_tool("sequence_analyze")
ToolExecutor
  -> validate allowlist and required inputs
sequence_analyze tool
  -> calculate length, type, GC content, counts, ORFs
EvidenceCollector
  -> record skill, tool output, files if any
Verifier
  -> check errors/missing evidence
BioAgentOrchestrator
  -> format final answer and structured result
```

This separation keeps the LLM away from raw implementation details while still
allowing it to choose high-level workflows.

## 8. Skill Registry

All callable skills are registered in:

```text
registries/skill_registry.py
```

Each skill has:

```text
SKILL_SPEC        JSON-schema-like workflow description for the LLM
handler           Python workflow function
category          Execution branch label
tools             Tool names the workflow may use
instruction_path  SKILL.md path
```

The registry exposes:

```python
SKILL_SPECS
SKILLS
SKILL_DEFINITIONS
```

Registered skills:

```text
example_skill
species_report
ncbi_retrieval
database_lookup
pdb_download
sequence_analysis
protein_structure_analysis
blast_search
file_inspection
pipeline_runner
```

To add a new skill:

```text
1. Create skills/<skill_name>/SKILL.md
2. Create skills/<skill_name>/workflow.py
3. Define SKILL_SPEC
4. Implement the workflow using SkillContext to call tools
5. Export the workflow in skills/<skill_name>/__init__.py
6. Add a SkillDefinition in registries/skill_registry.py
7. Add a route rule only if deterministic routing is useful
8. Add evidence/response formatting if the result has a new shape
9. Add a smoke test in evals/
```

## 9. Tool Registry

All concrete tools are registered in:

```text
registries/tool_registry.py
```

Each tool has:

```text
name
description
handler
input_schema
output_schema
category
risk_level
requires_confirmation
auth_required
```

Registered tools:

```text
echo
ncbi_fetch
pdb_download
bio_database_search
sequence_analyze
genome_map
protein_structure_analyze
blast_search
file_inspect
pipeline_runner
pubmed_collect
trusted_web_collect
rag_chunk
rag_store
rag_retrieve
rag_citations
species_model_opinions
species_report_synthesis
markdown_report_writer
```

Runtime checks currently live in code. `ToolExecutor` enforces tool
registration, skill tool allowlists, and required input fields.
`ToolDefinition.run()` enforces the per-tool `auth_required` and
`requires_confirmation` metadata when a user context is provided.

The orchestrator does not import random tool functions directly. Workflows run
tools through `SkillContext`:

```python
from execution.skill_context import ensure_skill_context

context = ensure_skill_context(context, "sequence_analysis")
result = context.run_tool("sequence_analyze", {"sequence": "ATGAAATAG"})["result"]
```

## 10. Bio APIs Layer

The bio APIs layer wraps public biological databases.

Modules:

```text
bio_data/ncbi.py     Stable NCBI data adapter
bio_data/uniprot.py  UniProt REST search
bio_data/pdb.py      RCSB PDB search and structure download
bio_data/blast.py    NCBI BLAST URL API
```

Tools using this layer:

```text
ncbi_fetch
bio_database_search
pdb_download
protein_structure_analyze
blast_search
```

Example output from a database search is structured:

```python
{
    "database": "uniprot",
    "query": "BRCA1 human",
    "record_count": 5,
    "records": [
        {
            "accession": "P38398",
            "name": "Breast cancer type 1 susceptibility protein",
            "organism": "Homo sapiens",
            "url": "https://www.uniprot.org/uniprotkb/P38398/entry"
        }
    ]
}
```

Structured outputs are easier to verify, cite, and summarize than raw text.

## 11. Bio Tools Layer

The local bio tools layer contains deterministic computation.

Modules:

```text
tools/sequence/core.py    FASTA parsing, sequence type, GC content, counts, ORFs
tools/file_io/core.py     FASTA/CSV/TSV/text inspection
```

Tools in this layer:

```text
sequence_analyze
file_inspect
```

Example:

```bash
python -m interfaces.cli "Analyze PhiX174 segment sequence GAGTTTTATCGCTTCCATGACGCAGAAGTTAACACTTTCGGATATTTCTGATGAGTCGAAAAATTATCTT"
```

This route does not need an LLM or network call.

## 12. Retrieval / Knowledge Layer

The retrieval layer supports source-backed reports.

Modules:

```text
rag/documents.py       normalized retrieval documents and hits
rag/chunking.py        chunk source records
rag/vector_db.py       Chroma vector database wrapper
rag/keyword_search.py  exact-term keyword retrieval
rag/filters.py         metadata filters
rag/retriever.py       hybrid document retriever
rag/ranker.py          source/chunk ranker and deduplicator
rag/citations.py       citation manager and evidence context builder
rag/pipeline.py        retrieve, rank, cite, and format evidence
reporting/species_report/prompts.py
reporting/species_report/opinions.py
reporting/species_report/synthesis.py
models/embedding_client.py
models/text_generation.py
models/multi_model.py
skills/species_report/workflow.py
```

The species report workflow:

```text
pubmed_collect tool
trusted_web_collect tool
rag_chunk tool
rag_store tool
rag_retrieve and rag_citations tools
species_model_opinions tool
species_report_synthesis tool
markdown_report_writer tool
```

The `rag/` package contains reusable retrieval infrastructure. The
`reporting/species_report/` package contains domain reporting logic and prompt
builders. LLM provider code stays in `models/`. Agent-callable wrappers are
exposed through `tools/rag/` and `tools/reporting/`.

The vector database is Chroma by default. BioAgent uses two output scopes:

```text
runtime/runs/{run_id}/
  chroma/

runtime/sessions/{session_id}/artifacts/
  downloads/
  uploads/
  pipelines/
  reports/
```

Run directories are for temporary execution state and intermediate files.
Session artifacts are for reusable user-visible outputs. For example, an NCBI
downloaded FASTA, uploaded pipeline input, or pipeline report is stored as a
session artifact so a later request can reuse it without requiring the user to
copy a `run_id` path.

Explicit user-provided output paths are still honored.

Pipeline folders use three config layers:

```text
runner.yaml          how to run: engine, config/inputs, entrypoint/Snakefile/workflow, cores, timeout
config.yaml          default base config; can be renamed with runner.yaml config:
config.runtime.yaml  generated per run with session input/output paths
```

For multi-input pipelines, `runner.yaml` declares named input slots that can be
mapped to uploaded or session artifact files:

```yaml
inputs:
  sequence:
    label: Sequence FASTA
    config_key: input_path
    required: true
    accepts: [".fa", ".fasta", ".fna"]
  metadata:
    label: Metadata table
    config_key: metadata_path
    required: true
    accepts: [".tsv", ".csv"]
```

For plug-and-play agent execution, keep this simple shape in the base config:

```yaml
label: my_pipeline
input_path: path/to/default/input.file
output_dir: output
report_path: output/report.md
metrics_path: output/metrics.json
params:
  min_length: 0
  mode: example
```

`config.runtime.yaml` starts from the configured base config. BioAgent replaces
declared input config keys with uploaded/session input files and resolves
declared output config keys such as `report_path` and `metrics_path` inside the
per-run pipeline artifact directory:

```text
runtime/sessions/{session_id}/artifacts/pipelines/{pipeline_name}/{run_id}/config.runtime.yaml
runtime/sessions/{session_id}/artifacts/pipelines/{pipeline_name}/{run_id}/output/report.md
runtime/sessions/{session_id}/artifacts/pipelines/{pipeline_name}/{run_id}/output/metrics.json
```

Requests can still override keys under `params`.

Embedding-backed retrieval and LLM synthesis require:

```bash
export OPENROUTER_API_KEY="..."
```

## 11. Evidence

Evidence collection is handled by:

```text
agent_core/evidence.py
```

It extracts:

```text
skills used
databases queried
query terms
record IDs
citations
URLs
files
tool outputs
retrieval date
```

For biology, this is critical. A useful answer should tell the user where facts
came from, what database was queried, what files were created, and what remains
uncertain.

## 12. Verifier

Verification is handled by:

```text
agent_core/verifier.py
```

Current checks:

```text
Tool execution errors
Biological claims without retrieval/tool support
Missing files, citations, or record IDs for tool-backed tasks
Biosafety-sensitive request patterns
```

The verifier returns:

```python
{
    "status": "ok" | "warning" | "error",
    "warnings": [...],
    "errors": [...]
}
```

The current verification checks are intentionally lightweight. Stronger
production safety controls could add:

```text
User permissions
Tool allowlists per user
Write-action approval
Prompt injection checks
Sensitive data masking
Rate limits
Human review for high-risk biological requests
```

## 13. Final Result Assembly

The orchestrator converts internal results into user-facing answers and the
structured API result.

Main method:

```text
BioAgentOrchestrator._finalize_model_answer()
```

It prefers generic fields from skill results:

```text
answer   User-facing text produced by the skill
summary  Short fallback text produced by the skill
error    Structured skill failure
```

The response generator should not invent facts. It should format information
from skill results, evidence, retrieved sources, or model responses.

## 14. Model Layer

Model configuration and runtime clients live in:

```text
models/config.py
models/llm_client.py
models/embedding_client.py
```

The project does not use YAML model configuration. Defaults live in
`models/config.py` and can be overridden with environment variables.

Default model keys:

```text
nemotron-3-super
gpt-oss
```

Important environment variables:

```text
OPENROUTER_API_KEY
OPENROUTER_API_BASE
EMBEDDING_MODEL
BIOAGENT_AGENT_MODEL_KEY
BIOAGENT_MAX_SKILL_STEPS
```

Direct deterministic routes do not require an LLM key. LLM skill-loop and RAG
workflows do require model access.

## 15. Common Agent Loop

BioAgent follows this loop:

```python
with memory.locked_session(session_id, user_request) as (session, session_created):
    session.user_request = user_request
    session.skill_results = []
    artifact_store.prepare_run(session)
    trace.record("session_started")

    route = router.route(user_request)
    trace.record("intent_routed")

    plan = planner.plan(user_request, route, model_key)
    trace.record("plan_created")

    for step in plan.steps:
        if step.name == "control_response":
            answer = step.arguments["answer"]
        elif step.kind == "llm_response":
            answer = llm.complete_without_tools(...)
        elif step.kind == "skill":
            result = skill_executor.execute_skill(step.name, step.arguments)
            session.skill_results.append(result)
            artifact_store.register_result(session, result)
        elif step.kind == "llm_skill_loop":
            loop_result = run_model_guided_skill_calls(...)
            answer = loop_result["answer"]
        elif step.kind == "evidence":
            evidence = evidence_collector.collect(session.skill_results)
        elif step.kind == "verification":
            verification = verifier.verify(...)
        elif step.kind == "respond" and not answer:
            answer = _answer_for_skill_record(session.skill_results[-1])

    evidence = evidence_collector.collect(session.skill_results)
    verification = verifier.verify(user_request, session.skill_results, evidence)
    return _build_result(...)
```

## 16. Testing and Evaluation

Smoke tests live in:

```text
evals/smoke_architecture.py
evals/golden_tasks.yaml
```

Run:

```bash
python -B evals/smoke_architecture.py
```

Useful manual checks:

```bash
python -m interfaces.cli "help"
python -m interfaces.cli "Analyze PhiX174 segment sequence GAGTTTTATCGCTTCCATGACGCAGAAGTTAACACTTTCGGATATTTCTGATGAGTCGAAAAATTATCTT"
python -m interfaces.cli "Search UniProt for BRCA1 human"
python -m interfaces.cli "Inspect file data/ncbi_downloads_phix174/phix174_A.fasta"
```

## 17. Extension Guidelines

When extending BioAgent:

```text
Prefer deterministic tools for biological computation.
Use public databases for facts.
Keep LLM outputs source-backed when possible.
Return structured tool results.
Collect evidence for every nontrivial tool result.
Add verifier checks for new risk areas.
Keep interfaces thin.
Keep the executor as the tool boundary.
Add tests for routing and result shape.
```

Avoid:

```text
Hardcoding API keys
Letting the LLM run arbitrary code
Mixing interface logic with skill logic
Returning only raw text from tools
Making unsupported biological claims without evidence
```

## 18. Current Limitations

Current limitations:

```text
Memory, sessions, and trace are app-scoped but in-process only.
The web UI/API uses the Python standard library, not a production ASGI server.
The web Stop button aborts browser waiting only; it does not kill backend work.
Verifier checks are rule-based and lightweight.
BLAST support uses the NCBI URL API and may require polling/waiting.
The planner is mostly rule-based and not yet a complex workflow graph.
Long-term memory, user authentication, and runtime permission policies are not implemented.
Policy YAML files are reference material only unless wired into runtime code.
```

These are deliberate MVP choices. The architecture is now split cleanly enough
that each of these can be replaced with a production component later.
