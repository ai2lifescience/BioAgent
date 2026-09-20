# Bacterial read variant analysis

> Pipeline dependencies and databases belong to the pipeline container. The BioAgent environment does not install workflow tools.

Map bacterial reads to a reference, call and filter variants, build a cross-sample SNP matrix, and optionally infer a phylogeny.

## Inputs

- `reads` (required, `input_path`): Sequence reads supplied to the workflow.. Accepted: .fastq, .fq, .fastq.gz, .fq.gz.
- `reference` (optional, `reference_path`): Reference sequence or reference resource used for comparison.. Accepted: .fasta, .fa, .fna, .fas.

## Outputs

- `report`: `data/output/report.md` — BioAgent Markdown report produced by this workflow..
- `metrics`: `data/output/metrics.json` — BioAgent metrics produced by this workflow..
- `matrix`: `data/output/matrix.tsv` — Filtered SNP matrix produced by this workflow..
- `variants`: `data/output/variants.tsv` — Annotated variants produced by this workflow..
- `variants_summary`: `data/output/variants_summary.txt` — Variant statistics produced by this workflow..
- `final_tree`: `data/output/final_tree.nwk` — Final phylogenetic tree produced by this workflow..
- `tree_alignment`: `data/output/tree.fasta` — Tree alignment produced by this workflow..
- `treefile`: `data/output/tree.treefile` — IQ-TREE tree produced by this workflow..
- `iqtree_report`: `data/output/tree.iqtree` — IQ-TREE report produced by this workflow..
- `iqtree_log`: `data/output/tree.log` — IQ-TREE log produced by this workflow..
- `pipeline_log`: `data/output/pipeline.log` — Pipeline execution log produced by this workflow..

## Run

Ask the agent to run `bacterial_read_variant_analysis` with the inputs above. For the bundled example, say:

```text
Run bacterial_read_variant_analysis with its bundled example data and collect the results.
```

The `runner.yaml` file is the agent-facing input/output contract. The runtime stages inputs and writes declared outputs inside the per-run workspace.
