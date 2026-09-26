# Metagenomic read quality control

This WDL 1.0 workflow performs fastp quality/length filtering followed by
Kraken2 and Bowtie2 host/vector removal. It produces reads and read-count tables
for downstream metagenomic analysis.

## Requirements

Standalone execution requires:

- miniwdl for local execution, or Java for the standalone Cromwell command;
- a reachable Cromwell Server when `CROMWELL_URL` is set, with the configured
  S3-backed input/output paths available to Cromwell and task containers;
- Docker or the configured backend with `cncb/mscan-detection-qc:v1.0` (or a
  compatible image) containing `fastp`, Kraken2, Bowtie2, and
  `/app/scripts/count_reads.py`;
- mounted Kraken2 database files and the complete Bowtie2 host/vector index.

The database files are not bundled. Their paths are intentionally represented
as `Array[String]` in `inputs.json`; they must already be mounted at the same
paths inside the task container. The default profile can require 8 CPUs, 64 GB
RAM, and 500 GB disk.

BioAgent defaults to local miniwdl when `CROMWELL_URL` is unset. For Cromwell
submission, configure and verify its endpoint before starting BioAgent:

```bash
export CROMWELL_URL=http://192.168.164.39:39000
curl "$CROMWELL_URL/engine/v1/status"
```

## Inputs and processing

- `MetagenomicQc.fastq_r1`: required FASTQ/FASTQ.GZ read 1;
- `MetagenomicQc.fastq_r2`: optional read 2; its presence selects paired mode;
- `MetagenomicQc.kraken2_db_files`: mounted Kraken2 database files;
- `MetagenomicQc.host_bowtie2_index_files`: mounted Bowtie2 index files;
- sample ID, lean-I/O, Docker, and resource settings in `inputs.json`.

The two reads may use different compression suffixes. The workflow runs:
`fastp -> Kraken2 host filtering -> Bowtie2 host/vector filtering`.

## Run standalone

```bash
cp inputs.json inputs.local.json
# Replace FASTQ and mounted database paths in inputs.local.json.
java -jar cromwell.jar run stage0_qc.wdl \
  -i inputs.local.json -o options.json
```

Use a Cromwell service instead if the execution backend is remote. BioAgent
submits the same WDL, polls it, and copies the declared outputs after success.

## Outputs

- `clean.R1.fq`: cleaned single-end reads or paired read 1;
- `clean.R2.fq`: paired read 2, absent for single-end input;
- `qc_counts.tsv`: input, post-QC, and post-host-removal counts;
- `phase1_read_overview.tsv`: one-row sample metrics.

The workflow also returns `post_host_reads` as an integer WDL output.

## BioAgent use and limits

Use `pipeline_name: metagenomic_read_quality_control` with `read1` and optional
`read2`. Database quality and the selected host/vector references control what
is removed; this pipeline does not identify pathogens.
