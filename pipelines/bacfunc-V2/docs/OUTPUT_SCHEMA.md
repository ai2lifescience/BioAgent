# BacFunc output schema

`gene_annotations.tsv` begins with `sample_id`. Assemble/genome mode then preserves the exact eggNOG `#query` header order, including unknown future columns.

Reads mode preserves those eggNOG columns and appends, when not already present:

`accession, supporting_reads, mean_pct_identity, mean_query_coverage, mean_bitscore`.

Reads are aggregated by real `seed_ortholog`; both `query` and `accession` identify that database accession. No contig coordinate, strand, or locus-tag value is created. `annotation_terms.tsv` remains `sample_id, gene_id, namespace, term_id, term_name, source_column`; in reads mode, `gene_id` is the seed-ortholog accession. Multi-valued fields become distinct deterministic term rows.

Empty biological results produce header-only result tables. `status.json` is authoritative. `manifest.json` records input hashes, argument arrays, actual branch tools, database provenance, and YAML scientific parameters. `qc.json` records input metadata; reads mode adds raw/trimmed read and base counts, mean read length, and retained-read percentage while marking assembly and gene prediction not applicable.

Schema version 1.1 records `input_type` and `analysis_mode` in status, manifest, and QC. Each batch sample directory contains the complete single-sample schema.