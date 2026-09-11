# BioAgent CLI Usage Guide

This guide shows how to use BioAgent from the command line.

The CLI entrypoint is:

```bash
python -m interfaces.cli "<your request>"
```

The CLI accepts natural-language requests. It routes requests to **skills**.
Skills then call concrete **tools** through `registries/tool_registry.py`.

```text
CLI request
  -> IntentRouter
  -> Skill workflow
  -> Concrete tool(s)
  -> Evidence / verification / response
```

## Basic CLI Form

```bash
python -m interfaces.cli "help"
```

Optional model arguments:

```bash
python -m interfaces.cli --model-key nemotron-3-super "help"
python -m interfaces.cli --model-key gpt-oss "help"
python -m interfaces.cli --max-skill-steps 3 "Summarize PhiX174 with trusted sources"
```

Available model keys are defined in `models/config.py`.

LLM-backed requests require:

```bash
export OPENROUTER_API_KEY="..."
```

Direct deterministic routes such as `help`, sequence analysis, file inspection,
and the example skill do not require an LLM key.

## Skills and Tools Coverage

The CLI calls skills. The skill workflow calls the listed tool.

```text
Skill                Tool(s) used
---------------------------------------------------------
example_skill        echo
pipeline_runner      pipeline_runner
ncbi_retrieval       ncbi_fetch
database_lookup      bio_database_search
pdb_download         pdb_download
sequence_analysis    sequence_analyze
genome_map           genome_map
protein_structure_analysis   protein_structure_analyze
blast_search         blast_search
file_inspection      file_inspect
species_report       pubmed_collect, trusted_web_collect, rag_chunk,
                     rag_store, rag_retrieve, rag_citations, species_model_opinions,
                     species_report_synthesis, markdown_report_writer
```

## 1. Direct Help

No skill or tool is needed.

```bash
python -m interfaces.cli "help"
```

Expected route:

```text
control_response
```

Use this to verify the CLI starts correctly.

## 2. Chatbot Explanation

No skill or tool is needed, but the configured model is called.

```bash
python -m interfaces.cli "What is GC content?"
```

Expected route:

```text
llm_response
```

Use this for conceptual explanations. Requests that ask to search, retrieve,
analyze files, cite sources, or run pipelines should route to skills instead.

## 3. Example Skill

Skill:

```text
example_skill
```

Tool:

```text
echo
```

Command:

```bash
python -m interfaces.cli "Please test skill calling by running the example skill with message hello and tag smoke."
```

Expected behavior:

```text
Route: direct_skill
Skill: example_skill
Tool: echo
Output: echoed message, tag, status, word count
```

Uppercase example:

```bash
python -m interfaces.cli "Run the example skill with message hello world and tag uppercase-test uppercase."
```

Use this skill to test that routing, skill execution, and tool execution are
working without network access.

## 4. Pipeline Skills

Pipeline execution uses one public skill and one public tool. The selected
pipeline folder decides the engine and base config file through `runner.yaml`.
The configured base config contains raw pipeline defaults.

```text
CLI request
  -> pipeline_runner skill
  -> pipeline_runner tool
  -> pipelines/<pipeline_name>/runner.yaml
  -> configured base config file, default: pipelines/<pipeline_name>/config.yaml
  -> engine: shell, snakemake, nextflow, or wdl
  -> uploaded input path, if provided
  -> runtime/sessions/<session_id>/artifacts/pipelines/<pipeline_name>/<run_id>/
```

The default pipeline folders are:

```text
pipelines/generic_shell/
pipelines/generic_snakemake/
pipelines/generic_nextflow/
pipelines/generic_wdl/
```

Use `pipeline_name` to select a different approved folder. The runner accepts
folder names only, not arbitrary script paths.

Skill:

```text
pipeline_runner
```

Tool:

```text
pipeline_runner
```

The shell example reads runner settings from:

```text
pipelines/generic_shell/runner.yaml
```

The raw pipeline defaults are in:

```text
pipelines/generic_shell/config.yaml
```

The tool writes a runtime config under the per-run pipeline directory and calls:

```bash
bash pipelines/generic_shell/run.sh <run_dir>/config.runtime.yaml
```

