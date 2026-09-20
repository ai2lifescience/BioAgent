# RNA secondary-structure prediction

> Pipeline dependencies and databases belong to the pipeline container. The BioAgent environment does not install workflow tools.

Convert nucleotide FASTA records to RNA, predict minimum-free-energy secondary structures with RNAfold, and return structured reports.

## Inputs

- `rna` (required, `rna_path`): One or more RNA or DNA-letter nucleotide sequences in FASTA format.. Accepted: .fasta, .fa, .fna.

## Outputs

- `report`: `output/report.md` — RNA folding report produced by this workflow..
- `metrics`: `output/metrics.json` — RNA folding metrics produced by this workflow..
- `structures`: `output/structures.tsv` — RNA structures table produced by this workflow..
- `dot_bracket`: `output/structures.dbn` — Dot-bracket structures produced by this workflow..
- `log`: `output/rnafold.log` — RNAfold execution log produced by this workflow..

## Run

Ask the agent to run `rna_secondary_structure_prediction` with the inputs above. For the bundled example, say:

```text
Run rna_secondary_structure_prediction with its bundled example data and collect the results.
```

The `runner.yaml` file is the agent-facing input/output contract. The runtime stages inputs and writes declared outputs inside the per-run workspace.
