# WDL pipeline template

This WDL 1.0 bundle demonstrates a small containerized task that normalizes one
FASTA sequence, calculates length/GC/minimum-length metrics, and writes a
normalized FASTA, JSON metrics, and Markdown report.

## Requirements

For standalone execution, use one of:

- Cromwell with a Docker-enabled backend; or
- miniwdl 1.12 or newer with Docker enabled.

The task runtime uses the `python:3.11-slim` image, so Docker must be accessible
to the workflow engine and able to pull that image. No external bioinformatics
tool or database is required. The WDL itself supplies the Python code inside the
task container.

Verify a local setup with:

```bash
miniwdl check workflow.wdl
miniwdl --version
docker image inspect python:3.11-slim || docker pull python:3.11-slim
```

## Inputs and outputs

The workflow inputs are `TemplateWdl.input_fasta`, `label`, `min_length`, and
`uppercase`. It removes FASTA headers and punctuation, optionally uppercases the
sequence, and writes `normalized.fasta`, `metrics.json`, and `report.md`.
`inputs.json` contains the bundled example values; replace its FASTA path for a
real run.

## Standalone run

With miniwdl:

```bash
cp inputs.json inputs.local.json
# Edit TemplateWdl.input_fasta in inputs.local.json.
miniwdl run workflow.wdl inputs.local.json
```

With Cromwell:

```bash
java -jar cromwell.jar run workflow.wdl -i inputs.local.json -o options.json
```

The engine creates its own output directory; copy the three declared files to
your desired result directory.

## BioAgent use and limitations

Use `pipeline_name: template_wdl` with `sequence`, or request:

```text
Run template_wdl with its bundled example data and collect the results.
```

This is an engine integration example. Its sequence metrics and normalization
do not constitute a production biological analysis.