By default, the runner uses the configured input path directly. If the request
provides an uploaded file path, BioAgent writes that path into
`config.runtime.yaml` and keeps the previous/default source as
`original_input_path`.

Command:

```bash
python -m interfaces.cli "Run the shell pipeline."
```

Choose a specific shell pipeline folder:

```bash
python -m interfaces.cli "Run the shell pipeline with pipeline_name: generic_shell."
```

Shell pipeline folder contract:

```text
pipelines/<pipeline_name>/
  runner.yaml
  config.yaml      # or another file selected by runner.yaml config:
  run.sh           # or another file selected by runner.yaml entrypoint:
```

The shell `runner.yaml` should include:

```yaml
name: generic_shell
engine: shell
config: config.yaml
entrypoint: run.sh
timeout: 120
inputs:
  reads:
    label: Reads text
    config_key: input_path
    required: true
    accepts: [".txt", ".fastq", ".fq", ".fasta", ".fa"]
outputs:
  report:
    config_key: report_path
    default: output/report.md
    kind: report
    required: true
  metrics:
    config_key: metrics_path
    default: output/metrics.json
    kind: metrics
    required: true
```

The shell base config should use the plug-and-play shape:

```yaml
label: generic_shell
input_path: data/input/example_reads.txt
metadata_path: data/input/example_metadata.tsv
output_dir: output
report_path: output/report.md
metrics_path: output/metrics.json
normalized_path: output/normalized.txt
subtype_path: output/subtypes.tsv
params:
  normalize_mode: whitespace
  uppercase: false
  sequence_id_column: sequence_id
  subtype_column: subtype
  missing_subtype: unassigned
```

The shell script must accept one argument:

```bash
bash run.sh config.runtime.yaml
```

The Snakemake example reads runner settings from:

```text
pipelines/generic_snakemake/runner.yaml
```

The raw pipeline defaults are in:

```text
pipelines/generic_snakemake/config.yaml
```

The tool writes a runtime config under the per-run pipeline directory and calls Snakemake with the configured Snakefile:

```bash
snakemake --cores 2 --snakefile pipelines/generic_snakemake/Snakefile --configfile <run_dir>/config.runtime.yaml
```

Command:

```bash
python -m interfaces.cli "Run the snakemake pipeline dry-run with 2 cores."
```

Override multiple declared inputs by slot name:

```bash
python -m interfaces.cli 'Run pipeline with pipeline_name: generic_snakemake sequence: "runtime/sessions/<session_id>/artifacts/uploads/sequences.fasta" metadata: "runtime/sessions/<session_id>/artifacts/uploads/metadata.tsv" min_length 50.'
```

Choose a specific Snakemake pipeline folder:

```bash
python -m interfaces.cli "Run the snakemake pipeline with pipeline_name: generic_snakemake dry-run with 2 cores."
```

Run the Nextflow example with its declared inputs:

```bash
python -m interfaces.cli 'Run pipeline with pipeline_name: generic_nextflow sequence: "pipelines/generic_nextflow/data/input/sequences_segment1.fasta" metadata: "pipelines/generic_nextflow/data/input/metadata.tsv" min_length 20.'
```

The Nextflow folder contract is:

```text
pipelines/<pipeline_name>/
  runner.yaml
  config.yaml       # or another file selected by runner.yaml config:
  main.nf           # or another file selected by runner.yaml workflow:
  nextflow.config   # optional, selected by runner.yaml nextflow_config:
```

A Nextflow `runner.yaml` uses the same input declarations as other engines and
maps published output names back to BioAgent artifact paths:

```yaml
name: generic_nextflow
engine: nextflow
config: config.yaml
workflow: main.nf
nextflow_config: nextflow.config
cores: 1
inputs:
  sequence:
    config_key: input_path
    required: true
    accepts: [".fa", ".fasta", ".fna"]
outputs:
  report:
    config_key: report_path
    default: output/report.md
    nextflow_output: report.md
    kind: report
    required: true
```

BioAgent calls Nextflow with the generated YAML parameter file and an isolated
work directory:

```bash
nextflow -c pipelines/<pipeline_name>/nextflow.config run pipelines/<pipeline_name>/main.nf -params-file <run_dir>/config.runtime.yaml -work-dir <run_dir>/nextflow_work
```

