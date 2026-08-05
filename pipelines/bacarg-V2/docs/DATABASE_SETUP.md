# MEGARes 3.0 database setup

The deployer supplies licensed/official MEGARes nucleotide FASTA and CSV/TSV annotation metadata. Normal pipeline runs never download or modify a database.

```bash
python -m scripts.prepare_megares_v3 \
  --fasta <official-nucleotide-fasta> \
  --metadata <official-annotation-table> \
  --datadir <deployment-chosen-database-root>
```

The script rewrites headers as `DB~~~GENE~~~ACCESSION~~~RESISTANCE`, creates `<datadir>/<database_name>/sequences`, invokes `makeblastdb`, and writes normalized metadata plus `database_manifest.json`. Existing targets require `--force`. `--dry-run` only shows the command. Use repeated `--field-map logical=source_header` when download headers differ.

Connect the project with `BACARG_ABRICATE_DATADIR`, `BACARG_MEGARES_METADATA`, and optionally `BACARG_MEGARES_MANIFEST`, or equivalent YAML values. The database can live anywhere chosen by the deployer; the project carries no database.
