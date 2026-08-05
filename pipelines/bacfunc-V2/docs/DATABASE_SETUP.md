# eggNOG v5 database setup

The deployer prepares eggNOG data separately under the applicable license. Normal runs never download, upgrade, or modify it. The configured directory must contain four non-empty readable files: `eggnog.db`, `eggnog.taxa.db`, `eggnog.taxa.db.traverse.pkl`, and `eggnog_proteins.dmnd`.

Validate an existing directory:

```bash
python -m scripts.validate_eggnog_database --data-dir <deployment-chosen-directory> --json
```

The validator opens `eggnog.db` read-only as SQLite and reports any detected version metadata. Connect with `BACFUNC_EGGNOG_DATA_DIR` and optional `BACFUNC_EGGNOG_MANIFEST`, or YAML. The directory may be anywhere selected by the deployer and is not copied into this project.