The runtime parameters include `nextflow_output_dir`. The workflow must publish
final files there; the runner copies and validates them using the
`nextflow_output` mappings. A BioAgent dry run uses Nextflow `-preview`.

Run a WDL pipeline folder with a declared input slot:

```bash
python -m interfaces.cli 'Run pipeline with pipeline_name: generic_wdl sequence: "pipelines/generic_wdl/data/input/example_sequence.fasta"'
```

WDL execution uses `miniwdl`. Install dependencies first:

```bash
pip install -r requirements.txt
```

miniwdl uses your local miniwdl runtime configuration. By default, miniwdl
expects Docker unless your environment is configured otherwise.

If the pipeline folder has `options.json`, BioAgent writes
`options.runtime.json` into the run directory. Relative Cromwell-style
`final_workflow_outputs_dir` values are rewritten under the run directory for
future Cromwell compatibility, but `runner.yaml.outputs` still controls what
BioAgent collects and shows.

Snakemake pipeline folder contract:

```text
pipelines/<pipeline_name>/
  runner.yaml
  config.yaml      # or another file selected by runner.yaml config:
  Snakefile        # or another file selected by runner.yaml snakefile:
```

The Snakemake `runner.yaml` should include:

```yaml
name: generic_snakemake
engine: snakemake
config: config.yaml
snakefile: Snakefile
cores: 1
timeout: 300
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
outputs:
  report:
    config_key: report_path
    default: output/report.md
    kind: report
    required: true
  metrics:
    config_key: metrics_path
    default: output/metrics.json
    kind: metrics
    required: true
  normalized_sequence:
    config_key: normalized_fasta_path
    default: output/normalized.fasta
    kind: sequence
    required: true
```

The Snakemake base config should use the same plug-and-play shape:

```yaml
label: generic_snakemake
input_path: data/input/sequences_segment1.fasta
metadata_path: data/input/metadata.tsv
output_dir: output
report_path: output/report.md
metrics_path: output/metrics.json
normalized_fasta_path: output/normalized.fasta
params:
  subtype: subtype1
  segment: segment1
  time: all-time
  analysis_mode: example
  min_length: 0
```

The runner calls Snakemake like:

```bash
snakemake --cores <cores> --snakefile pipelines/<pipeline_name>/Snakefile --configfile <run_dir>/config.runtime.yaml
```

Expected behavior:

```text
Route: direct_skill
Skill: pipeline_runner
Tool: pipeline_runner
Output: runtime config path, output directory, report path, metrics
```

Uploaded pipeline inputs are used directly from:

```text
runtime/sessions/<session_id>/artifacts/uploads/
```

Before running, the pipeline runner skill checks required inputs declared in
`runner.yaml`. If a required input is missing or points to a missing/wrong file,
the skill returns a prompt asking for the needed path instead of starting the
tool. The skill does not use default input files from `config.yaml`; those
defaults are examples for the raw pipeline and are copied into the runtime
config only after the user provides the selected runtime input.

The generated runtime config is written under the per-run pipeline directory:

```text
runtime/sessions/<session_id>/artifacts/pipelines/<pipeline_name>/<run_id>/config.runtime.yaml
```

It starts from the configured base config, then BioAgent writes controlled
runtime fields such as selected input paths, declared output paths, run
directory, and output directory. It also adds compatibility fields:

```text
input_path
original_input_path
session_input_path
input_staged
run_dir
output_dir
report_path
metrics_path
pipeline_name
label
timeout
```

For plug-and-play pipelines, keep runtime fields top-level in the base config:

```yaml
input_path: path/to/default/input.file
output_dir: output
report_path: output/report.md
metrics_path: output/metrics.json
params:
  min_length: 0
  mode: example
```

BioAgent replaces declared input config keys with uploaded/session files and
resolves declared output config keys such as `report_path` and `metrics_path`
under the per-run pipeline directory. Requests can override keys under `params`:

```bash
python -m interfaces.cli "Run pipeline generic_snakemake with input_path: runtime/sessions/<session_id>/artifacts/uploads/sequences.fasta min_length 50."
```

When the request does not provide output overrides, BioAgent writes reusable
pipeline outputs to the declared output file paths inside the run directory:

