# Bacterial functional annotation

> Pipeline dependencies and databases belong to the pipeline container. The BioAgent environment does not install workflow tools.

Annotate bacterial genes and assign functional terms from contigs or reads using the bundled functional-annotation workflow.

## Inputs

- `input_data` (required, `input_path`): Sequence input accepted by this workflow.. Accepted: .fasta, .fa, .fna, .fastq, .fq.

## Outputs

- `gene_annotations`: `data/output/gene_annotations.tsv` — Gene annotations table produced by this workflow..
- `annotation_terms`: `data/output/annotation_terms.tsv` — Annotation terms table produced by this workflow..
- `qc`: `data/output/qc.json` — Quality-control summary produced by this workflow..
- `status`: `data/output/status.json` — Pipeline status produced by this workflow..

## Run

Ask the agent to run `bacterial_functional_annotation` with the inputs above. For the bundled example, say:

```text
Run bacterial_functional_annotation with its bundled example data and collect the results.
```

The `runner.yaml` file is the agent-facing input/output contract. The runtime stages inputs and writes declared outputs inside the per-run workspace.
