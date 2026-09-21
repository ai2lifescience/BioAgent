# Bacterial genome mutation analysis

BactMut FASTA compares one or more assembled bacterial genomes with a reference,
calls SNPs, filters low-coverage and recombination-dense positions, builds a
filtered alignment, annotates variants, and optionally runs IQ-TREE.

## Requirements

- Bash and Python 3.9 or newer with PyYAML;
- `minimap2` when assemblies contain indels or `params.aligner` is `minimap2`;
- `iqtree2` or `iqtree` only when phylogeny is requested.

The internal aligner can handle equal-length full-genome FASTA files, so
minimap2 is optional for that restricted case. The default local-reference mode
needs no database. `species` and `taxonid` reference modes require a local GTDB
representative FASTA and metadata table exposed as `GTDB_DB_PATH` and
`GTDB_METADATA_PATH`.

## Inputs and parameters

- `input_path`: one FASTA or a directory of FASTA files with `.fasta`, `.fa`,
  `.fna`, or `.fas` suffixes;
- `reference_path`: required when `params.reference_mode: local`;
- `params.reference_mode`: `local`, `species`, or `taxonid`;
- `threads`, `aligner` (`auto|minimap2|internal`), `min_coverage`,
  `window_size`, `step_size`, and `sd_threshold`;
- optional `simulate`, `simulate_snp_rate`, `simulate_samples`, `seed`, and
  `verbose` controls for validation fixtures.

Simulation mode intentionally does not read `input_path`. Reference selection
is conditional: local mode needs `reference_path`, while the GTDB modes need the
environment variables above.

## Standalone installation and run

```bash
chmod +x run.sh
cp config.yaml config.local.yaml
# Edit input_path, reference_path, output_dir, and params.
./run.sh config.local.yaml
```

For a direct single comparison, the workflow can also be called through Python:

```bash
python workflow.py config.local.yaml
```

A deployment with GTDB reference selection should export its database paths
before running. No GTDB files are bundled.

## Outputs

Required outputs are `report.md`, `metrics.json`,
`filtered_snp_matrix.fasta`, `variants.tsv`, `variants_summary.txt`, and
`summary.txt`. Detailed `initial_snp_list.csv` and `mutation_report.csv`,
execution logs, and optional `final_tree.nwk`/IQ-TREE files are also written.
A one-sample run or a run with no surviving SNPs can complete successfully
without a tree.

## BioAgent use and limits

Use `pipeline_name: bacterial_genome_mutation_analysis` with `genomes` and a
local `reference` when applicable. A bundled request is:

```text
Run bacterial_genome_mutation_analysis with its bundled example data and collect the results.
```

This workflow is for assembled-genome comparison. Filtering thresholds,
reference choice, recombination masking, assembly errors, and optional tree
availability affect the result; it is not a clinical interpretation workflow.
