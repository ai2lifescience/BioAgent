# Viral genome mutation analysis

> Pipeline dependencies and databases belong to the pipeline container. The BioAgent environment does not install workflow tools.

Compare viral genome FASTA files to a reference, call nucleotide variants, and optionally infer a phylogeny.

## Inputs

- `genomes` (required, `input_path`): One genome FASTA or a directory of genome FASTA files.. Accepted: .fasta, .fa, .fna.
- `reference` (optional, `reference_path`): Reference sequence or reference resource used for comparison.. Accepted: .fasta, .fa, .fna.

## Outputs

- `matrix`: `data/output/matrix.tsv` — SNP matrix produced by this workflow..
- `variants`: `data/output/variants.tsv` — Variants table produced by this workflow..
- `summary`: `data/output/variants_summary.txt` — Variants summary produced by this workflow..
- `tree_fasta`: `data/output/tree.fasta` — Tree FASTA produced by this workflow..
- `treefile`: `data/output/tree.treefile` — IQ-TREE tree produced by this workflow..
- `iqtree_report`: `data/output/tree.iqtree` — IQ-TREE report produced by this workflow..
- `iqtree_log`: `data/output/tree.log` — IQ-TREE log produced by this workflow..

## Run

Ask the agent to run `viral_genome_mutation_analysis` with the inputs above. For the bundled example, say:

```text
Run viral_genome_mutation_analysis with its bundled example data and collect the results.
```

The `runner.yaml` file is the agent-facing input/output contract. The runtime stages inputs and writes declared outputs inside the per-run workspace.
