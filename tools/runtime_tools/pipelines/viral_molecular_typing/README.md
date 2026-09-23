# Viral molecular typing

This WDL 1.0 pipeline performs reference-based viral read processing, consensus
generation, and Nextclade typing for configured influenza or SARS-CoV-2 data.
The stages are `fastp -> BWA -> SAMtools filtering/deduplication -> BamUtil
trimming -> iVar consensus -> Nextclade`.

## Requirements

- miniwdl for local execution, or Java for the standalone Cromwell command;
- a reachable Cromwell Server when `CROMWELL_URL` is set, with shared paths
  for BioAgent, Cromwell, and task containers;
- Docker or the configured backend with `cncb/molecular-wdl:v1.0` (or a
  compatible image);
- a task image containing Bash/core utilities, fastp, BWA, SAMtools, BamUtil,
  iVar, Nextclade, and Java;
- reference FASTA/index files and a compatible Nextclade dataset. The dataset
  must include `reference.fasta`; annotation, tree, and pathogen JSON files are
  used when supplied;
- the default profile can require up to 16 CPUs and 32 GB RAM.

The reference and Nextclade data are not included. Replace every deployment
path in `inputs.json` with paths visible inside the Cromwell task image.

BioAgent defaults to local miniwdl when `CROMWELL_URL` is unset. For Cromwell
submission, configure and verify its endpoint before starting BioAgent:

```bash
export CROMWELL_URL=http://192.168.164.39:39000
curl "$CROMWELL_URL/engine/v1/status"
docker image inspect cncb/molecular-wdl:v1.0
```

## Inputs

- `run_molecular_typing.file1Path`: required read 1 FASTQ/FASTQ.GZ;
- `file2Path`: optional read 2;
- `REF`: reference FASTA and optional BWA index files;
- `NEXTCLADE_DATASET`: Nextclade dataset files;
- `sample`, `pathogen`, `MIN_LENGTH`, `MIN_QUAL`, `THREADS`, and
  `docker_image`;
- optional `HA_REFNAME`, task CPU, and legacy metadata fields.

Influenza runs need `HA_REFNAME` for the HA reference contig. SARS-CoV-2 aliases
are normalized by the workflow, and H3N2 uses its dedicated Nextclade columns.

## Run standalone

```bash
cp inputs.json inputs.local.json
# Replace reads, reference/index, and Nextclade dataset paths.
java -jar cromwell.jar run workflow.wdl \
  -i inputs.local.json -o options.json
```

Use a Cromwell REST service for remote execution. BioAgent submits the same WDL
and copies the declared files after success.

## Outputs

- `result.csv`: summarized clade/subclade, quality, coverage, and depth;
- `nextclade.tsv` and `nextclade.json`;
- `consensus.fa`;
- `final.bam`.

## BioAgent use and limits

Use `pipeline_name: viral_molecular_typing` with `read1` and optional `read2`.
Typing quality depends on coverage, the selected reference, the Nextclade data
release, and pathogen-specific thresholds; the pipeline does not replace
manual review of low-quality samples.
