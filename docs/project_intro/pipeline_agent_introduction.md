# Pipeline2Agent — bioinformatics work from question to evidence

**Purpose:** a compact introduction to Pipeline2Agent for scientists, bioinformaticians, and collaborators.

This deck is based on the system figures in `docs/images/system_architecture.png` and `docs/images/system_functions.png`, plus the verified GPT‑5.6‑Sol live-test report in `docs/live_test_report_2026-09-26_gpt-5.6-sol.md`.

## Slide 1 — System architecture

**Pipeline Agent = LLM + Harness + Tools**

- **LLM:** understands intent, plans actions, chooses registered tools, and interprets observations.
- **Harness:** owns the agent loop, handoffs, context and memory, sessions, approvals, tracing, progress, and durable execution.
- **Tools:** deterministic bioinformatics functions, public-database clients, file/data operations, knowledge retrieval, reports, and pipelines.
- **Human in the loop:** provides goals, feedback, and approvals at defined control points.
- **Sandbox workspace:** keeps uploaded inputs and generated files together for the active session.
- **Results:** returns answers, evidence, reports, artifacts, and execution status.

**Visual:** `docs/images/system_architecture.png`

## Slide 2 — System functions

Pipeline2Agent turns a biological question and optional files into a reproducible result:

1. **Question & data:** define the question and upload FASTA, FASTQ, tables, documents, or structures.
2. **Select & configure:** choose a tool or pipeline and set validated parameters.
3. **Run & monitor:** execute deterministic operations or longer workflows, with progress and bounded resources.
4. **Results & reports:** inspect outputs, download artifacts, and explain evidence and limitations.

The function map spans genome assembly, taxonomic identification, functional annotation, variant detection, molecular typing, risk assessment, data/document analysis, knowledge search, and coding support.

**Visual:** `docs/images/system_functions.png`

## Slide 3 — Web UI and Website Bridge

### Web UI

- Chat-first workspace with model selection, turns, uploads, conversations, and a session-owned Files panel.
- Durable HTTP runs expose `run_id`, status, resumable events, approvals, evidence, and workspace artifacts.
- The same agent is available through the web UI, CLI, HTTP API, and Python interface.

### Website Bridge

A trusted host page can connect an embedded assistant drawer with a signed ticket and page-context adapter. The bridge supports:

- page context and revision identifiers;
- table and figure reads with filters;
- manual search/read;
- export, highlight, navigation, and host actions;
- refreshed reads after a state-changing action.

The live rerun changed a synthetic comparison from **all** to **treated**, verified the new revision, reduced the table from 4 to 2 rows, and reduced the figure from 6 to 3 values.

**Visuals:** `docs/images/web_ui.png`, `docs/images/live_tests_2026-09-26_gpt-5.6-sol/website_bridge_live_rerun_sidebar.png`

## Slide 4 — Basic bioinformatics

Core sequence and genome operations are deterministic and evidence-friendly:

- sequence length, GC content, base composition, validation, and reverse complement;
- ORF discovery on both strands and translation of selected ORFs;
- FASTA and GenBank feature reading;
- genome maps with reference sequences and feature JSON;
- concise interpretation that distinguishes annotated features from predictions.

In the live examples, Pipeline2Agent analyzed PhiX174 data, reported verified sequence statistics, generated ORF features, and rendered an interactive genome map.

**Visual:** `docs/images/live_tests_2026-09-26_gpt-5.6-sol/genome_map.png`

## Slide 5 — Public biology databases, retrieval, download, and structures

The public-data layer connects the agent to:

- **NCBI and PubMed** for nucleotide records, literature, and evidence searches;
- **UniProt, InterPro, KEGG, and QuickGO** for protein records, domains, pathways, and annotations;
- **PDB and AlphaFold DB** for experimental and predicted protein structures.

The agent returns source identifiers and URLs, downloads workspace-owned files, and can inspect or visualize them. Live records include NCBI retrieval, UniProt/InterPro/KEGG/QuickGO lookups, PDB 1A3N inspection, AlphaFold P0A7V8 CIF handoff, and structure summaries.

**Visuals:** `docs/images/live_tests_2026-09-26_gpt-5.6-sol/database_lookup.png`, `docs/images/live_tests_2026-09-26_gpt-5.6-sol/pdb_structure.png`

## Slide 6 — Data analysis and Documents

### Data analysis

