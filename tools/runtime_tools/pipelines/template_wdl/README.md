# WDL pipeline template

> Pipeline dependencies belong to the task container. The BioAgent environment does not install workflow tools.

Use this template to demonstrate the WDL engine with one FASTA sequence. Its task
runs in the `python:3.11-slim` container and writes a normalized FASTA, metrics
JSON, and Markdown report.

Run it through the runtime with:

```text
Run template_wdl with its bundled example data and collect the results.
```

The bundle keeps only the WDL workflow, native input/options JSON, examples, README,
and `runner.yaml` contract.
