# BacVF output schema

`vf_hits.tsv` has this stable order:

`sample_id, contig, start, end, strand, vf_id, gene, accession, factor_name, category, subcategory, associated_pathogen, product, pct_identity, pct_coverage, coverage, gaps, supporting_reads, depth, database_name, database_version, locus_tag, prokka_gene, prokka_product`.

Assemble/genome rows retain one-based ABRicate coordinates and Prokka context; their reads-only `supporting_reads` and `depth` fields are empty. Reads-mode rows aggregate passing PAF alignments by deployed reference factor. `pct_coverage` is cumulative covered reference percentage, `coverage` is `covered_bases/reference_length`, and `depth` is aligned bases divided by reference length. `contig`, `start`, `end`, `strand`, `locus_tag`, `prokka_gene`, and `prokka_product` are empty in reads mode.

`vf_hits.jsonl` contains the same fields. Empty biological results produce a header-only TSV and empty JSONL. Associated-organism metadata remains descriptive database provenance.

`status.json` is authoritative. `manifest.json` records input hashes, argument arrays, actual branch tools, database provenance, and YAML scientific parameters. `qc.json` records input metadata; reads mode adds raw/trimmed read and base counts, mean read length, and retained-read percentage while marking assembly and gene prediction not applicable.

Schema version 1.1 records `input_type` and `analysis_mode` in status, manifest, and QC. Each batch sample directory contains the complete single-sample schema.