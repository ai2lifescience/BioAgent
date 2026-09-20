# Pipeline2Agent Web UI Usage

This guide shows how to run the Pipeline2Agent browser interface locally or from
another computer on the same local network.

## Start Local Web UI

Use this when you only need to open Pipeline2Agent on the same machine:

```bash
conda activate openaisdk
python -B -m interfaces.web --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000
```

`127.0.0.1` means only this computer can access the web page.

## Separate Assistant Page

Restart the web server after updating, then open:

```text
http://127.0.0.1:8000/assistant
```

The original interface remains at `/`. The assistant page is a compact chat
surface intended to fill a host website's right-side drawer. It includes model
selection, file attachments, streamed activity, and a small context summary.

Open `/assistant-demo` to see a sample workspace with Pipeline2Agent mounted as a
collapsible drawer:

```text
http://127.0.0.1:8000/assistant-demo
```

Another website can open the assistant in an iframe or a separate tab and
prefill the visible context:

```text
/assistant?project_id=123&sample_id=456&result_type=summary
```

These values are labels included with your message; they do not fetch data from
MScan. Attach a file or paste results for the agent to use. Encode parameter
values with `URLSearchParams` when building links.

For a host website, include the reusable drawer helper and mount it once:

```html
<div id="agent-drawer"></div>
<script src="https://pipeline2agent.example.org/static/assistant-embed.js"></script>
<script>
  const drawer = Pipeline2AgentDrawer.mount({
    target: document.getElementById("agent-drawer"),
    src: "https://pipeline2agent.example.org/assistant",
    context: { project_id: "123", sample_id: "456", result_type: "summary" }
  });
</script>
```

The helper creates the launcher, right-side panel, close button, iframe, and
context messaging. Call `drawer.updateContext(nextContext)` when the user
changes projects or samples.

A custom embedding can update the assistant after loading with `postMessage`:

```js
assistantFrame.contentWindow.postMessage(
  {
    type: "agent-context",
    context: { project_id: "123", sample_id: "456", result_type: "summary" }
  },
  "https://pipeline2agent.example.org"
);
```

Use the exact Pipeline2Agent origin as the second argument and validate `event.origin`
in a custom embedding implementation. The assistant accepts text labels only.

For a proxy mount such as `/agent/assistant`, route the whole `/agent/`
prefix to Pipeline2Agent and rewrite that prefix before forwarding, including static
files and API requests. The page resolves these URLs relative to its mount
point. Disable proxy buffering for streaming responses. Public website
integration still needs that website's authentication and session permissions;
this page does not add them.

The separate page keeps its conversation while it is open. Reloading or choosing
**New chat** starts a new session; context labels stay on screen. **Stop waiting**
disconnects the response stream; work already started on the server may continue.

On the main page, use the session actions beside a conversation to rename it or
pin it. Pinned conversations stay at the top of the list and the title and pin
state are stored with the server-side session metadata.

## Runtime Panel

Each completed request includes a compact tab row below the answer: **Runtime**,
**Plan & execution**, **Evidence**, and **Trace**. Select one tab at a time; the
selected diagnostic view uses one shared content area:

Click the selected tab again to hide the diagnostic area.

- **Runtime** shows status, model, elapsed time, tool count, file count, and the
  configured maximum turns.
- **Plan & execution** shows the registered operations and the ordered agent,
  model, handoff, tool, guardrail, approval, and completion events returned by
  the Agents SDK. It reports observable actions and does not expose private
  model reasoning.
- **Evidence** groups tools, databases, queries, records, sources, links, files,
  and tool errors. Workspace files link to their downloads.
- **Trace** shows the timestamped technical event stream in a compact readable
  form so the useful diagnostic details stay visible.

The report remains useful for direct answers, database lookups, document reads,
and pipeline requests. Pipeline outputs and structure or figure previews still
appear above the report when a tool produces them.

## Start For Local Network Access

