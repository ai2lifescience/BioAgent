# Pathogen variant risk assessment

This WDL 1.0 workflow aligns clean pathogen reads, calls variants with iVar,
annotates effects with snpEff, and creates a pathogen-specific risk report. It
supports the configured influenza and SARS-CoV-2 reference/resource sets.

## Requirements

- Java and a reachable Cromwell Server (`CROMWELL_URL`, default
  `http://127.0.0.1:8000`), with shared paths between submitter, Cromwell, and
  task containers;
- Docker or the configured backend with `cncb/risk-wdl:v1.0` (or a compatible
  image), including `/app/run_variant_risk.sh` and
  `/app/lib/docker_bin_paths.sh`;
- reference FASTA, snpEff config/database/tarball, segment table, and risk
  annotation files readable by Cromwell;
- the default profile can require 8 CPUs, 64 GB RAM, 200 GB disk, and Java
  memory for snpEff.

All pathogen resources are deployment-managed and omitted from this bundle.
Do not use the example absolute paths in `inputs.json` without replacing them.

Check Cromwell:

```bash
export CROMWELL_URL=http://127.0.0.1:8000
curl "$CROMWELL_URL/engine/v1/status"
```

## Inputs and analysis

- `VariantRisk.fastq_r1`: required clean FASTQ R1;
- `VariantRisk.fastq_r2`: optional R2;
- `sample_id`, `pathogen`, and `log_tag`;
- `reference_fasta`, `snpeff_config`, `snpeff_db`,
  `snpeff_data_tarball`, `segments_tsv`, and `reference_label`;
- iVar/map quality, depth, allele-frequency, trimming, thread, and resource
  parameters in `inputs.json`;
- optional influenza H/N or SARS-CoV-2 risk annotation tables.

Processing is `BWA -> filtering/deduplication/trimming -> iVar -> snpEff ->
risk tables`. Choose `H1N1`, `H3N2`, or `SARS_CoV_2` consistently with the
matching references and annotation resources.

## Run standalone

```bash
cp inputs.json inputs.local.json
# Replace reads and every pathogen-resource path in inputs.local.json.
java -jar cromwell.jar run pipeline.wdl \
  -i inputs.local.json -o options.json
```

A Cromwell REST submission is also supported. BioAgent submits, polls, and
collects the same outputs after Cromwell reports `Succeeded`.

## Outputs

- `final_variant_risk_report.tsv`;
- `segments.tsv` with segment mean-depth summaries;
- `risk_assessment_output.tar` containing the complete task output directory.

## BioAgent use and limits

Use `pipeline_name: pathogen_variant_risk_assessment` with `read1` and optional
`read2`; configure pathogen-specific resources in the deployment input JSON.
Risk annotations are reference- and threshold-dependent evidence, not a general
clinical risk score. Coverage, contamination, reference choice, and database
versions can change the interpretation.
