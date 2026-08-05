# VFDB core database setup

The deployer supplies official VFDB core nucleotide FASTA and matching CSV/TSV metadata. Normal pipeline runs never download or modify a database.

```bash
python -m scripts.prepare_vfdb_core \
  --fasta <official-core-nucleotide-fasta> \
  --metadata <official-annotation-table> \
  --datadir <deployment-chosen-database-root>
```

The script creates a custom `vfdb_core` directory, rewrites ABRicate-compatible headers, invokes `makeblastdb`, and writes normalized metadata plus a manifest. Existing targets require `--force`; `--dry-run` only plans. Repeated `--field-map logical=source_header` options resolve download-specific columns without fuzzy guesses.

Set `BACVF_ABRICATE_DATADIR`, `BACVF_VFDB_METADATA`, and optionally `BACVF_VFDB_MANIFEST`, or their YAML equivalents. The database may be stored anywhere selected by the deployer; no large database is part of the project.