Use this when another PC on the same LAN should open the Pipeline2Agent page:

Set the OpenRouter proxy once in your terminal, then start the server:

```bash
conda activate openaisdk
export AGENT_PROXY=socks5h://127.0.0.1:10801
python -B -m interfaces.web --host 0.0.0.0 --port 8000
```

`ALL_PROXY` is not required when `AGENT_PROXY` is set. You do not need to
unset `HTTP_PROXY` or `HTTPS_PROXY` for OpenRouter requests. Use `http://` if
your proxy provides an HTTP listener; use `socks5h://` for the SOCKS5 listener
shown above.

Alternatively, set the proxy for just the server process after activating
`openaisdk`:

```bash
AGENT_PROXY=socks5h://127.0.0.1:10801 \
  python -B -m interfaces.web --host 0.0.0.0 --port 8000
```

For direct OpenRouter connections, use:

```bash
AGENT_DISABLE_PROXY=1 \
  python -B -m interfaces.web --host 0.0.0.0 --port 8000
```

`AGENT_DISABLE_PROXY=1` takes priority over proxy settings. If you previously
exported it, run `unset AGENT_DISABLE_PROXY` before switching back to a
proxy. Restart a running server after changing its environment.

These Pipeline2Agent settings control OpenRouter model and embedding requests.
Other database and pipeline clients retain their own proxy settings.

Find this machine's LAN IP:

```bash
hostname -I
```

On another PC in the same local network, open:

```text
http://<LAN_IP>:8000
```

For example, if this machine's LAN IP is `192.168.75.56`:

```text
http://192.168.75.56:8000
```

`0.0.0.0` means the server accepts connections from other machines that can
reach this computer. Use it only on a trusted local network.

## Stop A Previous Web Server

Check what process is using port `8000`:

```bash
ss -ltnp 'sport = :8000'
```

Example output may include:

```text
users:(("python",pid=190933,fd=3))
```

Stop that process:

```bash
kill 190933
```

Replace `190933` with the real PID shown on your machine.

You can also list Pipeline2Agent web processes:

```bash
ps -eo pid,cmd | rg 'interfaces\.web|interfaces/web.py'
```

## Firewall

If another PC cannot open the page, allow port `8000` through the firewall:

```bash
sudo ufw allow 8000/tcp
```

Then retry:

```text
http://<LAN_IP>:8000
```

## Web UI Basics

The web page works like a chat interface:

1. Select a model from the model menu.
2. Type a biological request in the message box.
3. Click Send.
4. Open the Thinking panel if you want to see runtime progress.
5. Check the answer, evidence, status, trace, and generated files below
   the response.

The left session sidebar lets you create a new chat, switch between server-side
SDK sessions, and delete sessions. The browser keeps only the active session ID;
conversation messages are loaded from the server's `SQLiteSession` when a chat
opens, so another browser tab or page reload sees the same history.

The same session can reuse downloaded files. For example, you can download a
FASTA file in one message and then ask Pipeline2Agent to analyze the latest FASTA in a
later message.

## Manage Workspace Files

The `Workspace` panel is the file browser for the active SDK sandbox session.
The agent and its tools see the same workspace, so an uploaded file is already
available to pipeline tools; there is no separate input label or path insertion
step.

- Choose `Upload`, or drop files into the upload area. Files are stored under
  `uploads/` in the current session.
- Use the search box or the `All files`, `Inputs`, and `Outputs` filter to find a
  file. The panel shows each file's name, type, size, and workspace-relative
  path.
- Use `Download` when you need a local copy. Use `Remove` to delete a file from
  the session workspace.
- Refer to a file by name in your message, for example `Analyze reads.fastq`
  or `Run sequence_metadata_assignment on metadata.csv`. Pipeline2Agent resolves the workspace file
  and supplies the path required by the selected tool.
