# Synthetic FASTQ shell example

This small demonstration validates four artificial FASTQ records, filters by
minimum length and fraction of N bases, and joins read IDs to sample metadata.
It does not require downloads or external bioinformatics programs. Requirements:
Bash, Python 3.11+, and PyYAML (already in Pipeline2Agent's requirements).

Inputs: `reads.fastq` and `metadata.tsv` with `read_id` and `sample` columns.
Outputs: `filtered.fastq`, `assignments.tsv`, `metrics.json`, and `report.md`.
With default parameters, 4 reads / 28 bases become 2 reads / 16 retained bases.
All four input reads appear in the assignment table, with their pass/fail flag.

Ask Pipeline2Agent: “Use the example_sequence_qc example data, run the pipeline, and
collect its results.” It stages the examples into the session, creates a plan,
requests execution approval, then starts a local job and collects the outputs.

For a standalone run, create a small runtime YAML with `input_path`,
`metadata_path`, and output paths, then pass it to `bash run.sh`. No base
`config.yaml` is bundled; the runtime service creates this file in the per-job
directory from `runner.yaml`.

For the runtime CLI, see the
[pipeline architecture guide](../../../../docs/architecture.md#pipeline-runtime).
Examples are only staged when explicitly requested; uploaded data takes
precedence for real tasks.
