# Bacterial genome annotation

> Pipeline dependencies and databases belong to the pipeline container. The BioAgent environment does not install workflow tools.

Annotate assembled bacterial contigs with Prokka or Bakta and normalize the results into sequence, feature, report, metrics, and archive artifacts.

## Inputs

- `genome` (required, `genome_path`): Assembled bacterial contigs in FASTA format.. Accepted: .fasta, .fa, .fna.

## Outputs

- `report`: `output/report.md` — Annotation report produced by this workflow..
- `metrics`: `output/metrics.json` — Annotation metrics produced by this workflow..
- `gff`: `output/annotation.gff` — GFF3 annotation produced by this workflow..
- `genbank`: `output/annotation.gbk` — GenBank annotation produced by this workflow..
- `proteins`: `output/annotation.faa` — Protein sequences produced by this workflow..
- `genes`: `output/annotation.ffn` — Gene nucleotide sequences produced by this workflow..
- `contigs`: `output/annotation.fna` — Annotated contigs produced by this workflow..
- `features`: `output/annotation.tsv` — Feature table produced by this workflow..
- `summary`: `output/annotation.txt` — Annotation statistics produced by this workflow..
- `log`: `output/annotation.log` — Annotation execution log produced by this workflow..
- `bundle`: `output/annotation_outputs.zip` — Complete raw annotation output produced by this workflow..
- `bakta_json`: `output/annotation.json` — Bakta machine-readable annotation produced by this workflow..
- `inference`: `output/annotation.inference.tsv` — Bakta inference evidence produced by this workflow..
- `hypotheticals`: `output/annotation.hypotheticals.tsv` — Bakta hypothetical proteins produced by this workflow..
- `plot_svg`: `output/annotation.svg` — Bakta annotation plot (SVG) produced by this workflow..
- `plot_png`: `output/annotation.png` — Bakta annotation plot (PNG) produced by this workflow..

## Run

Ask the agent to run `bacterial_genome_annotation` with the inputs above. For the bundled example, say:

```text
Run bacterial_genome_annotation with its bundled example data and collect the results.
```

The `runner.yaml` file is the agent-facing input/output contract. The runtime stages inputs and writes declared outputs inside the per-run workspace.
