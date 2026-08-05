# BacFunc

BacFunc performs gene-level whole functional annotation for metagenomes as an independently deployable pipeline. Prokka predicts proteins for assembled inputs, and eggNOG-mapper 2.1.15 annotates against eggNOG v5.

## Inputs and workflows

Content detection, including gzip magic bytes, accepts one assembled metagenome FASTA, one single-end metagenome FASTQ, or explicit paired R1/R2 FASTQ.

FASTA: `validate → assembly QC → Prokka --metagenome → eggNOG-mapper → wide gene table + long term table`

FASTQ assemble mode: validate -> Trimmomatic -> metaSPAdes -> assembly QC -> Prokka --metagenome -> eggNOG-mapper -> tables
FASTQ reads mode: validate -> Trimmomatic -> FASTQ-to-FASTA -> DIAMOND blastx against eggnog_proteins.dmnd -> eggNOG-mapper no_search annotation -> per-ortholog aggregation

Paired reads use paired Trimmomatic outputs. Unpaired outputs are retained and excluded from assembly by default.

## Deployment requirements and database

This delivery is a self-contained `runner.yaml` + `run.sh` + `workflow.py`
pipeline, not an installable Python package. Deploy it under
`BioAgent/pipelines/bacfunc-V2/` and ensure that the Conda environment named
`bacfunc` contains the required tools listed below.

The environment pins `eggnog-mapper==2.1.15`. The project does not include or download eggNOG. An existing data directory must contain `eggnog.db`, `eggnog.taxa.db`, `eggnog.taxa.db.traverse.pkl`, and `eggnog_proteins.dmnd`. Configure:

```text
BACFUNC_CONFIG
BACFUNC_EGGNOG_DATA_DIR
BACFUNC_EGGNOG_MANIFEST
```

or YAML equivalents. Precedence is explicit `--config`, `BACFUNC_CONFIG`, working-directory `config.yaml`, project `config.yaml`, then package defaults. Relative paths resolve from the YAML location.

## CLI and Agent use

```bash
bacfunc run --input contigs.fna --output results
bacfunc run --input reads_R1.fastq.gz reads_R2.fastq.gz --output results
bacfunc-fasta --assembly contigs.fna --output results --sample-id sample01
bacfunc-fastq --read1 reads_R1.fastq.gz --read2 reads_R2.fastq.gz --output results
bacfunc doctor --json
bacfunc version
```

The runner YAML files expose general file-list, directory-batch, FASTA-only, and explicit FASTQ Agent contracts. The shell and PowerShell wrappers locate only this project and use the caller's Python. `--dry-run` builds an auditable command plan without requiring tools.

## Outputs

- `gene_annotations.tsv`: wide table preserving all eggNOG header columns, including unknown future columns;
- `annotation_terms.tsv`: deterministic long table for GO, COG, eggNOG OG, EC, KEGG, BRITE, CAZy, BiGG, and PFAM terms;
- `raw/<sample>.emapper.annotations` plus seed-ortholog/hit files;
- `raw/reads_diamond.tsv` and `raw/reads.emapper.seed_orthologs` in reads mode;
- reads-mode wide rows add accession, supporting-read, identity, query-coverage, and bit-score fields;
- retained Prokka outputs under `raw/prokka/`;
- `status.json`, `manifest.json`, `qc.json`, per-tool logs, and retained work files.

BacFunc does not calculate counts, TPM, abundance, pathway completeness, fixed panels, or automated biological conclusions. A term is not evidence that a complete pathway exists.

## Scientific limitations and testing

Results depend on assembly, gene prediction, search sensitivity, and database version. Metagenome contigs are not assigned to taxa without separate evidence. Unknown eggNOG columns are preserved but not invented as namespaces.

```bash
python -m pytest
python workflow.py --help
python workflow.py version
```

Tests use synthetic annotations, SQLite fixtures, and fake executables. For server deployment, copy this directory alone, prepare eggNOG at any administrator-chosen location, configure it, run `bacfunc doctor`, and validate a small control. See the deployment documents.

## Explicit input contract and batches

The general CLI exposes run-level `--input-type {auto,reads,genome}` and `--analysis-mode {auto,reads,genome,assemble}`. Auto mode resolves FASTQ to `reads + assemble` and FASTA to `genome + genome`; an explicit declaration must match validated file content.

`genome` mode accepts metagenome contig FASTA and skips trimming and assembly. `assemble` mode preserves Trimmomatic -> metaSPAdes -> Prokka -> eggNOG-mapper.
`reads` mode runs translated read search against the existing eggNOG protein database and annotates real seed-ortholog accessions. It does not call metaSPAdes or Prokka.

Multiple FASTA samples, FASTQ singletons, and recognizable R1/R2 pairs can be passed after `--input`, or discovered from the immediate files in `--input-dir`. Inputs are never pooled. A single discovered sample uses the requested output directory directly; a batch writes one complete output contract under `<output>/<sample_id>/` for each sample. `--sample-id` is accepted only when exactly one sample is discovered.

```bash
bacfunc run --input-type genome --analysis-mode genome --input contigs.fna --output results
bacfunc run --input-type reads --analysis-mode reads --input sample_R1.fastq.gz sample_R2.fastq.gz --output reads_results
bacfunc run --input-type reads --analysis-mode assemble --input sample_R1.fastq.gz sample_R2.fastq.gz --output assembly_results
bacfunc run --input-dir batch_inputs --output batch_results --dry-run
```

Schema version 1.1 records `input_type` (`reads` or `genome`) and `analysis_mode` in `status.json`, `qc.json`, and `manifest.json`. Dry-run records only the commands in the selected supported branch.

## BioAgent packaged workflow

This packaged version is run through `runner.yaml` and `run.sh`, which use
Conda environment `bacfunc`. It requires Python with PyYAML, Prokka,
eggNOG-mapper 2.1.15, and a readable eggNOG v5 data directory containing
`eggnog.db`, `eggnog.taxa.db`, `eggnog.taxa.db.traverse.pkl`, and
`eggnog_proteins.dmnd`. Read/assembly modes additionally require Trimmomatic,
DIAMOND, and metaSPAdes.

Check deployment readiness:

```bash
conda run -n bacfunc python workflow.py doctor --config config.yaml
```

Complete genome-mode annotation is intentionally database-intensive. For a
direct run with an appropriate CPU allocation:

```bash
conda run --no-capture-output -n bacfunc python workflow.py run \
  --config config.yaml --input contigs.fasta --input-type genome \
  --analysis-mode genome --output results --threads 8 --sample-id sample01
```

In BioAgent, provide `pipeline_name: bacfunc-V2` and `input_data`. The required
outputs are `gene_annotations.tsv`, `annotation_terms.tsv`, `qc.json`, and
`status.json`; raw eggNOG files and logs remain under the run output directory.

See [`../../DATABASE_REQUIREMENTS.md`](../../DATABASE_REQUIREMENTS.md) for the
four required eggNOG v5 files and deployment-path rules. The eggNOG database is
intentionally excluded from this package and must not be uploaded to Git.
