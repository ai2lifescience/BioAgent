# Bacterial genome mutation analysis

> Pipeline dependencies and databases belong to the pipeline container. The BioAgent environment does not install workflow tools.

Compare assembled bacterial genomes against a reference, call and filter SNPs, and optionally build a phylogeny.

## Inputs

- `genomes` (optional, `input_path`): One genome FASTA or a directory of genome FASTA files.. Accepted: .fasta, .fa, .fna, .fas.
- `reference` (optional, `reference_path`): Reference sequence or reference resource used for comparison.. Accepted: .fasta, .fa, .fna, .fas.

## Outputs

- `report`: `data/output/report.md` — BioAgent Markdown report produced by this workflow..
- `metrics`: `data/output/metrics.json` — BioAgent metrics produced by this workflow..
- `matrix`: `data/output/filtered_snp_matrix.fasta` — Filtered SNP alignment produced by this workflow..
- `variants`: `data/output/variants.tsv` — Annotated variants produced by this workflow..
- `variants_summary`: `data/output/variants_summary.txt` — Variant statistics produced by this workflow..
- `pipeline_summary`: `data/output/summary.txt` — Pipeline summary produced by this workflow..
- `initial_snps`: `data/output/initial_snp_list.csv` — SNP calls before filtering produced by this workflow..
- `mutation_report`: `data/output/mutation_report.csv` — Detailed mutation report produced by this workflow..
- `final_tree`: `data/output/final_tree.nwk` — Final phylogenetic tree produced by this workflow..
- `treefile`: `data/output/iqtree_run.treefile` — IQ-TREE tree produced by this workflow..
- `iqtree_report`: `data/output/iqtree_run.iqtree` — IQ-TREE report produced by this workflow..
- `iqtree_log`: `data/output/iqtree_run.log` — IQ-TREE log produced by this workflow..
- `pipeline_log`: `data/output/pipeline.log` — Pipeline execution log produced by this workflow..

## Run

Ask the agent to run `bacterial_genome_mutation_analysis` with the inputs above. For the bundled example, say:

```text
Run bacterial_genome_mutation_analysis with its bundled example data and collect the results.
```

The `runner.yaml` file is the agent-facing input/output contract. The runtime stages inputs and writes declared outputs inside the per-run workspace.
