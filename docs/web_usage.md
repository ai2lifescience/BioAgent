# BioAgent Web UI Usage

This guide shows how to run the BioAgent browser interface locally or from
another computer on the same local network.

## Start Local Web UI

Use this when you only need to open BioAgent on the same machine:

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

Open `/assistant-demo` to see a sample workspace with BioAgent mounted as a
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
<div id="bioagent-drawer"></div>
<script src="https://bioagent.example.org/static/assistant-embed.js"></script>
<script>
  const drawer = BioAgentDrawer.mount({
    target: document.getElementById("bioagent-drawer"),
    src: "https://bioagent.example.org/assistant",
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
    type: "bioagent-context",
    context: { project_id: "123", sample_id: "456", result_type: "summary" }
  },
  "https://bioagent.example.org"
);
```

Use the exact BioAgent origin as the second argument and validate `event.origin`
in a custom embedding implementation. The assistant accepts text labels only.

For a proxy mount such as `/bioagent/assistant`, route the whole `/bioagent/`
prefix to BioAgent and rewrite that prefix before forwarding, including static
files and API requests. The page resolves these URLs relative to its mount
point. Disable proxy buffering for streaming responses. Public website
integration still needs that website's authentication and session permissions;
this page does not add them.

The separate page keeps its conversation while it is open. Reloading or choosing
**New chat** starts a new session; context labels stay on screen. **Stop waiting**
disconnects the response stream; work already started on the server may continue.

## Start For Local Network Access

Use this when another PC on the same LAN should open the BioAgent page:

Set the OpenRouter proxy once in your terminal, then start the server:

```bash
conda activate openaisdk
export BIOAGENT_PROXY=socks5h://127.0.0.1:10801
python -B -m interfaces.web --host 0.0.0.0 --port 8000
```

`ALL_PROXY` is not required when `BIOAGENT_PROXY` is set. You do not need to
unset `HTTP_PROXY` or `HTTPS_PROXY` for OpenRouter requests. Use `http://` if
your proxy provides an HTTP listener; use `socks5h://` for the SOCKS5 listener
shown above.

Alternatively, set the proxy for just the server process after activating
`openaisdk`:

```bash
BIOAGENT_PROXY=socks5h://127.0.0.1:10801 \
  python -B -m interfaces.web --host 0.0.0.0 --port 8000
```

For direct OpenRouter connections, use:

```bash
BIOAGENT_DISABLE_PROXY=1 \
  python -B -m interfaces.web --host 0.0.0.0 --port 8000
```

`BIOAGENT_DISABLE_PROXY=1` takes priority over proxy settings. If you previously
exported it, run `unset BIOAGENT_DISABLE_PROXY` before switching back to a
proxy. Restart a running server after changing its environment.

These BioAgent settings control OpenRouter model and embedding requests.
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

You can also list BioAgent web processes:

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
FASTA file in one message and then ask BioAgent to analyze the latest FASTA in a
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
  or `Run generic_shell on metadata.csv`. BioAgent resolves the workspace file
  and supplies the path required by the selected tool.

Workspace files are stored in the active SDK sandbox session:

```text
runtime/sessions/<session_id>/uploads/
```

If the same filename is uploaded more than once, BioAgent avoids overwriting by
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
analysis, ask for a specific BioAgent tool such as NCBI retrieval, species
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

### Sequence / Genome Analysis

Use this for deterministic sequence statistics, GC content, base counts, FASTA
summaries, and ORF detection.

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

Use this to analyze local or downloaded PDB/mmCIF files for atoms, chains,
residues, ligands, water, models, method, and resolution.

Analyze a PDB ID directly:

```text
Analyze the structure of 3GOU
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

BioAgent discovers registered workflows under `tools/runtime_tools/pipelines/`
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
Run the example_sequence_qc example and summarize its metrics.
```

For your own data, upload files to the current session and mention the filenames
and their roles in the request. The agent discovers the matching workspace
paths before it creates the validated plan:

```text
Run example_sequence_qc with my reads.fastq as reads and metadata.tsv as metadata, with min_length 8. Return the results.
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
Run generic_snakemake with its bundled example data as a dry run with 2 cores.
```

```text
Run generic_nextflow with its bundled example data and summarize the results.
```

```text
Run generic_bio with its bundled example data and summarize the results.
```

The corresponding engines and dependencies must be installed. Shell pipelines
do not support `--dry-run`; planning validates their declared inputs and
settings without executing the workflow. Snakemake, Nextflow, and miniwdl have
engine-specific validation modes described in the architecture reference.

`generic_bio` is an educational demo: its alignment and variant outputs use a
positional comparison. Its tree outputs are optional; ask to disable them or
set `emit_phylogenetic_tree=false` when planning.

### Example Tool / Smoke Test

Use this when you want to confirm tool calling works.

```text
Please test tool calling by running the example tool with message hello and tag smoke.
```

```text
Run the example tool with message hello world and tag uppercase-test uppercase.
```

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