- For a text-based PDF, ask `Summarize my uploaded paper.pdf` or ask a question
  about the paper. Pipeline2Agent extracts the document in page-aware chunks and
  `workspace_search` can find a phrase across several uploaded documents before
  `document_read` reads the relevant PDF pages. Scanned PDFs still require OCR;
  extracted text includes page markers so answers can cite page numbers.

## Common assistant applications

The current tool surface supports four general assistant workflows alongside
the biology tools:

- **Document assistant:** search uploaded text/PDF files with `workspace_search`,
  then read selectable PDF pages with `document_read` and cite the workspace
  path and page markers.
- **Data analyst:** use `data_analysis` for bounded profiles, missing-value
  checks, grouped summaries, and distribution plots from CSV, TSV, or Excel
  files. The tool returns measured values and created plot paths.
- **Web research:** use `web_research` for current multi-source questions. It
  preserves source URLs and bounded excerpts for citations; curated NCBI and
  database requests still use their dedicated tools.
- **Coding assistant:** use `code_inspection` for read-only workspace questions.
  `code_edit` and `code_test` are approval-controlled and limited to the active
  session workspace and bounded commands.

For a task combining several operations, the root agent can delegate to
`document_specialist`, `data_analysis_specialist`, `web_research_specialist`,
or `coding_specialist`. Each specialist shares the session workspace and returns
the same runtime evidence used by the main chat.

Workspace files are stored in the active SDK sandbox session:

```text
runtime/sessions/<session_id>/uploads/
```

If the same filename is uploaded more than once, Pipeline2Agent avoids overwriting by
adding a unique prefix to the stored name. Generated outputs appear in the same
workspace listing and can be downloaded or removed from the Workspace panel.

```text
a1b2c3d4e5f6_reads.fastq
b2c3d4e5f6a1_reads.fastq
```

Keep this distinction:

```text
uploads/   original files provided through the web UI
outputs/   files generated by other tools
runs/      pipeline job records, input copies, and outputs
```

Pipeline workers stage verified copies of selected uploads under
`runs/<job-id>/inputs/` before execution.

## Usage Examples

Use these examples directly in the web chat box.

### Biology Chat / Knowledge QA

Use this for general explanations that do not need file output or live database
retrieval.

```text
What is GC content?
```

```text
Explain the difference between nucleotide sequence alignment and protein sequence alignment.
```

```text
What is the biological meaning of an open reading frame?
```

If you need citations, current records, downloaded files, or deterministic
analysis, ask for a specific Pipeline2Agent tool such as NCBI retrieval, species
report, sequence analysis, or BLAST.

### NCBI Retrieval

Use this to search or download public NCBI/Entrez sequence records, FASTA files,
metadata CSVs, PubMed records, nucleotide records, protein records, or accession
records.

```text
Download 10 records phiX174 genes A G
```

```text
Download 5 records organism "Escherichia phage phiX174" genes A G
```

```text
Download 10 records phiX174 genes A G from 2020-2024
```

```text
Search NCBI nucleotide for NC_001422 and download FASTA metadata
```

Typical output:

```text
Answer summary
FASTA file paths
Metadata CSV paths
NCBI query information
Evidence and trace details
```

### UniProt / PDB Database Lookup

Use this for lightweight database search without downloading a structure file.

```text
Search UniProt for BRCA1 human
```

```text
Find 3 UniProt records for BRCA1 human
```

```text
Find 3 PDB entries for hemoglobin
```

Typical output:

```text
Record IDs
Names or titles
Organism or source
Database URLs
```

### PDB Structure Download

Use this to download a specific structure file from RCSB PDB.

```text
Download PDB structure 1A3N as cif
```

```text
Download PDB 1A3N as pdb
```

```text
Fetch PDB 3GOU as cif
```

Downloaded structures are stored in the active session file directory by
default. They can be reused later in the same web chat session.

### Biology / Sequence / Genome Analysis

