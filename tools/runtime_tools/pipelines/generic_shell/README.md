# Generic Shell Pipeline Environment

## Requirements

The pipeline runtime requires:

- Bash with standard Unix utilities: `cat`, `cp`, `dirname`, `mkdir`, `mv`,
  `sed`, `tr`, and `wc`.
- Python 3.9 or newer.
- PyYAML 6.0 or newer.

It does not require Docker, network access, or external bioinformatics command
line tools.

## BioAgent environment

The project environment already includes the required dependency. From the
repository root:

```bash
conda create -n bioagent python=3.12 -y
conda activate bioagent
python -m pip install -r requirements.txt
```

## Minimal standalone environment

To run only this pipeline, a small virtual environment is sufficient:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install "PyYAML>=6.0"
```

Verify the required commands and Python package:

```bash
bash --version
python -c "import yaml; print(yaml.__version__)"
```

## Workflow

### Function

This pipeline joins sequence records with a TSV or CSV metadata table and
writes the subtype assigned to each sequence. It is a small shell-based
BioAgent pipeline example that can also run directly from Bash.

The processing flow is:

```text
sequence file + metadata table
  -> extract sequence IDs
  -> match IDs to metadata rows
  -> normalize the sequence input
  -> write subtype assignments, metrics, and a report
```

### Inputs

The pipeline requires two inputs:

- `input_path`: FASTA, FASTQ, or whitespace-delimited sequence text.
- `metadata_path`: TSV or CSV metadata containing sequence ID and subtype
  columns.

FASTA IDs are taken from the first value after `>` in each header. FASTQ IDs
are taken from the first value after `@` in each record header. For other text,
the first value on each non-empty line is used as the sequence ID.

The metadata column names are configurable with `sequence_id_column` and
`subtype_column`. A sequence without a populated metadata subtype receives the
configured `missing_subtype` value, which defaults to `unassigned`.

Duplicate sequence IDs, duplicate metadata IDs, missing metadata columns, and
invalid FASTQ record structures stop the run with an error.

### Outputs

The pipeline produces:

- `subtypes.tsv`: one `sequence_id` and `subtype` row per input sequence, in
  input order.
- `normalized.txt`: normalized sequence input; the path and extension are
  configurable.
- `metrics.json`: input size and subtype-assignment counts.
- `report.md`: a human-readable run summary.

The runtime writes declared outputs into the per-job output directory and
returns them through `bioagent-pipeline results --job-id <job_id>`.

Example subtype output:

```tsv
sequence_id	subtype
strain1	subtype1
strain2	subtype1
strain3	subtype1
```
