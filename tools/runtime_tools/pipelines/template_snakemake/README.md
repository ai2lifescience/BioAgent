# Snakemake pipeline template

This educational Snakemake bundle cleans and combines FASTA sequence content,
calculates basic sequence/metadata metrics, and writes a normalized FASTA, JSON
metrics, and Markdown report.

## Requirements

- Python 3.10 or newer;
- Snakemake 8 or newer;
- PyYAML is useful for the BioAgent runtime, although the Snakefile itself uses
  only Python standard-library modules.

The workflow does not need Docker, network access, external bioinformatics
tools, or workflow-managed Conda environments. A minimal standalone setup is:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install "snakemake>=8" "PyYAML>=6"
snakemake --version
```

## Inputs and parameters

`input_path` is a FASTA (`.fa`, `.fasta`, or `.fna`) and `metadata_path` is an
optional TSV/CSV table; the example reports its number of data rows. Parameters
are `label`, `subtype`, `segment`, `time`, `analysis_mode`, and `min_length`.
All non-header FASTA lines are combined, punctuation is removed, and the
sequence is uppercased.

## Standalone run

The bundle has no project-level config file. Create a Snakemake config and run
the Snakefile directly:

```bash
cat > config.local.yaml <<'YAML'
label: template_snakemake
input_path: data/input/sequences_segment1.fasta
metadata_path: data/input/metadata.tsv
output_dir: output
normalized_fasta_path: output/normalized.fasta
metrics_path: output/metrics.json
report_path: output/report.md
params:
  subtype: subtype1
  segment: segment1
  time: all-time
  analysis_mode: example
  min_length: 0
YAML
snakemake --snakefile Snakefile --configfile config.local.yaml --cores 1
```

## BioAgent use and limitations

Use `pipeline_name: template_snakemake` with `sequence` and `metadata`, or
request:

```text
Run template_snakemake with its bundled example data and collect the results.
```

The output metrics are engine-test artifacts; they do not provide validated
sequence analysis or biological conclusions.
