# Shell pipeline template

This dependency-light shell template joins sequence IDs to a TSV/CSV metadata
table, normalizes the input text, and writes subtype assignments, metrics, and
a report. It follows the standalone bundle shape used by the runtime engines.

## Requirements

- Bash and standard utilities: `cp`, `dirname`, `mkdir`, `mv`, `sed`, `tr`, and
  `wc`;
- Python 3.9 or newer with PyYAML (`python -m pip install PyYAML`).

It does not require Docker, network access, a database, or external
bioinformatics tools. Install these dependencies in the pipeline container or
in a small standalone virtual environment; they are not added to BioAgent's
base requirements.

## Inputs and behavior

The runtime YAML requires `input_path` and `metadata_path`. The sequence input
may be plain text, FASTA, or FASTQ. FASTA IDs come from the first value after
`>`; FASTQ IDs come from the first value after `@`; other text uses the first
value on each non-empty line.

The metadata must contain configurable `sequence_id_column` and
`subtype_column` fields (defaults: `sequence_id` and `subtype`). Missing
subtypes receive `missing_subtype` (default: `unassigned`). Duplicate sequence
IDs, duplicate metadata IDs, missing columns, and malformed FASTQ records stop
the run. Parameters are `normalize_mode` (`whitespace`, `lines`, or `raw`) and
`uppercase`.

## Standalone run

Create a small runtime YAML beside the bundle and call `run.sh`:

```bash
cat > config.local.yaml <<'YAML'
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
YAML
./run.sh config.local.yaml
```

## Outputs and BioAgent use

The output files are `subtypes.tsv` (one row per input sequence),
`normalized.txt`, `metrics.json`, and `report.md`. Use
`pipeline_name: template_shell` with `reads` and `metadata`, or request:

```text
Run template_shell with its bundled example data and collect the results.
```

The template performs deterministic metadata joining; it does not infer
biological subtypes or sequence similarity.
