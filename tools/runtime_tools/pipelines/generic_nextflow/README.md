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

From the Pipeline2Agent repository root, run the example through the CLI:

```bash
python -m interfaces.cli 'Run generic_nextflow with its bundled example data and collect the results.'
```

`runner.yaml` holds parameter defaults and input/output declarations.
`nextflow.config` remains the native Nextflow configuration file.

On Windows, run Pipeline2Agent and Nextflow inside WSL because Nextflow processes use
a POSIX shell.

## Workflow

### Function

This pipeline demonstrates Pipeline2Agent's Nextflow engine with a small local
sequence-analysis workflow. It normalizes a FASTA sequence, calculates basic
metrics, and creates a Markdown report.

```text
FASTA + metadata
  -> Nextflow stages declared inputs
  -> normalize sequence characters
  -> calculate length, GC percentage, and minimum-length status
  -> publish normalized FASTA, metrics, and report
```

### Inputs

- `input_path`: required FASTA input (`.fa`, `.fasta`, or `.fna`).
- `metadata_path`: required TSV or CSV metadata table.

### Outputs

- `normalized.fasta`: normalized sequence with the configured label and segment.
- `metrics.json`: sequence, metadata, and configured analysis metrics.
- `report.md`: human-readable metric summary.

Nextflow first publishes these files to Pipeline2Agent's engine staging directory.
The runner then maps each `nextflow_output` declared in `runner.yaml` to the
stable per-run artifact path declared by that output record.
