# Bacterial virulence-factor detection

> Pipeline dependencies and databases belong to the pipeline container. The BioAgent environment does not install workflow tools.

Identify virulence-factor sequence candidates from bacterial or metagenomic data and return normalized evidence tables and QC artifacts.

## Inputs

- `input_data` (required, `input_path`): Sequence input accepted by this workflow.. Accepted: .fasta, .fa, .fna, .fastq, .fq.

## Outputs

- `vf_hits`: `data/output/vf_hits.tsv` — Virulence-factor hits table produced by this workflow..
- `vf_hits_jsonl`: `data/output/vf_hits.jsonl` — Virulence-factor hits JSONL produced by this workflow..
- `qc`: `data/output/qc.json` — Quality-control summary produced by this workflow..
- `status`: `data/output/status.json` — Pipeline status produced by this workflow..

## Run

Ask the agent to run `bacterial_virulence_factor_detection` with the inputs above. For the bundled example, say:

```text
Run bacterial_virulence_factor_detection with its bundled example data and collect the results.
```

The `runner.yaml` file is the agent-facing input/output contract. The runtime stages inputs and writes declared outputs inside the per-run workspace.
