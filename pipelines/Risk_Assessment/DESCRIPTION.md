# Variant Risk Assessment Pipeline Description

## Function

This WDL 1.0 workflow aligns clean FASTQ reads to a pathogen reference,
calls variants with iVar, annotates effects with snpEff, and produces a
pathogen-specific risk report.

```text
FASTQ (R1[, R2])
  -> BWA align / filter / dedup / trim
  -> iVar variant calling
  -> snpEff amino-acid annotation
  -> pathogen risk tables (HA/NA or Spike)
  -> final risk report and complete output archive
```

## Inputs

- `VariantRisk.fastq_r1` / optional `fastq_r2`: clean reads after host removal.
- `sample_id`, `pathogen`, and `log_tag`: sample and pathogen metadata.
- `reference_fasta`, `snpeff_config`, `snpeff_db`,
  `snpeff_data_tarball`, `segments_tsv`, and `reference_label`.
- Variant thresholds: `mapq`, `baseq`, `ivar_min_depth`, `ivar_min_af`,
  `highconf_depth`, `highconf_af`, `segment_depth_threshold`, `trim_bp`.
- Optional influenza H/N and SARS-CoV-2 spike risk annotation tables.
- Thread, Java memory, Docker image, CPU, memory, and disk settings.

## Outputs

- `final_variant_risk_report.tsv`: final annotated risk report.
- `segments.tsv`: segment mean depth summary.
- `risk_assessment_output.tar`: complete task output directory.

BioAgent collects these outputs after Cromwell reports `Succeeded`.
