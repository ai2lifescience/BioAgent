# Bacterial functional annotation

BacFunc performs gene-level functional annotation for metagenomic contigs or
reads. Assembled-input modes use Prokka followed by eggNOG-mapper 2.1.15;
read mode uses translated DIAMOND searches followed by eggNOG-mapper annotation.

## Requirements and database

The entrypoint selects Conda environment `bacfunc`. Provide Bash, Python 3.9 or
newer with PyYAML, and:

- `prokka`, `trimmomatic`, `metaspades.py`, and `diamond`;
- `emapper.py` from eggNOG-mapper **2.1.15**.

For example, create the environment with Conda/Mamba and install the matching
Bioconda packages, then verify `emapper.py --version`, `prokka --version`, and
`diamond version`. The eggNOG v5 data directory is deployment-managed and must
contain at least `eggnog.db`, `eggnog.taxa.db`,
`eggnog.taxa.db.traverse.pkl`, and `eggnog_proteins.dmnd`. Set
`databases.eggnog.data_dir` and optionally `databases.eggnog.manifest` in
`config.yaml`; the database is not bundled or downloaded by normal runs.

## Inputs and workflows

`input_path` accepts one assembled FASTA, one single-end FASTQ, a paired FASTQ
set, or a directory of recognizable samples. Gzip input is supported.

- `genome`: validate, QC, Prokka `--metagenome`, and eggNOG-mapper.
- `assemble`: trim reads, assemble with metaSPAdes, run Prokka, then annotate.
- `reads`: trim reads, convert them to collision-free FASTA identifiers, run
  DIAMOND against `eggnog_proteins.dmnd`, and annotate seed orthologs without
  re-running a search in eggNOG-mapper.

Set `input_type` and `analysis_mode` explicitly when needed. Paired reads use
paired trimming outputs; unpaired reads are retained but excluded from assembly
by default.

## Standalone installation and run

Copy the directory to a host with the `bacfunc` environment and eggNOG data:

```bash
chmod +x run.sh
cp config.yaml config.local.yaml
# Edit config.local.yaml input_path/output_dir and config.yaml database paths.
./run.sh config.local.yaml
```

The direct CLI is useful for deployment checks and dry runs:

```bash
conda run -n bacfunc python workflow.py doctor --config config.yaml
conda run -n bacfunc python workflow.py run \
  --config config.yaml --input contigs.fasta --input-type genome \
  --analysis-mode genome --output results --threads 8 --sample-id sample01
```

Use `--input-dir` for batches and `--dry-run` to validate a command plan without
running external tools.

## Outputs

The stable outputs are `gene_annotations.tsv`, `annotation_terms.tsv`, `qc.json`,
and `status.json`. The run also retains eggNOG annotation/seed-ortholog files,
read-mode DIAMOND tables, Prokka outputs, `manifest.json`, tool logs, and work
files. The long table preserves GO, COG, eggNOG OG, EC, KEGG, BRITE, CAZy,
BiGG, and PFAM namespaces.

## BioAgent use and limits

Use `pipeline_name: bacterial_functional_annotation` with `input_data`; the
`runner.yaml` file is the complete agent contract. A bundled request is:

```text
Run bacterial_functional_annotation with its bundled example data and collect the results.
```

The workflow does not calculate abundance, TPM, pathway completeness, bin
contigs, assign taxonomy, or make automated biological conclusions. Results
depend on assembly, gene prediction, search sensitivity, and eggNOG version.
