# BactMut FASTA

BactMut FASTA compares one or more assembled bacterial genomes against a
reference, calls SNPs, filters low-coverage and recombination-dense positions,
builds a filtered SNP alignment, annotates variants, and optionally constructs
an IQ-TREE phylogeny.

## Inputs

- `input_path`: one query genome FASTA or a directory of query FASTAs with
  `.fasta`, `.fa`, `.fna`, or `.fas` suffixes. It is not used when
  `params.simulate` is `true`.
- `reference_path`: local reference FASTA used when
  `params.reference_mode: local`.
- `params.reference_mode`: `local`, `species`, or `taxonid`.

Species and Taxonomy ID modes resolve references from a local GTDB database and
require `GTDB_DB_PATH` and `GTDB_METADATA_PATH` in the runner environment.

## Main outputs

- `report.md` and `metrics.json`: BioAgent result summary and structured metrics.
- `filtered_snp_matrix.fasta`: filtered SNP alignment.
- `variants.tsv` and `variants_summary.txt`: annotated variants and counts.
- `summary.txt`: pipeline parameters, timings, filter counts, and tree status.
- `initial_snp_list.csv` and `mutation_report.csv`: detailed call tables.
- `final_tree.nwk` and IQ-TREE files: optional phylogenetic outputs.

Tree outputs are optional because no tree can be built when no SNP survives, and
IQ-TREE may not be installed. Required BioAgent outputs are still produced in
those cases.
