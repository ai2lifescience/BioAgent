# Snakemake pipeline template

> Pipeline dependencies belong to the pipeline container. The BioAgent environment does not install workflow tools.

Use this template to demonstrate the Snakemake engine with one FASTA sequence and
a TSV/CSV metadata table. It writes a normalized FASTA, metrics JSON, and Markdown
report.

Run it through the runtime with:

```text
Run template_snakemake with its bundled example data and collect the results.
```

The `runner.yaml` file declares the Snakefile, input slots, outputs, and parameter
defaults. The bundle has no separate project configuration file.
