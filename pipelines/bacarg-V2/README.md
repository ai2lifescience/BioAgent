# BacARG

BacARG annotates MEGARes 3.0 sequence-homology antimicrobial-resistance candidates on metagenome contigs. It is an independent pipeline: it does not import BacPath, BacVF, or BacFunc and does not report abundance.

## Inputs and workflow

Input is detected from content, including gzip magic bytes:

- one FASTA/FASTA.GZ: supplied assembled metagenome contigs;
- one FASTQ/FASTQ.GZ: single-end metagenome reads;
- two FASTQ/FASTQ.GZ files: ordered R1/R2 metagenome reads.

FASTA: `validate → assembly QC → Prokka --metagenome → ABRicate MEGARes on contigs → metadata/context join`

FASTQ assemble mode: validate -> Trimmomatic -> metaSPAdes -> assembly QC -> Prokka --metagenome -> ABRicate MEGARes -> metadata/context join
FASTQ reads mode: validate -> Trimmomatic -> minimap2 -x sr against MEGARes sequences -> per-gene read aggregation -> metadata join

Paired reads use paired Trimmomatic outputs. Unpaired outputs are retained and are excluded from assembly by default; administrators can enable `tools.assembler.include_unpaired`.

## Installation

```bash
conda env create -f environment.yml
conda activate <environment-chosen-by-deployer>
python -m pip install -e .
```

Databases are not bundled or downloaded by normal runs. Prepare official MEGARes nucleotide FASTA and metadata as described in `docs/DATABASE_SETUP.md`, then either edit a copy of `config.example.yaml` or set:

```text
BACARG_CONFIG
BACARG_ABRICATE_DATADIR
BACARG_MEGARES_METADATA
BACARG_MEGARES_MANIFEST
```

Configuration precedence is explicit `--config`, `BACARG_CONFIG`, working-directory `config.yaml`, project `config.yaml`, then the package default. Relative paths are relative to the selected YAML.

## CLI and Agent entry points

```bash
bacarg run --input contigs.fna --output results
bacarg run --input reads_R1.fastq.gz reads_R2.fastq.gz --output results
bacarg-fasta --assembly contigs.fna --output results --sample-id sample01
bacarg-fastq --read1 reads_R1.fastq.gz --read2 reads_R2.fastq.gz --output results
bacarg doctor --json
bacarg version
```

`runner.yaml`, `runner.directory.yaml`, `runner.fasta.yaml`, and `runner.fastq.yaml` describe the general and explicit Agent contracts. `run.sh` and `run.ps1` locate only their own project and never activate a fixed environment.

Use `--dry-run` to validate input/configuration and write a command plan without requiring external tools. It records `dry_run: true`; its empty hit table is not a biological result.

## Outputs

- `arg_hits.tsv` and `arg_hits.jsonl`: deterministic candidate hits and MEGARes hierarchy;
- `raw/abricate_<database>.tsv`: unmodified assemble/genome ABRicate table;
- `raw/minimap2_<database>.paf`: unmodified direct-reads alignments;
- `raw/prokka/`: retained Prokka FAA, FFN, GFF, TSV, and TXT;
- `status.json`: running/success/failed state and hit count;
- `manifest.json`: input hashes, argument-list commands, parameters, database provenance, and warnings;
- `qc.json`: input, assembly, gene-prediction, and annotation metrics;
- separate logs for Trimmomatic, metaSPAdes, Prokka, ABRicate, and the pipeline.

## Scientific limitations

This project reports MEGARes 3.0 sequence-homology candidate hits. It does not detect resistance caused only by point mutations and does not equate a candidate with phenotypic resistance. Entries requiring a SNP/indel confirmation remain `candidate_hit`, with `snp_status=not_evaluated`. The workflow does not claim to detect every resistance mechanism.

Assembly, gene calling, database curation, thresholds, and contig fragmentation affect results. FASTA input is never assumed to be a complete isolate genome.

## Testing and deployment

```bash
python -m pytest
python -m bacarg --help
python -m bacarg version
```

Local tests use synthetic files and fake tools. Copy this directory alone to a server, create its environment, prepare the database anywhere permitted, configure paths, run `bacarg doctor`, then process a small validation sample. See `DESCRIPTION.md` and `docs/DEPLOYMENT.md`.

## Explicit input contract and batches

The general CLI exposes run-level `--input-type {auto,reads,genome}` and `--analysis-mode {auto,reads,genome,assemble}`. Auto mode resolves FASTQ to `reads + assemble` and FASTA to `genome + genome`; an explicit declaration must match validated file content.

`genome` mode accepts metagenome contig FASTA and skips trimming and assembly. `assemble` mode preserves Trimmomatic -> metaSPAdes -> Prokka -> ABRicate.
`reads` mode runs Trimmomatic -> minimap2 directly against the deployed MEGARes nucleotide `sequences` file. It does not call metaSPAdes or Prokka; unavailable contig/context fields stay empty.

Multiple FASTA samples, FASTQ singletons, and recognizable R1/R2 pairs can be passed after `--input`, or discovered from the immediate files in `--input-dir`. Inputs are never pooled. A single discovered sample uses the requested output directory directly; a batch writes one complete output contract under `<output>/<sample_id>/` for each sample. `--sample-id` is accepted only when exactly one sample is discovered.

```bash
bacarg run --input-type genome --analysis-mode genome --input contigs.fna --output results
bacarg run --input-type reads --analysis-mode reads --input sample_R1.fastq.gz sample_R2.fastq.gz --output reads_results
bacarg run --input-type reads --analysis-mode assemble --input sample_R1.fastq.gz sample_R2.fastq.gz --output assembly_results
bacarg run --input-dir batch_inputs --output batch_results --dry-run
```

Schema version 1.1 records `input_type` (`reads` or `genome`) and `analysis_mode` in `status.json`, `qc.json`, and `manifest.json`. Dry-run records only the commands in the selected supported branch.
