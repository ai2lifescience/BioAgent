# DNA analysis template

This educational shell template demonstrates a complete DNA read-analysis
artifact set without external bioinformatics programs. It validates FASTQ
reads, calculates read/base QC, filters reads, performs a deterministic
positional comparison to one reference, and writes alignments, consensus,
variant-like records, figures, and reports.

The positional comparison is a format demonstration. It is not a replacement
for a validated aligner or variant caller.

## Requirements

- Bash and Python 3.9 or newer;
- PyYAML and Matplotlib (`python -m pip install PyYAML matplotlib`);
- no network, database, Docker, or external bioinformatics executable.

The dependency belongs in the pipeline container when the bundle is run through
BioAgent. A standalone virtual environment is sufficient:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install "PyYAML>=6" "matplotlib>=3"
```

## Inputs, parameters, and outputs

The runtime YAML requires `input_path` (single-end FASTQ with Phred+33
qualities), `reference_path` (one DNA FASTA record), and `metadata_path` (TSV or
CSV with a unique `sample_id`). Parameters under `params` are:

- `sample_id`, `min_length`, `min_mean_quality`, and `min_base_quality`;
- `min_alt_fraction`, `min_alt_depth`, and `plot_dpi`;
- `emit_phylogenetic_tree` (default `true`).

The workflow writes `filtered_reads.fastq`, `alignments.sam`,
`consensus.fasta`, `variants.vcf`, `read_qc.tsv`, `sample_summary.tsv`,
`coverage.tsv`, `variant_summary.tsv`, `qc_overview.png`, `coverage.png`,
`variant_allele_fraction.png`, `metrics.json`, `report.md`, and `report.html`.
It optionally writes `phylogenetic_tree.nwk` and `phylogenetic_tree.png`.

## Standalone run

The template intentionally has no project-level config file. Create one beside
the bundle and run the included shell entrypoint:

```bash
cat > config.local.yaml <<'YAML'
label: template_bio
input_path: data/input/example_reads.fastq
reference_path: data/input/example_reference.fasta
metadata_path: data/input/example_samples.tsv
report_path: output/report.md
html_report_path: output/report.html
metrics_path: output/metrics.json
filtered_fastq_path: output/filtered_reads.fastq
read_qc_path: output/read_qc.tsv
sample_summary_path: output/sample_summary.tsv
coverage_path: output/coverage.tsv
alignment_sam_path: output/alignments.sam
consensus_fasta_path: output/consensus.fasta
variants_vcf_path: output/variants.vcf
variant_table_path: output/variant_summary.tsv
qc_figure_path: output/qc_overview.png
coverage_figure_path: output/coverage.png
variant_figure_path: output/variant_allele_fraction.png
phylogenetic_tree_path: output/phylogenetic_tree.nwk
phylogenetic_tree_figure_path: output/phylogenetic_tree.png
params:
  sample_id: sample_demo
  min_length: 12
  min_mean_quality: 20
  min_base_quality: 20
  min_alt_fraction: 0.6
  min_alt_depth: 2
  plot_dpi: 140
  emit_phylogenetic_tree: true
YAML
./run.sh config.local.yaml
```

## BioAgent use and limitations

Use `pipeline_name: template_bio` and provide `reads`, `reference`, and
`metadata`:

```text
Run template_bio with its bundled example data and collect the results.
```

Each read is assumed to start at reference position 1. The synthetic SAM, VCF,
consensus, and tree are demonstrations only and must not support research,
clinical, or epidemiological conclusions.
