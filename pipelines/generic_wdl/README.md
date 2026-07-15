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

Pipeline function, inputs, and outputs are documented in
[`DESCRIPTION.md`](DESCRIPTION.md).