Use the regular sequence workflow for deterministic sequence statistics, GC
content, base counts, FASTA summaries, and ORF detection. Use the Biopython
workflow for reverse complements, translation, and GenBank feature summaries.
It accepts FASTA input but does not replace the sequence metrics workflow.

```text
Translate the uploaded sample.fasta in reading frame 1
```

```text
Show the GenBank features in uploads/record.gb
```

```text
Find the reverse complement of ATGCGTAA
```

```text
Analyze PhiX174 segment sequence GAGTTTTATCGCTTCCATGACGCAGAAGTTAACACTTTCGGATATTTCTGATGAGTCGAAAAATTATCTT
```

```text
Find ORFs and GC content for PhiX174 segment sequence GAGTTTTATCGCTTCCATGACGCAGAAGTTAACACTTTCGGATATTTCTGATGAGTCGAAAAATTATCTT
```

```text
Analyze FASTA file data/ncbi_downloads_phix174/phix174_A.fasta
```

After downloading FASTA in the same web session:

```text
Analyze the latest FASTA
```

Typical output:

```text
Record count
Sequence length
GC content
Base or residue counts
ORF count
```

### Genome Map / Genome Structure Figure

Use this to create a visual 1D genome map from FASTA, GenBank, or GFF input.
The web UI renders generated SVG figures inline.

```text
Show genome structure for FASTA file data/ncbi_downloads_phix174/phix174_A.fasta as a circular map
```

```text
Create a linear genome map for FASTA file data/ncbi_downloads_phix174/phix174_A.fasta
```

After downloading FASTA in the same web session:

```text
Show genome structure of the latest FASTA as a circular map
```

Typical output:

```text
Genome length
Feature counts
Gene/CDS/ORF counts
SVG genome map shown in the answer
```

### Protein Structure Analysis

Use this to analyze local or already downloaded PDB/mmCIF files for atoms,
chains, residues, ligands, water, models, method, and resolution. A PDB ID is
downloaded with `pdb_download` first, then passed to this analysis tool.

Download and analyze a PDB ID:

```text
Download and analyze PDB structure 3GOU
```

Analyze a local structure file:

```text
Analyze structure file runtime/sessions/demo/outputs/structures/1A3N.cif
```

After downloading a structure in the same web session:

```text
Analyze the latest structure
```

Typical output:

```text
Atom count
Chain count
Residue count
Ligands
Experimental method
Resolution
Collapsible 3D viewer for .cif, .mmcif, and .pdb files
```

### BLAST Search

Use this only when you explicitly want NCBI BLAST sequence similarity search.

Submit a BLAST request:

```text
BLAST PhiX174 segment sequence GAGTTTTATCGCTTCCATGACGCAGAAGTTAACACTTTCGGATATTTCTGATGAGTCGAAAAATTATCTT with blastn database nt
```

Submit and wait for hits:

```text
BLAST PhiX174 segment sequence GAGTTTTATCGCTTCCATGACGCAGAAGTTAACACTTTCGGATATTTCTGATGAGTCGAAAAATTATCTT with blastn database nt and wait
```

Poll an existing RID:

```text
Poll BLAST RID ABCD123456 and return hits
```

BLAST uses the public NCBI BLAST URL API. Waiting for BLAST results can take
time.

### File Inspection

Use this to inspect local FASTA, CSV, TSV, Markdown, or text files.

```text
Inspect file data/ncbi_downloads_phix174/phix174_A.fasta
```

```text
Inspect file data/ncbi_downloads_phix174/phix174_A.metadata.csv
```

```text
Inspect file runs/<job-id>/outputs/report.md
```

Typical output:

```text
File type
File size
Line count
Record or row count
Preview lines
```

### PDF Document Reading

Upload a selectable-text PDF to the current workspace, then ask a question
about it or request a summary:

```text
Summarize my uploaded Paper2Agent.pdf and cite the relevant pages
```

Pipeline2Agent extracts the PDF in bounded, page-aware chunks and uses the page
markers in its answer. Long documents may require several extraction calls.
Scanned PDFs need OCR before their contents can be summarized.

