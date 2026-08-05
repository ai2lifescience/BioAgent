# External database and reference requirements

Large reference databases are intentionally **not included** in this archive
and must not be committed to Git. The bundled `data/input` files are only small
synthetic integration fixtures. Administrators should retain the following
large files on approved server storage and configure paths by YAML or the
documented environment variables.

| Pipeline | Required external data | How the path is configured | Tested server-path information |
| --- | --- | --- | --- |
| `bacarg-V2` | Custom ABRicate MEGARes v3 database, normalized metadata TSV, database manifest | `databases.abricate_datadir`, `databases.metadata`, `databases.manifest`; environment alternatives are `BACARG_ABRICATE_DATADIR`, `BACARG_MEGARES_METADATA`, `BACARG_MEGARES_MANIFEST` | The tested configuration points to `/data/wutt/xjp/BioAgent-clean/databases/bacarg/abricate`, with metadata at `/data/wutt/xjp/BioAgent-clean/databases/bacarg/abricate/megares_v3/metadata.normalized.tsv` and manifest at `/data/wutt/xjp/BioAgent-clean/databases/bacarg/abricate/megares_v3/database_manifest.json`. |
| `bacfunc-V2` | eggNOG v5: `eggnog.db`, `eggnog.taxa.db`, `eggnog.taxa.db.traverse.pkl`, `eggnog_proteins.dmnd`; optional manifest | `BACFUNC_EGGNOG_DATA_DIR` and optional `BACFUNC_EGGNOG_MANIFEST`, or `databases.eggnog.data_dir` / `manifest` in YAML | No path is deliberately hardcoded in this package. The tested server deployment supplied this directory externally and `bacfunc doctor` confirmed eggNOG version 5.0.2. Record the local approved storage path when deploying elsewhere. |
| `bacvf-V2` | Custom ABRicate VFDB-core database, normalized metadata TSV, database manifest | `databases.abricate_datadir`, `databases.metadata`, `databases.manifest`; environment alternatives are `BACVF_ABRICATE_DATADIR`, `BACVF_VFDB_METADATA`, `BACVF_VFDB_MANIFEST` | No path is hardcoded in the portable package. The deployment owner must set all three paths before production use. |
| `bactmut_fasta` | None for `reference_mode: local`; GTDB representative FASTA plus metadata only for `species` or `taxonid` mode | User provides `reference` for local mode; otherwise set `GTDB_DB_PATH` and `GTDB_METADATA_PATH` | `GTDB_DB_PATH=/hpcdisk1/jcyj_group/jiangxq226/pathdect_pipeline/database/pcf/bacterial_reference_res96_v2/representative.fa.filter_sp_mag`; `GTDB_METADATA_PATH=/hpcdisk1/jcyj_group/jiangxq226/pathdect_pipeline/database/pcf/bacterial_reference_res96_v2/bac120_metadata.tsv.deversion`. |
| `bactmut_fastq` | None for `reference_mode: local`; GTDB representative FASTA plus metadata only for `species` or `taxonid` mode | User provides `reference` for local mode; otherwise set `GTDB_DB_PATH` and `GTDB_METADATA_PATH` | `GTDB_DB_PATH=/hpcdisk1/jcyj_group/jiangxq226/pathdect_pipeline/database/pcf/bacterial_reference_res96_v2/representative.fa.filter_sp_mag`; `GTDB_METADATA_PATH=/hpcdisk1/jcyj_group/jiangxq226/pathdect_pipeline/database/pcf/bacterial_reference_res96_v2/bac120_metadata.tsv.deversion`. |
| `virmut` | None for `reference_mode: local`; viral reference FASTA and metadata only for `species` or `taxonid` mode | User provides `reference` for local mode; otherwise use `VIRUS_DB` and `VIRUS_METADATA` | `run.sh` defaults to `/hpcdisk1/jcyj_group/jiangxq226/pathdect_pipeline/database/pcf/virus_db_reference_merged3/reference.fasta` and `/hpcdisk1/jcyj_group/jiangxq226/pathdect_pipeline/database/pcf/virus_db_reference_merged3/meta.tsv`. Override these environment variables if the deployment has different approved storage. |

## Tool databases versus reference files

Prokka, ABRicate, eggNOG-mapper, minimap2, samtools, and bcftools are software
dependencies. The large resources listed above are reference databases or
metadata. They must be present and readable by the service account, but are
not pipeline inputs and are not part of this Git contribution.

Before a production run, use the relevant `doctor` command for BacARG,
BacFunc, or BacVF. For BactMut and virmut, verify that the selected local
reference file or the required environment variables are readable.
