# Generic WDL Pipeline

This is a small plug-and-play WDL example for BioAgent pipeline experiments.

Files:

- `runner.yaml`: BioAgent-facing metadata for the pipeline folder.
- `workflow.wdl`: WDL 1.0 workflow that normalizes a FASTA sequence and writes a report.
- `inputs.json`: default WDL workflow inputs.
- `options.json`: optional WDL engine options metadata kept with each run.
- `data/example_sequence.fasta`: example input FASTA.

`runner.yaml` declares BioAgent-facing input slots and WDL output mapping. A
WDL run generates `inputs.runtime.json` from `inputs.json`, writes
`options.runtime.json` from `options.json`, runs `miniwdl`, then copies declared
WDL outputs to the `target` paths declared in `runner.yaml`.

Current status:

- The current BioAgent `pipeline_runner` supports this folder with `miniwdl`.
- Install WDL support with `pip install -r requirements.txt`.
- miniwdl uses your normal local miniwdl runtime configuration. By default,
  miniwdl expects Docker unless your environment is configured otherwise.
- This example task declares `docker: "python:3.11-slim"` in `workflow.wdl`.
  Pull that image first if your machine cannot reach Docker Hub during runs.
- Cromwell support is not implemented yet. `options.runtime.json` is prepared so
  future Cromwell support can pass rewritten runtime output options without
  changing `runner.yaml.outputs`.

Example local command with miniwdl:

```bash
miniwdl run workflow.wdl -i inputs.json
```
