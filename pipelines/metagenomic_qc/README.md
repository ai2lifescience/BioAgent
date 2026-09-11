# Metagenomic QC Cromwell Pipeline

## Runtime requirements

- A reachable Cromwell Server. BioAgent uses `CROMWELL_URL` when set and
  otherwise uses `http://127.0.0.1:8000` from `runner.yaml`.
- BioAgent and Cromwell must resolve uploaded FASTQ and output paths through a
  shared filesystem.
- The Cromwell task runtime must already mount the Kraken2 and Bowtie2 database
  directories at the paths declared in `inputs.json`.
- The task backend must provide `mscan-detection-qc:v1.0` (or an overridden
  image) with `/app/scripts/count_reads.py`, fastp, Kraken2, and Bowtie2.

Check the service before submitting:

```bash
export CROMWELL_URL=http://192.168.164.39:39000
curl "$CROMWELL_URL/engine/v1/status"
```

BioAgent submits `stage0_qc.wdl`, preserves Cromwell's returned `Submitted`
response, polls until a terminal status, and then collects the declared files.
A temporary `Unrecognized workflow ID` is retried for up to 300 seconds.

The Kraken2 and Bowtie2 database inputs intentionally remain `Array[String]`.
They refer to paths already mounted by the Cromwell task backend and are not
localized as WDL `File` values.
