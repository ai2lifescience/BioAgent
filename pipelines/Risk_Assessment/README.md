# Variant Risk Assessment Cromwell Pipeline

## Runtime requirements

- A reachable Cromwell Server. `CROMWELL_URL` overrides the default
  `http://127.0.0.1:8000` declared in `runner.yaml`.
- BioAgent and Cromwell must resolve the uploaded FASTQ and output paths
  through a shared filesystem.
- Cromwell must be able to read the reference, snpEff, segment, and risk
  annotation files declared in `inputs.json`.
- The task backend must provide `cncb/risk-wdl:v1.0` (or an override),
  including `/app/run_variant_risk.sh` and `/app/lib/docker_bin_paths.sh`.

Check the service before submitting:

```bash
export CROMWELL_URL=http://192.168.164.39:39000
curl "$CROMWELL_URL/engine/v1/status"
```

BioAgent submits `pipline.wdl`, preserves Cromwell's `Submitted` response,
polls status until completion, and collects the report, segments table, and
full output archive. A temporary `Unrecognized workflow ID` is retried for up
to 300 seconds.

The user must upload clean FASTQ (`fastq_r1`, optional `fastq_r2`) and
explicitly choose `H1N1`, `H3N2`, or `SARS_CoV_2`. That choice applies the
matching reference, snpEff database, risk annotations, and default variant
thresholds from production `variant-risk` settings.
