# BacFunc Agent Description

BacFunc 0.2.0 accepts supplied metagenome contig FASTA, single-end FASTQ, paired R1/R2 FASTQ, and directory batches. `genome` and `assemble` retain the existing Prokka plus eggNOG-mapper workflow. `reads` runs Trimmomatic, converts retained reads to collision-free FASTA query identifiers, performs DIAMOND blastx against the deployed `eggnog_proteins.dmnd`, and passes the resulting four-column seed-ortholog table to eggNOG-mapper 2.1.15 in `no_search` mode.

Stable outputs are `gene_annotations.tsv`, `annotation_terms.tsv`, `status.json`, `manifest.json`, and `qc.json`. Reads are aggregated by real eggNOG seed-ortholog accession, with `supporting_reads`, mean identity, mean query coverage, and mean bit score. Zero annotations remain successful and schema-valid.

BacFunc preserves source annotation namespaces and does not calculate abundance, bin contigs, assign taxonomy, or write automated biological conclusions.