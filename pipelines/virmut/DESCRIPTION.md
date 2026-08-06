# Viral mutation calling

Virmut compares one viral genome FASTA, or a directory of single-record viral
genome FASTAs, with a local reference genome. It aligns assembled genomes with
`minimap2`, calls nucleotide variants from the resulting PAF alignments,
writes a SNP matrix and annotated variant table, and attempts phylogenetic
inference when enough samples and variable sites are available.

The normal `local` reference mode uses `reference_path`. `species` and
`taxonid` modes resolve a reference from `VIRUS_DB` and `VIRUS_METADATA`.
Tree files are optional: a successful one-sample comparison produces the core
matrix, variants, and summary even when tree inference is skipped.
