# Generic Shell Pipeline Environment

## Requirements

The pipeline runtime requires:

- Bash with standard Unix utilities: `cat`, `cp`, `dirname`, `mkdir`, `mv`,
  `sed`, `tr`, and `wc`.
- Python 3.9 or newer.
- PyYAML 6.0 or newer.

It does not require Docker, network access, or external bioinformatics command
line tools.

## BioAgent environment

The project environment already includes the required dependency. From the
repository root:

```bash
conda create -n bioagent python=3.12 -y
conda activate bioagent
python -m pip install -r requirements.txt
```

## Minimal standalone environment

To run only this pipeline, a small virtual environment is sufficient:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install "PyYAML>=6.0"
```

Verify the required commands and Python package:

```bash
bash --version
python -c "import yaml; print(yaml.__version__)"
```

Pipeline function, inputs, and outputs are documented in
[`DESCRIPTION.md`](DESCRIPTION.md).
