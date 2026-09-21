# Antimicrobial resistance detection

BacARG reports MEGARes 3.0 sequence-homology candidates from bacterial or metagenomic
contigs and reads. It is an independently deployable bundle; it does not infer
abundance, phenotype, or species attribution.

## Requirements

The entrypoint selects Conda environment `bacarg`. Provide Bash, Python 3.9 or
newer with PyYAML, and these executables in that environment:

- `prokka`, `abricate`, and an ABRicate MEGARes 3.0 database;
- `trimmomatic`, `minimap2`, and `metaspades.py` for FASTQ assembly/read modes.

A typical environment can be prepared with Conda/Mamba, then checked with:

```bash
conda create -n bacarg -c conda-forge -c bioconda \
  python=3.11 pyyaml prokka abricate trimmomatic minimap2 spades
conda run -n bacarg prokka --version
conda run -n bacarg abricate --list
conda run -n bacarg minimap2 --version
```

The MEGARes database and its normalized metadata are not included. Install or
prepare the official database separately, then set the `databases.abricate_datadir`,
`databases.metadata`, and `databases.manifest` paths in `config.yaml`. The
`megares_v3` ABRicate database must be visible from the `bacarg` environment.

## Inputs and modes

`input_path` may be one assembled FASTA (`.fasta`, `.fa`, `.fna`), one FASTQ
(`.fastq`, `.fq`, including gzip variants), a pair of FASTQ files, or a directory
of recognizable samples. The workflow detects content, including gzip magic bytes.

- `genome`: validate contigs, run assembly QC, Prokka, ABRicate MEGARes, and
  metadata/context joining.
- `assemble`: trim FASTQ, assemble with metaSPAdes, then annotate contigs.
- `reads`: trim FASTQ and map directly with minimap2 to MEGARes; Prokka and
  assembly context are intentionally absent.

Set `input_type` and `analysis_mode` in the runtime YAML when automatic detection
is not sufficient. Paired reads use paired Trimmomatic outputs; unpaired reads
are retained but excluded from assembly by default.

## Standalone installation and run

Copy this directory to any host with the environment and database available. The
bundle is self-contained and does not need the BioAgent source tree:

```bash
chmod +x run.sh
cp config.yaml config.local.yaml
# Edit config.local.yaml input_path, output_dir, input_type, and analysis_mode.
# Edit config.yaml database paths if they differ from your deployment.
./run.sh config.local.yaml
```

`run.sh` uses the hard-coded `bacarg` environment and invokes the bundled
`workflow.py`. For a configuration check or a dry command plan, use the workflow
CLI directly:

```bash
conda run -n bacarg python workflow.py doctor --config config.yaml
conda run -n bacarg python workflow.py run --help
conda run -n bacarg python workflow.py run \
  --config config.yaml --input contigs.fasta --input-type genome \
  --analysis-mode genome --output results --threads 8 --sample-id sample01
```

The direct CLI also supports `--input-dir` for batches and `--dry-run`; a dry run
validates inputs and records commands but is not a biological result.

## Outputs

Required artifacts are `arg_hits.tsv`, `qc.json`, and `status.json`. The bundle
also writes `arg_hits.jsonl` when enabled. Work and provenance files include:

- raw ABRicate tables, minimap2 PAF alignments, and Prokka outputs;
- `manifest.json` with input hashes, commands, parameters, database provenance,
  and warnings;
- `qc.json` with input, assembly, gene-prediction, and annotation metrics;
- separate logs for Trimmomatic, metaSPAdes, Prokka, ABRicate, and the pipeline.

## BioAgent use

The agent-facing contract is in `runner.yaml`. Provide `pipeline_name:
antimicrobial_resistance_detection` and `input_data`; the runtime stages the
input and collects the declared artifacts. A bundled smoke request is:

```text
Run antimicrobial_resistance_detection with its bundled example data and collect the results.
```

## Interpretation limits

Hits are sequence-homology candidates. The workflow does not detect mechanisms
represented only by point mutations, establish phenotypic resistance, quantify
abundance, bin contigs, or assign a hit to a species. Assembly quality, gene
calling, database curation, thresholds, and contig fragmentation affect results.
