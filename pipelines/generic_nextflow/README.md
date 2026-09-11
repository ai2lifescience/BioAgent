# Generic Nextflow Pipeline Environment

## Requirements

- A recent Nextflow release.
- Java 17 or newer.
- Python 3.10 or newer with PyYAML 6.0 or newer.
- Bash, as required by local Nextflow process execution.

Install Nextflow using its official installation instructions, then verify:

```bash
nextflow -version
java -version
python3 -c "import yaml; print(yaml.__version__)"
```

From the BioAgent repository root, run the example through the CLI:

```bash
python -m interfaces.cli 'Run pipeline with pipeline_name: generic_nextflow sequence: "pipelines/generic_nextflow/data/input/sequences_segment1.fasta" metadata: "pipelines/generic_nextflow/data/input/metadata.tsv"'
```

On Windows, run BioAgent and Nextflow inside WSL because Nextflow processes use
a POSIX shell.

Pipeline function, inputs, and outputs are documented in
[`DESCRIPTION.md`](DESCRIPTION.md).
