# Bacterial virulence-factor detection

BacVF reports sequence homologs from a deployment-owned VFDB core database on
metagenomic contigs or reads. It does not report abundance or make a
pathogenicity diagnosis.

## Requirements and database

The entrypoint selects Conda environment `bacvf`. Provide Bash, Python 3.9 or
newer with PyYAML, plus:

- `prokka`, `abricate`, and an ABRicate `vfdb_core` database;
- `trimmomatic`, `minimap2`, and `metaspades.py` for FASTQ modes.

A typical tool environment can be provisioned with Conda/Mamba using the same
packages as the BacARG bundle, then verified with `prokka --version`,
`abricate --list`, and `minimap2 --version`. Build or install the official VFDB
core nucleotide database separately. Set `databases.abricate_datadir`,
`databases.metadata`, and `databases.manifest` in `config.yaml`; no database is
included in this repository.

## Inputs and workflows

`input_path` accepts one FASTA, one single-end FASTQ, paired R1/R2 FASTQ, or a
directory of recognizable samples. Plain and gzip-compressed files are accepted.

- `genome`: Prokka `--metagenome`, ABRicate VFDB core, and metadata joining.
- `assemble`: Trimmomatic, metaSPAdes, Prokka, and ABRicate.
- `reads`: Trimmomatic followed by minimap2 against the VFDB core sequence
  database; assembly and Prokka context are intentionally absent.

Set `input_type` and `analysis_mode` in the runtime YAML to select a branch.
Unpaired trimmed reads are excluded from assembly by default.

## Standalone installation and run

```bash
chmod +x run.sh
cp config.yaml config.local.yaml
# Edit config.local.yaml input_path/output_dir and config.yaml database paths.
./run.sh config.local.yaml
```

`run.sh` uses the `bacvf` environment. You can validate a deployment or run a
sample directly with:

```bash
conda run -n bacvf python workflow.py doctor --config config.yaml
conda run -n bacvf python workflow.py run \
  --config config.yaml --input contigs.fasta --input-type genome \
  --analysis-mode genome --output results --threads 8 --sample-id sample01
```

`--input-dir` supports batches and `--dry-run` writes an auditable command plan
without invoking external tools.

## Outputs

Required artifacts are `vf_hits.tsv`, `qc.json`, and `status.json`; the bundle
also writes `vf_hits.jsonl`. Raw ABRicate tables, minimap2 PAFs, Prokka output,
`manifest.json`, QC metrics, and per-tool logs remain in the output workspace.
A no-hit run is successful and produces a schema-valid empty hit table.

## BioAgent use and limits

Use `pipeline_name: bacterial_virulence_factor_detection` with `input_data`.
For the bundled fixture:

```text
Run bacterial_virulence_factor_detection with its bundled example data and collect the results.
```

A virulence-factor homolog does not prove that a sample is pathogenic or identify
its host species. Results depend on assembly, gene prediction, thresholds, and
VFDB curation; the workflow does not perform taxonomy, binning, ARG detection,
or abundance estimation.
