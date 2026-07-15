# Generic Snakemake Pipeline Environment

## Requirements

The pipeline runtime requires:

- Python 3.10 or newer.
- Snakemake 8.0 or newer.
- PyYAML 6.0 or newer.

The workflow uses only Python standard-library modules for its analysis and
does not require Docker, network access, workflow-managed Conda environments,
or external bioinformatics tools.

## BioAgent environment

From the repository root:

```bash
conda create -n bioagent python=3.12 -y
conda activate bioagent
python -m pip install -r requirements.txt
```

## Minimal standalone environment

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install "snakemake>=8.0" "PyYAML>=6.0"
```

Verify the environment:

```bash
snakemake --version
python -c "import yaml; print(yaml.__version__)"
```

Pipeline function, inputs, and outputs are documented in
[`DESCRIPTION.md`](DESCRIPTION.md).