### Species Report

Use this for a trusted-source report using PubMed, trusted web collection, RAG,
multiple model opinions, synthesis, and Markdown report output.

```text
Create a trusted-source species report about PhiX174 with PubMed and RAG
```

```text
Create a species report about PhiX174 focusing on genome structure and host range
```

```text
Summarize SARS-CoV-2 host range and genome structure using trusted sources
```

Typical output:

```text
Narrative answer
Source summaries
Citation/evidence details
Markdown report path
Evidence caveats if the source material is incomplete
```

### Pipeline Runner

Pipeline2Agent discovers registered workflows under `tools/runtime_tools/pipelines/`
and uses `pipeline_shell` to plan, execute, monitor, and collect their results.
The [pipeline architecture reference](architecture.md#pipeline-runtime) contains
the command protocol, file-role handling, manifest contract, engine requirements,
and instructions for [adding a pipeline](architecture.md#adding-a-pipeline).

First discover the available workflows:

```text
List the available pipelines and their required inputs.
```

For a demonstration using bundled synthetic data:

```text
Run the sequence_qc_demo example and summarize its metrics.
```

For your own data, upload files to the current session and mention the filenames
and their roles in the request. The agent discovers the matching workspace
paths before it creates the validated plan:

```text
Run sequence_qc_demo with my reads.fastq as reads and metadata.tsv as metadata, with min_length 8. Return the results.
```

The agent discovers paths, selects inputs, and creates a validated plan. Missing
inputs lead to a clarification request. Filename conventions can help identify
roles, but there is no built-in R1/R2 classifier; provide explicit mappings
when filenames or sample assignments are ambiguous. Bundled files are used only
when an example is requested.

Real execution pauses for approval of the saved plan. After approval, the job
runs in a local worker. The agent can wait briefly and collect successful
outputs, or report the job ID and status for a longer job. Review existing
outputs in the same chat without rerunning the workflow:

```text
Check the status of job <job-id> and collect its results if it succeeded.
```

Results provide workspace file paths, metrics, bounded table previews, and a
ZIP bundle. The agent can summarize these in its answer; the Workspace panel
provides file downloads. Original uploads remain under `uploads/`; the worker
uses verified input copies under `runs/<job-id>/inputs/` and writes declared
outputs under `runs/<job-id>/outputs/`.

Other bundled examples can be requested explicitly by name:

```text
Run sequence_normalization_snakemake_demo with its bundled example data as a dry run with 2 cores.
```

```text
Run sequence_normalization_nextflow_demo with its bundled example data and summarize the results.
```

```text
Run dna_analysis_demo with its bundled example data and summarize the results.
```

The selected pipeline supplies its execution container and workflow
dependencies. Shell pipelines do not support `--dry-run`; planning validates
their declared inputs and settings without executing the workflow. Snakemake,
Nextflow, and WDL bundles have engine-specific validation modes described in
the architecture reference.

`dna_analysis_demo` is an educational demo: its alignment and variant outputs use a
positional comparison. Its tree outputs are optional; ask to disable them or
set `emit_phylogenetic_tree=false` when planning.

## Multi-Turn Workspace Usage

The web UI is the best interface for workflows that reuse files across turns.
Examples:

```text
Download 10 records phiX174 genes A G
```

Then:

```text
Analyze the latest FASTA
```

Or:

```text
Download PDB structure 1A3N as cif
```

Then:

```text
Analyze the latest structure
```

This works because the web session keeps the SDK sandbox workspace. Separate CLI
commands do not automatically share the same session unless you explicitly use
the same API session.

## Notes

- The web UI files live in `web_ui/`.
- `interfaces/web.py` serves HTTP routes and the browser UI.
- The web UI is for development and local-network use, not public internet
  deployment.
- The Stop button in the browser stops waiting for the current response in the
  UI. It is not a full backend process killer.
