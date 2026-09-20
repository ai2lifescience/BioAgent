# Shell pipeline template

> Pipeline dependencies belong to the pipeline container. The BioAgent environment does not install workflow tools.

Use this small shell template to join sequence IDs to a TSV/CSV metadata table,
normalize the input text, and produce a report, metrics, and assignment table.

Inputs are `reads` (text, FASTA, or FASTQ) and `metadata` (TSV or CSV with
`sequence_id` and `subtype` columns). Outputs are `normalized.txt`,
`subtypes.tsv`, `metrics.json`, and `report.md`.

Run it through the runtime with:

```text
Run template_shell with its bundled example data and collect the results.
```

The `runner.yaml` file is the complete agent-facing contract. The bundle is
self-contained and has no project-level configuration file.
