# Molecular Meta WDL Pipeline Environment

## Host requirements

The host runtime requires:

- Python 3.9 or newer.
- miniwdl 1.12 or newer.
- A running Docker daemon accessible to the current user.
- Access to the `cncb/molecular-wdl:v1.0` task image, or a compatible image
  supplied through the workflow's `docker_image` input.
- Up to 16 CPU cores and 32 GB memory with the default input settings.

## BioAgent environment

From the repository root:

```bash
conda create -n bioagent python=3.12 -y
conda activate bioagent
python -m pip install -r requirements.txt
docker pull cncb/molecular-wdl:v1.0
```

## Task environment

The WDL tasks require Bash/core utilities, fastp, BWA, SAMtools, BamUtil,
iVar, Nextclade, and Java. These commands must be present inside the configured
task image.

[`environment.yml`](environment.yml) documents this tool environment and can
be resolved separately with:

```bash
conda env create -f pipelines/molecular_meta_wdl/environment.yml
conda activate molecular-meta-wdl
```

The current WDL `runtime` blocks explicitly select Docker, so activating this
Conda environment does not replace miniwdl and Docker during a workflow run.

Verify the host environment:

```bash
miniwdl --version
docker info
docker image inspect cncb/molecular-wdl:v1.0
```

Pipeline function, inputs, and outputs are documented in
[`DESCRIPTION.md`](DESCRIPTION.md).