```text
runtime/sessions/<session_id>/artifacts/pipelines/<pipeline_name>/<run_id>/output/report.md
runtime/sessions/<session_id>/artifacts/pipelines/<pipeline_name>/<run_id>/output/metrics.json
```

For example:

```text
runtime/sessions/<session_id>/artifacts/pipelines/generic_shell/<run_id>/output/
```

If the request provides `output_dir`, it overrides the raw config value for
pipelines that still use that directory. Declared output file keys remain the
source of truth for files collected by BioAgent. Relative output paths are
resolved under the run directory. For example:

```text
output_dir: custom_output
```

becomes:

```text
runtime/sessions/<session_id>/artifacts/pipelines/<pipeline_name>/<run_id>/custom_output
```

To add another plug-and-play shell pipeline:

```text
pipelines/read_qc/
  runner.yaml
  pipeline_config.yaml
  run_qc.sh
```

Then run:

```bash
python -m interfaces.cli "Run pipeline read_qc."
```

To add another plug-and-play Snakemake pipeline:

```text
pipelines/metagenome_qc/
  runner.yaml
  pipeline_config.yaml
  workflow.smk
```

Then run:

```bash
python -m interfaces.cli "Run pipeline metagenome_qc with 8 cores."
```

## 5. Sequence Analysis Skill

Skill:

```text
sequence_analysis
```

Tool:

```text
sequence_analyze
```

Analyze a raw sequence:

```bash
python -m interfaces.cli "Analyze PhiX174 segment sequence GAGTTTTATCGCTTCCATGACGCAGAAGTTAACACTTTCGGATATTTCTGATGAGTCGAAAAATTATCTT"
```

Expected behavior:

```text
Route: direct_skill
Skill: sequence_analysis
Tool: sequence_analyze
Output: record count, length, sequence type, GC content, ORFs
```

Analyze a FASTA file:

```bash
python -m interfaces.cli "Analyze FASTA file data/ncbi_downloads_phix174/phix174_A.fasta"
```

In the web UI or Python API, where a `session_id` is reused across turns, you
can also analyze the newest downloaded FASTA artifact:

```text
Analyze the latest FASTA.
```

Ask for ORF analysis:

```bash
python -m interfaces.cli "Find ORFs and GC content for PhiX174 segment sequence GAGTTTTATCGCTTCCATGACGCAGAAGTTAACACTTTCGGATATTTCTGATGAGTCGAAAAATTATCTT"
```

This skill is local-only and does not require network access or an LLM key.

## 6. Genome Map Skill

Skill:

```text
genome_map
```

Tool:

```text
genome_map
```

Create a circular genome map from a FASTA file. Replace the path with a real
downloaded FASTA path from your workspace. If the FASTA has no annotations,
BioAgent predicts ORFs and maps those:

```bash
python -m interfaces.cli "Show genome structure for FASTA file data/ncbi_downloads_phix174/phix174_A.fasta as a circular map"
```

In the web UI or Python API, where a `session_id` is reused across turns, you
can map the newest downloaded FASTA artifact:

```text
Show genome structure of the latest FASTA as a circular map.
```

Expected behavior:

```text
Route: direct_skill
Skill: genome_map
Tool: genome_map
Output: SVG image path, genome length, feature count, ORF/gene/CDS counts
```

The web UI renders the generated SVG map inline. GenBank or GFF+FASTA inputs
produce richer maps than plain FASTA.

## 7. File Inspection Skill

Skill:

```text
file_inspection
```

Tool:

```text
file_inspect
```

Inspect a FASTA file:

```bash
python -m interfaces.cli "Inspect file data/ncbi_downloads_phix174/phix174_A.fasta"
```

Inspect a metadata CSV:

```bash
python -m interfaces.cli "Inspect file data/ncbi_downloads_phix174/phix174_A.metadata.csv"
```

Expected behavior:

```text
Route: direct_skill
Skill: file_inspection
Tool: file_inspect
Output: file type, bytes, line count, record count or row count
```

This skill is local-only and read-only.

## 8. Database Lookup Skill

Skill:

```text
database_lookup
```

Tool:

```text
bio_database_search
```

Search UniProt:

