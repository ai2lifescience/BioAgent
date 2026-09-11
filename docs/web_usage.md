# BioAgent Web UI Usage

This guide shows how to run the BioAgent browser interface locally or from
another computer on the same local network.

## Start Local Web UI

Use this when you only need to open BioAgent on the same machine:

```bash
python -B -m interfaces.web --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000
```

`127.0.0.1` means only this computer can access the web page.

## Start For Local Network Access

Use this when another PC on the same LAN should open the BioAgent page:

```bash
python -B -m interfaces.web --host 0.0.0.0 --port 8000
```

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
5. Check the answer, evidence, verification, trace, and generated artifacts below
   the response.

The left session sidebar lets you create a new chat, switch between saved local
browser sessions, and delete sessions.

The same session can reuse downloaded artifacts. For example, you can download a
FASTA file in one message and then ask BioAgent to analyze the latest FASTA in a
later message.

## Upload Files

Use the `Uploads` panel in the sidebar when you want the web session to keep
input files that can be reused by skills or pipelines.

1. Click `Upload`.
2. Select one or more files.
3. The uploaded files appear in the current chat session's upload list.
4. Set `Input label` to the pipeline slot or tool argument name, for example
   `input_path`, `sequence`, or `metadata`.
5. Click `Use` beside a file to insert the labeled path into the message box.

```text
input_path: "runtime/sessions/<session_id>/artifacts/uploads/<filename>"
```

When BioAgent asks for missing pipeline inputs, the `Input label` box is filled
from the requested slot names in that answer, such as `reads`, `sequence`, or
`metadata`. The web UI uses structured `requested_inputs` from the agent result
when available, so it does not depend on parsing the displayed Markdown text.

If BioAgent just asked for missing pipeline input and the message box is empty,
`Use` prefills a complete pipeline request:

```text
Run pipeline with pipeline_name: generic_shell input_path: "runtime/sessions/<session_id>/artifacts/uploads/reads.fastq"
```

Then combine that path with a normal request:

```text
Run the shell pipeline with input_path: "runtime/sessions/<session_id>/artifacts/uploads/reads.fastq"
```

```text
Inspect file input_path: "runtime/sessions/<session_id>/artifacts/uploads/metadata.tsv"
```

Uploaded files are stored as immutable session artifacts:

```text
runtime/sessions/<session_id>/artifacts/uploads/
```

If the same filename is uploaded more than once, BioAgent avoids overwriting by
adding a suffix, for example:

```text
reads.fastq
reads_2.fastq
reads_3.fastq
```

Keep this distinction:

```text
uploads/   original files provided through the web UI
pipelines/ pipeline outputs and generated runtime configs
```

Pipeline runners use uploaded files directly from `uploads/`.

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
analysis, ask for a specific BioAgent skill such as NCBI retrieval, species
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

Downloaded structures are stored in the active session artifact directory by
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
Analyze structure file runtime/sessions/demo/artifacts/structures/1A3N.cif
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
Inspect file runtime/sessions/<session_id>/artifacts/pipelines/generic_shell/<run_id>/report.md
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
Verification warnings if evidence is incomplete
```

### Pipeline Runner

Use this to run approved pipeline folders under `pipelines/`.

Default shell pipeline:

```text
Run the shell pipeline
```

Specific shell pipeline folder:

```text
Run the shell pipeline with pipeline_name: generic_shell
```

Default Snakemake pipeline dry run:

```text
Run the snakemake pipeline dry-run with 2 cores
```

Specific Snakemake pipeline folder:

```text
Run the snakemake pipeline with pipeline_name: generic_snakemake dry-run with 2 cores
```

Default Nextflow pipeline:

```text
Run the Nextflow pipeline
```

For `generic_nextflow`, use named input paths:

```text
Run pipeline with pipeline_name: generic_nextflow sequence: "runtime/sessions/<session_id>/artifacts/uploads/sequences.fasta" metadata: "runtime/sessions/<session_id>/artifacts/uploads/metadata.tsv"
```

For uploaded inputs:

```text
1. Upload files in the Uploads panel.
2. Set `Input label` to the requested slot name, or let BioAgent fill it from
   the latest missing-input answer.
3. Click Use to insert the selected input label and file path.
4. For multiple inputs, change `Input label` to the next slot name and click
   Use again.
