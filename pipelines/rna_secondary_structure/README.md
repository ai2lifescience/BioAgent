# RNA Secondary Structure Pipeline Environment

This pipeline predicts minimum-free-energy RNA secondary structures with the
ViennaRNA `RNAfold` command and exposes normalized results as BioAgent
artifacts. It is an independent implementation and does not import Biomni.

## Requirements

- Ubuntu with Bash and Python 3.11 or newer.
- PyYAML, already included in the BioAgent requirements.
- ViennaRNA with `RNAfold` available on `PATH`.

A pinned Bioconda environment is recommended:

```bash
conda install -c bioconda viennarna=2.7.0
RNAfold --version
```

Start BioAgent from the same activated environment so its subprocess can find
`RNAfold`.

## Run through BioAgent

```text
Predict RNA secondary structure rna: "path/to/sequences.fasta" temperature_c 37
```

The explicit equivalent is:

```text
Run pipeline with pipeline_name: rna_secondary_structure rna: "path/to/sequences.fasta"
```

An artificial input and representative synthetic outputs are committed under
`data/`. They document the file contract and do not claim to be experimentally
or computationally validated results.