```bash
python -m interfaces.cli "Search UniProt for BRCA1 human"
```

Limit returned records:

```bash
python -m interfaces.cli "Find 3 UniProt records for BRCA1 human"
```

Search PDB:

```bash
python -m interfaces.cli "Find 3 PDB entries for hemoglobin"
```

Look up domains, pathways, ontology annotations, and predicted structures:

```bash
python -m interfaces.cli "Search InterPro domains for P0A7V8"
python -m interfaces.cli "Get KEGG query: eco:b0002"
python -m interfaces.cli "Find QuickGO annotations for UniProtKB:P0A7V8 taxid 562"
python -m interfaces.cli "Download AlphaFold structure for P0A7V8 as cif"
```

Expected behavior:

```text
Route: direct_skill
Skill: database_lookup
Tool: bio_database_search
Output: database, query, record count, IDs/accessions, URLs
```

This skill uses public web APIs and requires network access.

AlphaFold DB returns existing predicted models; it does not run AlphaFold.
KEGG public REST access is intended for academic use and is rate-limited by
BioAgent to at most three requests per second.

## 9. PDB Download Skill

Skill:

```text
pdb_download
```

Tool:

```text
pdb_download
```

Download a structure as mmCIF:

```bash
python -m interfaces.cli "Download PDB structure 1A3N as cif"
```

Download a structure in legacy PDB format:

```bash
python -m interfaces.cli "Download PDB 1A3N as pdb"
```

Expected behavior:

```text
Route: direct_skill
Skill: pdb_download
Tool: pdb_download
Output: PDB ID, format, local structure path, RCSB source URL
```

Downloaded structures are stored in the active session artifact directory by
default, under `artifacts/structures/`.

## 10. Protein Structure Analysis Skill

Skill:

```text
protein_structure_analysis
```

Tool:

```text
protein_structure_analyze
```

Analyze a downloaded or local protein mmCIF/PDB file:

```bash
python -m interfaces.cli "Analyze structure file runtime/sessions/demo/artifacts/structures/1A3N.cif"
```

Download and analyze a PDB ID in one request:

```bash
python -m interfaces.cli "Analyze the structure of 3GOU"
```

Expected behavior:

```text
Route: direct_skill
Skill: protein_structure_analysis
Tool: pdb_download when a PDB ID is provided, then protein_structure_analyze
Output: format, atom count, chain count, residue count, ligands, water count, method, resolution
```

In the web UI or Python API, where a `session_id` is reused across turns, you
can download a structure and then analyze the newest structure artifact:

```text
Download PDB structure 1A3N as cif
Analyze the latest structure
```

For separate CLI commands, pass the explicit `structure_path` because each CLI
invocation is a fresh process.

This skill is local-only after the structure file has been downloaded.

## 11. NCBI Retrieval Skill

Skill:

```text
ncbi_retrieval
```

Tool:

```text
ncbi_fetch
```

Download PhiX174 gene A and G records:

```bash
python -m interfaces.cli "download 10 records phiX174 genes A G"
```

Search a specific organism:

```bash
python -m interfaces.cli "download 5 records organism \"Escherichia phage phiX174\" genes A G"
```

Use an Entrez date range:

```bash
python -m interfaces.cli "download 10 records phiX174 genes A G from 2020-2024"
```

Expected behavior:

```text
Route: direct_skill
Skill: ncbi_retrieval
Tool: ncbi_fetch
Output: matched count, downloaded count, FASTA paths, metadata CSV paths
```

This skill uses NCBI Entrez and writes files under `data/`.

Optional NCBI settings:

```bash
export NCBI_EMAIL="you@example.com"
export NCBI_API_KEY="..."
```

## 12. BLAST Search Skill

Skill:

```text
blast_search
```

Tool:

```text
blast_search
```

Submit a BLASTN search without waiting:

```bash
python -m interfaces.cli "BLAST PhiX174 segment sequence GAGTTTTATCGCTTCCATGACGCAGAAGTTAACACTTTCGGATATTTCTGATGAGTCGAAAAATTATCTT with blastn database nt"
```

Submit and wait for parsed hit results:

