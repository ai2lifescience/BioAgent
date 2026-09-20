# Generic Snakemake Pipeline Environment

## Requirements

The pipeline runtime requires:

- Python 3.10 or newer.
- Snakemake 8.0 or newer.
- PyYAML 6.0 or newer.

The workflow uses only Python standard-library modules for its analysis and
does not require Docker, network access, workflow-managed Conda environments,
or external bioinformatics tools.

## Pipeline2Agent environment

From the repository root:

```bash
conda create -n agent python=3.12 -y
conda activate agent
python -m pip install -r requirements.txt
```

## Minimal standalone environment

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install "snakemake>=8.0" "PyYAML>=6.0"
```

Verify the environment:

```bash
snakemake --version
python -c "import yaml; print(yaml.__version__)"
```

## Workflow

### Function

This pipeline demonstrates a small sequence-analysis workflow implemented with
Snakemake. It cleans and combines the input FASTA sequence content, calculates
basic metrics, and creates a Markdown report.

```text
FASTA + metadata
  -> normalize sequence characters
  -> calculate length, GC percentage, and minimum-length status
  -> write normalized FASTA, metrics, and report
```

### Inputs

- `input_path`: required FASTA input (`.fa`, `.fasta`, or `.fna`).
- `metadata_path`: required TSV or CSV metadata table. The example workflow
  reports its number of data rows.

All non-header FASTA lines are combined, non-sequence punctuation is removed,
and the resulting sequence is converted to uppercase.

### Outputs

- `normalized.fasta`: combined normalized sequence labeled with the configured
  pipeline label and segment.
- `metrics.json`: sequence length, GC percentage, metadata row count,
  minimum-length result, and analysis parameters.
- `report.md`: human-readable summary of the metrics.

The runtime writes declared outputs into the per-job output directory and
returns them through `agent-pipeline results --job-id <job_id>`.
