# RNA secondary-structure prediction

This bundle converts nucleotide FASTA records to RNA (`T` becomes `U`) and
runs ViennaRNA `RNAfold` to predict minimum-free-energy secondary structures.
It is an independent implementation and does not import Biomni.

## Requirements

- Bash and Python 3.11 or newer;
- PyYAML available to that Python interpreter;
- ViennaRNA with `RNAfold` on `PATH`.

A pinned Bioconda installation is convenient:

```bash
conda create -n rnafold -c conda-forge -c bioconda python=3.11 pyyaml viennarna=2.7.0
conda activate rnafold
RNAfold --version
```

No network access or database is needed during the run.

## Inputs and parameters

`rna_path` is a FASTA file with `.fa`, `.fasta`, or `.fna` suffixes. The parser
accepts IUPAC nucleotide symbols and at most 1,000 records. Parameters under
`params` are:

- `temperature_c` (default `37.0`);
- `max_sequence_length` per record (default `10000`).

The workflow validates records and lengths before invoking RNAfold once per
record. User values are passed as bounded subprocess arguments; arbitrary
RNAfold options are not accepted.

## Standalone installation and run

```bash
chmod +x run.sh
cp config.yaml config.local.yaml
# Set rna_path and output_dir; adjust params if needed.
./run.sh config.local.yaml
```

The same command can be run as `python workflow.py config.local.yaml` when the
required Python package and `RNAfold` are active. The example FASTA is a small
synthetic fixture; the files in `output/` are contract examples rather than
validated biological predictions.

## Outputs

- `structures.tsv`: sequence ID, length, MFE, and dot-bracket structure;
- `structures.dbn`: FASTA-like sequence/dot-bracket records;
- `metrics.json` and `report.md`;
- `rnafold.log` with command, version, return code, and per-record output.

## BioAgent use and limits

Use `pipeline_name: rna_secondary_structure_prediction` with `rna`:

```text
Predict RNA secondary structure rna: "path/to/sequences.fasta" temperature_c 37
```

The prediction is an equilibrium minimum-free-energy model. It does not model
pseudoknots, tertiary structure, cellular conditions, or experimental probing.
