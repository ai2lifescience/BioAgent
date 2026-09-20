# Nextflow pipeline template

> Pipeline dependencies belong to the pipeline container. The BioAgent environment does not install workflow tools.

Use this template to demonstrate the Nextflow engine with one FASTA sequence and
a TSV/CSV metadata table. It writes a normalized FASTA, metrics JSON, and Markdown
report.

Run it through the runtime with:

```text
Run template_nextflow with its bundled example data and collect the results.
```

The `runner.yaml` file declares the workflow, native Nextflow configuration, input
slots, outputs, and parameter defaults.
