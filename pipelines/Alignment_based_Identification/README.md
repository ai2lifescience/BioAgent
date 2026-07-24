# Alignment-based Identification Cromwell Pipeline

## Runtime requirements

- A reachable Cromwell Server. `CROMWELL_URL` overrides the default
  `http://127.0.0.1:8000` declared in `runner.yaml`.
- BioAgent and Cromwell must resolve uploaded FASTQ, database, annotation, and
  output paths through a shared filesystem.
- The task backend must provide `mscan-detection:v1.0` (or an override),
  including Stage 1–6 Python/minimap2 entrypoints used by `pipeline.wdl`.

Check the service before submitting:

```bash
export CROMWELL_URL=http://192.168.164.39:39000
curl "$CROMWELL_URL/engine/v1/status"
```

BioAgent submits `pipeline.wdl`, preserves Cromwell's `Submitted` response,
polls status until completion, and collects the reports declared in
`runner.yaml`. A temporary `Unrecognized workflow ID` is retried for up to
300 seconds.

Provide host-filtered FASTQ from Stage 0 QC as `clean_r1` (optional
`clean_r2`). Enable pathogen databases by setting the corresponding `db_*`
paths in `inputs.json`; leave unused databases unset.
