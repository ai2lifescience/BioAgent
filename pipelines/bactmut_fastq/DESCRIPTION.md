# BactMut FASTQ

BactMut FASTQ maps bacterial FASTQ reads to a reference with `minimap2`, sorts
and measures coverage with `samtools`, calls variants with `bcftools`, filters
low-coverage and recombination-dense SNP positions, creates a cross-sample SNP
matrix, annotates variants, and optionally constructs an IQ-TREE phylogeny.

## Inputs

- `input_path`: directory containing single-end or paired-end FASTQ files with
  `.fastq`, `.fq`, `.fastq.gz`, or `.fq.gz` suffixes.
- `reference_path`: local reference FASTA used when
  `params.reference_mode: local`.
- `params.reference_mode`: `local`, `species`, or `taxonid`.

Paired reads are detected from common `_R1`/`_R2`, `.R1`/`.R2`, `_1`/`_2`, and
similar names. Species and Taxonomy ID modes require a local GTDB database
configured through `GTDB_DB_PATH` and `GTDB_METADATA_PATH`.

## Main outputs

- `report.md` and `metrics.json`: BioAgent result summary and structured metrics.
- `matrix.tsv`: filtered cross-sample SNP matrix.
- `variants.tsv` and `variants_summary.txt`: annotated variants and counts.
- `bcftools/`: per-sample SAM, sorted/indexed BAM, and VCF intermediates.
- `final_tree.nwk` and IQ-TREE files: optional phylogenetic outputs.

Tree outputs are optional because no tree can be built when no SNP survives, and
IQ-TREE may not be installed. Required BioAgent outputs are still produced in
those cases.
