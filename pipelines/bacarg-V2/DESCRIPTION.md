# BacARG Agent Description

BacARG 0.2.0 accepts supplied metagenome contig FASTA, single-end FASTQ, paired R1/R2 FASTQ, and directory batches. `genome` and `assemble` retain the existing Prokka/ABRicate workflows. `reads` runs Trimmomatic followed by minimap2 short-read mapping directly against the deployed MEGARes nucleotide `sequences` file, then joins the existing metadata.

Stable outputs are `arg_hits.tsv`, `arg_hits.jsonl`, `status.json`, `manifest.json`, and `qc.json`. In reads mode, contig coordinates, strand, locus tag, and Prokka context are empty. `supporting_reads`, cumulative reference coverage, and depth are computed from real alignments. Zero hits remain successful and schema-valid.

The pipeline reports sequence-homology candidates only. It does not confirm resistance-conferring point mutations, infer phenotype, quantify abundance, bin contigs, or assign hits to species.