# Metagenomic pathogen identification

This WDL 1.0 workflow performs post-QC pathogen detection against optional
bacterial, viral, fungal, and parasite minimap2 indexes. It arbitrates hits
across databases, assigns taxa, calculates coverage, and applies confidence
filters.

## Requirements

- miniwdl for local execution, or Java for the standalone Cromwell command;
- a reachable Cromwell Server when `CROMWELL_URL` is set, with a shared
  filesystem between BioAgent, Cromwell, and task containers;
- Docker or the configured backend with `mscan-detection:v1.0` (or a compatible
  image), including the Stage 1–6 Python/minimap2 entrypoints;
- mounted minimap2 indexes and annotation tables for every database type you
  enable;
- the default resource profile can require 8 mapping CPUs, 4 stage CPUs,
  64 GB mapping memory, and 500 GB disk.

The task image and databases are not included. Paths in `inputs.json` must be
valid inside the Cromwell task runtime. Leave unused database paths unset rather
than passing empty strings.

BioAgent defaults to local miniwdl when `CROMWELL_URL` is unset. For Cromwell
submission, configure and verify its endpoint before starting BioAgent:

```bash
export CROMWELL_URL=http://192.168.164.39:39000
curl "$CROMWELL_URL/engine/v1/status"
```

## Inputs and stages

- `MetagenomicDetection.sequence_file1`: required host-filtered FASTQ R1;
- `MetagenomicDetection.sequence_file2`: optional R2;
- `db_bacteria`, `db_virus`, `db_fungi`, `db_parasite`: optional minimap2 indexes;
- `anno_pathogen`, `anno_virus`, `non_report_list`, `white_list`, and
  `posstat_file`: annotation/filter resources;
- mapping, arbitration, Stage 6, image, and resource settings in `inputs.json`.

FASTQ and FASTQ.GZ are accepted; compression is detected from content. The
workflow expects reads after host/vector QC, normally from
`metagenomic_read_quality_control`.

## Run standalone

```bash
cp inputs.json inputs.local.json
# Replace sequence, database, and annotation paths in inputs.local.json.
java -jar cromwell.jar run pipeline.wdl \
  -i inputs.local.json -o options.json
```

The same WDL can be submitted to a Cromwell REST service. BioAgent preserves the
submission response, polls to completion, and retries temporary workflow-ID
visibility delays.

## Outputs

The declared files are `priority_with_confidence.tsv`,
`priority_microbe_panel.tsv`, `sample_overview.tsv`,
`stage2_read_accounting.tsv`, and `stage2_crossdb_signature.tsv`. Intermediate
mapping and stage files remain in Cromwell's output area when
`keep_intermediate` is enabled.

## BioAgent use and limits

Use `pipeline_name: metagenomic_pathogen_identification` with `sequence_file1`
and optional `sequence_file2`. Database curation, mapping thresholds, host
filtering, and the confidence policy determine sensitivity and specificity;
a reported signal is evidence for review, not a diagnosis.