```bash
python -m interfaces.cli "BLAST PhiX174 segment sequence GAGTTTTATCGCTTCCATGACGCAGAAGTTAACACTTTCGGATATTTCTGATGAGTCGAAAAATTATCTT with blastn database nt and wait"
```

Poll an existing BLAST RID:

```bash
python -m interfaces.cli "Poll BLAST RID ABCD123456 and return hits"
```

Expected behavior:

```text
Route: direct_skill
Skill: blast_search
Tool: blast_search
Output without waiting: RID, program, database, status, polling guidance
Output with waiting/polling: RID, status, hit count, and compact top-hit summaries
```

This skill uses the NCBI BLAST URL API and requires network access. Waiting for
results can take time.

## 13. Species Report Skill

Skill:

```text
species_report
```

Tools:

```text
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

Create a trusted-source species report:

```bash
export OPENROUTER_API_KEY="..."
python -m interfaces.cli "Create a trusted-source species report about PhiX174 with PubMed and RAG"
```

Ask a focused question:

```bash
export OPENROUTER_API_KEY="..."
python -m interfaces.cli "Create a species report about PhiX174 focusing on genome structure and host range"
```

Expected behavior:

```text
Route: direct_skill
Skill: species_report
Output: Markdown report, report path, source count, Chroma collection, citations
```

This skill requires network access and LLM access. It may write reports under:

```text
runtime/reports/
```

## 14. LLM Skill Loop Fallback

If no deterministic router rule matches, BioAgent asks the configured model to
choose from the registered skill specs.

Example:

```bash
export OPENROUTER_API_KEY="..."
python -m interfaces.cli "What can you find about PhiX174 biology from reliable sources?"
```

Expected behavior:

```text
Route: llm_skill_loop
Model chooses a registered skill if needed
Executor runs only registered skills
```

Use `--max-skill-steps` to limit the loop:

```bash
python -m interfaces.cli --max-skill-steps 2 "What can you find about PhiX174 biology from reliable sources?"
```

## 15. Inspecting Full Results From Python

The CLI prints only `result["answer"]`. To inspect route, plan, evidence, and
trace, use the Python API:

```python
from interfaces.api import handle_request

result = handle_request("Analyze PhiX174 segment sequence GAGTTTTATCGCTTCCATGACGCAGAAGTTAACACTTTCGGATATTTCTGATGAGTCGAAAAATTATCTT")
print(result["route"])
print(result["plan"])
print(result["evidence"])
print(result["trace"])
```

This is useful when debugging skill/tool routing.

## 16. Quick Smoke-Test Commands

Local-only:

```bash
python -m interfaces.cli "help"
python -m interfaces.cli "Please test skill calling by running the example skill with message hello and tag smoke."
python -m interfaces.cli "Analyze PhiX174 segment sequence GAGTTTTATCGCTTCCATGACGCAGAAGTTAACACTTTCGGATATTTCTGATGAGTCGAAAAATTATCTT"
python -m interfaces.cli "Inspect file data/ncbi_downloads_phix174/phix174_A.fasta"
```

Public API access:

```bash
python -m interfaces.cli "Search UniProt for BRCA1 human"
python -m interfaces.cli "Find 3 PDB entries for hemoglobin"
```

File-writing or longer-running:

```bash
python -m interfaces.cli "download 10 records phiX174 genes A G"
python -m interfaces.cli "BLAST PhiX174 segment sequence GAGTTTTATCGCTTCCATGACGCAGAAGTTAACACTTTCGGATATTTCTGATGAGTCGAAAAATTATCTT with blastn database nt"
```

LLM-backed:

```bash
export OPENROUTER_API_KEY="..."
python -m interfaces.cli "Create a trusted-source species report about PhiX174 with PubMed and RAG"
```

## 17. Troubleshooting

Missing OpenRouter key:

```text
Agent error: OPENROUTER_API_KEY is required for OpenRouter models.
```

Fix:

```bash
export OPENROUTER_API_KEY="..."
```

File not found:

```text
Skill file_inspection failed: File not found: ...
```

Fix the path or run an NCBI retrieval command first to create example FASTA/CSV
outputs.

Network/API failures:

```text
Skill database_lookup failed: ...
Skill ncbi_retrieval failed: ...
Skill blast_search failed: ...
```

Check network access, API rate limits, and any service-specific requirements.
