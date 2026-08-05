# BacVF

BacVF annotates sequence homologs from a deployment-owned VFDB core database on metagenome contigs. It is independent of BacPath, BacARG, and BacFunc and does not report abundance or make a pathogenicity diagnosis.

## Inputs and workflow

Content detection, including gzip magic bytes, accepts one metagenome FASTA/FASTA.GZ, one single-end FASTQ/FASTQ.GZ, or explicit paired R1/R2 FASTQ files.

FASTA: `validate → assembly QC → Prokka --metagenome → ABRicate VFDB core on contigs → metadata/context join`

FASTQ assemble mode: validate -> Trimmomatic -> metaSPAdes -> assembly QC -> Prokka --metagenome -> ABRicate VFDB core -> metadata/context join
FASTQ reads mode: validate -> Trimmomatic -> minimap2 -x sr against VFDB core sequences -> per-factor read aggregation -> metadata join

Paired Trimmomatic outputs feed metaSPAdes. Unpaired outputs are retained and excluded by default; administrators can enable them in YAML.

## Deployment requirements and database

This delivery is a self-contained `runner.yaml` + `run.sh` + `workflow.py`
pipeline, not an installable Python package. Deploy it under
`BioAgent/pipelines/bacvf-V2/` and ensure that the Conda environment named
`bacvf` contains the required tools listed below.

Normal runs neither bundle nor download VFDB. Follow `docs/DATABASE_SETUP.md` to build the custom `vfdb_core` database from official core nucleotide FASTA and metadata. Configure it in YAML or with:

```text
BACVF_CONFIG
BACVF_ABRICATE_DATADIR
BACVF_VFDB_METADATA
BACVF_VFDB_MANIFEST
```

Precedence is explicit `--config`, `BACVF_CONFIG`, working-directory `config.yaml`, project `config.yaml`, then package defaults. Relative paths resolve from the selected YAML.

## CLI and Agent use

```bash
bacvf run --input contigs.fna --output results
bacvf run --input reads_R1.fastq.gz reads_R2.fastq.gz --output results
bacvf-fasta --assembly contigs.fna --output results --sample-id sample01
bacvf-fastq --read1 reads_R1.fastq.gz --read2 reads_R2.fastq.gz --output results
bacvf doctor --json
bacvf version
```

`runner.yaml` defines the single BioAgent runtime contract, while `run.sh` invokes the local `workflow.py` implementation. `--dry-run` validates and records command argument lists without requiring tools; its empty result is explicitly marked as a dry run.

## Outputs

- `vf_hits.tsv` and `vf_hits.jsonl`: deterministic VFDB joins;
- `raw/abricate_<database>.tsv` and `raw/prokka/` for assemble/genome mode;
- `raw/minimap2_<database>.paf` for reads mode;
- `status.json`, `manifest.json`, and `qc.json`;
- per-tool logs and retained `work/` by default.

A no-hit ABRicate result is successful and produces a header-only TSV plus empty JSONL.

## Scientific limitations

Detecting a virulence-factor homolog does not prove that a sample is pathogenic. Without binning or taxonomic evidence, a metagenome contig hit cannot be assigned directly to a particular species. Fragmentation, thresholds, database curation, assembly, and gene prediction affect results. BacVF does not perform ARG annotation, abundance estimation, binning, taxonomy, or a final pathogenicity call.

## Testing and server deployment

```bash
python -m pytest
python workflow.py --help
python workflow.py version
```

Tests use synthetic fixtures and fake executables. Copy this directory alone, create its environment, prepare VFDB separately at any deployment-chosen location, configure it, run `bacvf doctor`, and validate a small control before production. See `DESCRIPTION.md` and `docs/DEPLOYMENT.md`.

## Explicit input contract and batches

The general CLI exposes run-level `--input-type {auto,reads,genome}` and `--analysis-mode {auto,reads,genome,assemble}`. Auto mode resolves FASTQ to `reads + assemble` and FASTA to `genome + genome`; an explicit declaration must match validated file content.

`genome` mode accepts metagenome contig FASTA and skips trimming and assembly. `assemble` mode preserves Trimmomatic -> metaSPAdes -> Prokka -> ABRicate.
`reads` mode runs Trimmomatic -> minimap2 directly against the deployed VFDB core nucleotide `sequences` file. It does not call metaSPAdes or Prokka; unavailable contig/context fields stay empty.

Multiple FASTA samples, FASTQ singletons, and recognizable R1/R2 pairs can be passed after `--input`, or discovered from the immediate files in `--input-dir`. Inputs are never pooled. A single discovered sample uses the requested output directory directly; a batch writes one complete output contract under `<output>/<sample_id>/` for each sample. `--sample-id` is accepted only when exactly one sample is discovered.

```bash
bacvf run --input-type genome --analysis-mode genome --input contigs.fna --output results
bacvf run --input-type reads --analysis-mode reads --input sample_R1.fastq.gz sample_R2.fastq.gz --output reads_results
bacvf run --input-type reads --analysis-mode assemble --input sample_R1.fastq.gz sample_R2.fastq.gz --output assembly_results
bacvf run --input-dir batch_inputs --output batch_results --dry-run
```

Schema version 1.1 records `input_type` (`reads` or `genome`) and `analysis_mode` in `status.json`, `qc.json`, and `manifest.json`. Dry-run records only the commands in the selected supported branch.

## BioAgent packaged workflow

This packaged version is run through `runner.yaml` and `run.sh`, which use
Conda environment `bacvf`. Required production tools are Python with PyYAML,
Prokka, ABRicate with a configured VFDB-core database, and for read/assembly
modes Trimmomatic, minimap2, and metaSPAdes.

Check deployment readiness before production:

```bash
conda run -n bacvf python workflow.py doctor --config config.yaml
```

For a direct assembled-contig run:

```bash
conda run -n bacvf python workflow.py run \
  --config config.yaml --input contigs.fasta --input-type genome \
  --analysis-mode genome --output results --threads 8 --sample-id sample01
```

In BioAgent, use `pipeline_name: bacvf-V2` and `input_data`. The required
outputs are `vf_hits.tsv`, `qc.json`, and `status.json`; a no-hit result is a
valid successful result with an otherwise schema-complete output set.

Configure the deployment-owned VFDB-core database with
`BACVF_ABRICATE_DATADIR` (or the equivalent YAML path); it must provide the
configured `vfdb_core` ABRicate database and its metadata. The database is
excluded from this package and must not be uploaded to Git.
