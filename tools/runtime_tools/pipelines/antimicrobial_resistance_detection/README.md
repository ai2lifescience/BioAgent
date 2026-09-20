# Antimicrobial resistance detection

> Pipeline dependencies and databases belong to the pipeline container. The BioAgent environment does not install workflow tools.

Identify antimicrobial resistance gene candidates from bacterial or metagenomic sequence data and return normalized hit tables, quality metrics, and run status.

## Inputs

- `input_data` (required, `input_path`): Sequence input accepted by this workflow.. Accepted: .fasta, .fa, .fna, .fastq, .fq.

## Outputs

- `arg_hits`: `data/output/arg_hits.tsv` — ARG hits table produced by this workflow..
- `arg_hits_jsonl`: `data/output/arg_hits.jsonl` — ARG hits JSONL produced by this workflow..
- `qc`: `data/output/qc.json` — Quality-control summary produced by this workflow..
- `status`: `data/output/status.json` — Pipeline status produced by this workflow..

## Run

Ask the agent to run `antimicrobial_resistance_detection` with the inputs above. For the bundled example, say:

```text
Run antimicrobial_resistance_detection with its bundled example data and collect the results.
```

The `runner.yaml` file is the agent-facing input/output contract. The runtime stages inputs and writes declared outputs inside the per-run workspace.