5. Send the completed pipeline request.
```

If a selected pipeline requires input files and no valid path is provided in the
request, BioAgent asks for the missing paths instead of starting the pipeline.
The skill does not use default input files from `config.yaml`; those defaults
are only examples for the raw pipeline.

For `generic_snakemake`, use named input paths:

```text
Run pipeline with pipeline_name: generic_snakemake sequence: "runtime/sessions/<session_id>/artifacts/uploads/sequences.fasta" metadata: "runtime/sessions/<session_id>/artifacts/uploads/metadata.tsv"
```

The dependency-light `generic_bio` demo accepts three common bioinformatics
inputs and produces filtered FASTQ, demonstration SAM, consensus FASTA,
variants VCF, multiple TSV tables, three PNG figures, metrics JSON, and
Markdown and HTML reports:

```text
Run pipeline with pipeline_name: generic_bio reads: "pipelines/generic_bio/data/input/example_reads.fastq" reference: "pipelines/generic_bio/data/input/example_reference.fasta" metadata: "pipelines/generic_bio/data/input/example_samples.tsv"
```

Completed pipelines are presented as download links. The web UI does not
automatically preview figures, tables, metrics, or report contents. To request
an interpreted view in the same chat, send:

```text
Collect and show all results from this pipeline run.
```

Pipeline outputs may be conditional. `generic_bio` emits a Newick phylogenetic
tree and PNG preview by default. To disable those two outputs:

```text
Run pipeline with pipeline_name: generic_bio reads: "pipelines/generic_bio/data/input/example_reads.fastq" reference: "pipelines/generic_bio/data/input/example_reference.fasta" metadata: "pipelines/generic_bio/data/input/example_samples.tsv" emit_phylogenetic_tree false
```

Pipeline folder contract:

```text
pipelines/<pipeline_name>/runner.yaml
pipelines/<pipeline_name>/config.yaml   # default, or runner.yaml config:
pipelines/<pipeline_name>/run.sh        # shell default, or runner.yaml entrypoint:
pipelines/<pipeline_name>/Snakefile     # snakemake default, or runner.yaml snakefile:
pipelines/<pipeline_name>/main.nf       # nextflow default, or runner.yaml workflow:
pipelines/<pipeline_name>/nextflow.config # optional runner.yaml nextflow_config:
```

For multi-input pipelines, `runner.yaml` can declare named input slots:

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

Use a simple base config shape for plug-and-play agent execution:

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

BioAgent generates `config.runtime.yaml` from this base config, replaces input
paths with uploaded/session files, and resolves declared output file keys such
as `report_path` and `metrics_path` inside the per-run pipeline directory. Web
requests can override keys under `params`:

```text
Run pipeline generic_snakemake with input_path: "runtime/sessions/<session_id>/artifacts/uploads/sequences.fasta" min_length 50
```

For `engine: shell`, `pipeline_runner` uses:

```text
bash pipelines/<pipeline_name>/run.sh <run_dir>/config.runtime.yaml
```

For `engine: snakemake`, `pipeline_runner` uses:

```text
snakemake --cores <cores> --snakefile pipelines/<pipeline_name>/Snakefile --configfile <run_dir>/config.runtime.yaml
```

For `engine: nextflow`, `pipeline_runner` uses:

```text
nextflow -c pipelines/<pipeline_name>/nextflow.config run pipelines/<pipeline_name>/main.nf -params-file <run_dir>/config.runtime.yaml -work-dir <run_dir>/nextflow_work
```

The workflow publishes final files into the runtime `nextflow_output_dir`.
`runner.yaml.outputs[*].nextflow_output` maps those relative published names to
BioAgent's stable artifact paths. Dry run uses Nextflow `-preview`.

For `engine: wdl`, `pipeline_runner` uses miniwdl:

```text
miniwdl run --dir <run_dir>/wdl_engine -o <run_dir>/wdl.outputs.json pipelines/<pipeline_name>/workflow.wdl -i <run_dir>/inputs.runtime.json
```

miniwdl uses your local miniwdl runtime configuration. By default, miniwdl
expects Docker unless your environment is configured otherwise.

If the pipeline has `options.json`, BioAgent writes `options.runtime.json` in
the run directory. This keeps Cromwell-style output options compatible for later
use, while `runner.yaml.outputs` remains the output contract for the web UI.

Typical output:

```text
Pipeline status
Session input path
Session artifact output directory
Runtime config path
Runner config path
Raw config path
Report path
Metrics path
Generated files
```

Pipeline input files from the web UI stay in the current session upload folder
and are passed directly to the pipeline:

```text
runtime/sessions/<session_id>/artifacts/uploads/
```

### Example Skill / Smoke Test

Use this when you want to confirm skill calling works.

```text
Please test skill calling by running the example skill with message hello and tag smoke.
```

```text
Run the example skill with message hello world and tag uppercase-test uppercase.
```

## Multi-Turn Artifact Usage

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

This works because the web session keeps a session artifact list. Separate CLI
commands do not automatically share the same session unless you explicitly use
the same API session.

## Notes

- The web UI files live in `web_ui/`.
- `interfaces/web.py` serves HTTP routes and the browser UI.
- The web UI is for development and local-network use, not public internet
  deployment.
- The Stop button in the browser stops waiting for the current response in the
  UI. It is not a full backend process killer.