- Inspect CSV, TSV, JSON, Markdown, and text files.
- Profile columns, types, missingness, groups, and summary statistics.
- Create plots and grouped output files that remain in the session workspace.

### Documents

- Read selectable-text PDFs with page markers and evidence references.
- Extract methods, findings, limitations, and structured report sections.
- Keep source files, generated reports, and output manifests together.

**Visuals:** `docs/images/live_tests_2026-09-26_gpt-5.6-sol/table_analysis.png`, `docs/images/live_tests_2026-09-26_gpt-5.6-sol/document_read.png`

## Slide 7 — Knowledge system

The Knowledge system provides durable, session-owned retrieval:

1. **Ingest:** crawl bounded public sources with an allowlist, page/depth limits, and a collection ID.
2. **Status:** poll the asynchronous job until it reaches a terminal state and report fetched, indexed, chunk, skipped, and error counts.
3. **Retrieve:** run a separate cited query against the existing collection and return source records, excerpts, and an evidence path.

The live UniProt test ingested one page into 59 chunks, then used a second turn to retrieve the function and S4 RNA-binding annotation for E. coli uS4/P0A7V8. The evidence artifact was saved under the session workspace.

**Visual:** `docs/images/live_tests_2026-09-26_gpt-5.6-sol/knowledge_ingest_query.png`

## Slide 8 — Research and reporting

The research specialist combines:

- PubMed and trusted web search;
- web fetching and database lookup;
- evidence retrieval, source review, and synthesis;
- cited Markdown report writing to the workspace;
- a follow-up turn that reads and displays the full substantive report.

The expanded live tests reviewed 18 sources in one workflow. A focused phage-therapy run reviewed 8 PubMed-indexed sources, compared study types and limitations, wrote a report, and then displayed its title, headings, evidence comparison, limitations, conclusion, and exact path.

**Visual:** `docs/images/live_tests_2026-09-26_gpt-5.6-sol/research_report_final_display.png`

## Slide 9 — Pipelines and execution

Pipeline2Agent treats pipelines as validated, observable jobs:

- catalog and discover available workflows;
- inspect bundled examples and validate typed inputs;
- create a plan with cores, memory, timeouts, and backend settings;
- request approval before executable actions when required;
- submit once, poll with bounded intervals, and collect declared outputs;
- record logs, manifests, status, hashes, empty outputs, and blockers honestly.

Supported workflow styles include **Shell, Snakemake, Nextflow, and WDL**. Live tests covered template workflows, metagenomic read QC, metagenomic de novo assembly, remote Cromwell execution, S3 input/output transport, and late output verification.

**Visual:** `docs/images/live_tests_2026-09-26_gpt-5.6-sol/remote_template_wdl.png`

## Slide 10 — Coding support

Coding support is bounded and evidence-producing:

- inspect source files and identify the smallest relevant change;
- edit only within the requested scope;
- run a bounded test or targeted check;
- report changed files, generated IDs, outputs, and failures.

The live coding case used code inspection and code testing to validate a small repository change. Coding is integrated with the same workspace, session history, approvals, and transparent result reporting as the biology tools.

**Visual:** `docs/images/live_tests_2026-09-26_gpt-5.6-sol/coding_support.png`

## Slide 11 — Guardrails and reliability

Pipeline2Agent is designed to be useful while keeping claims and actions bounded:

- refuses actionable requests to increase pathogen harm;
- validates tool arguments and enforces domain, page, resource, and turn limits;
- scopes files and knowledge collections to the active session;
- uses approvals for selected executable or state-changing actions;
- preserves tool evidence, citations, paths, status, logs, and hashes;
- distinguishes passed, partial, blocked, failed, and unavailable outcomes;
- reports missing dependencies, network limits, stale state, and empty outputs instead of inventing results.

The live guardrail test refused pathogen-enhancement assistance, while the broader report records truthful partial results for CAPTCHA, unavailable local runtimes, and remote polling bounds.

**Visual:** `docs/images/live_tests_2026-09-26_gpt-5.6-sol/guardrail_boundary.png`

## Reference material

- [Comprehensive GPT‑5.6‑Sol live-test report](../live_test_report_2026-09-26_gpt-5.6-sol.md)
- [System architecture figure](../images/system_architecture.png)
- [System functions figure](../images/system_functions.png)
- [Web UI figure](../images/web_ui.png)
