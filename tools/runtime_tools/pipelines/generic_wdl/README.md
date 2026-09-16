# Generic WDL Pipeline Environment

## Requirements

The host runtime requires:

- Python 3.9 or newer.
- miniwdl 1.12 or newer.
- A running Docker daemon accessible to the current user.
- Access to the `python:3.11-slim` task image.

The task image supplies Python and the standard-library modules used by the
workflow. No additional bioinformatics tools are required.

## BioAgent environment

From the repository root:

```bash
conda create -n bioagent python=3.12 -y
conda activate bioagent
python -m pip install -r requirements.txt
docker pull python:3.11-slim
```

## Minimal standalone environment

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install "miniwdl>=1.12.0"
docker pull python:3.11-slim
```

Verify the environment:

```bash
miniwdl --version
docker info
docker image inspect python:3.11-slim
```

## Workflow

### Function

This WDL 1.0 pipeline demonstrates sequence normalization and basic FASTA
metrics through BioAgent's WDL runner.

```text
FASTA
  -> remove headers and non-sequence punctuation
  -> optionally uppercase and relabel the sequence
  -> calculate length, GC percentage, and minimum-length status
  -> write normalized FASTA, metrics, and report
```

### Inputs

- `GenericWdl.input_fasta`: required FASTA file.
- `GenericWdl.label`: output FASTA label and report label.
- `GenericWdl.min_length`: minimum length used by the pass/fail metric.
- `GenericWdl.uppercase`: whether to uppercase the normalized sequence.

### Outputs

- `normalized.fasta`: cleaned sequence wrapped at 80 characters.
- `metrics.json`: sequence length, GC percentage, and minimum-length result.
- `report.md`: human-readable metric summary.

BioAgent copies these WDL outputs to the per-job output directory as declared in
`runner.yaml`. The bundled `inputs.json` and `options.json` are optional native
workflow files; session inputs still have to be selected explicitly.
BioAgent generates `inputs.runtime.json` and `options.runtime.json` in the job
directory without changing these source files. miniwdl consumes the generated
inputs; the options copy records Cromwell-style settings for provenance.
