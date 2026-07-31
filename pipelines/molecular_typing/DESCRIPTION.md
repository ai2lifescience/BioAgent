# Molecular Meta WDL Pipeline Description

## Function

This WDL 1.0 pipeline performs reference-based viral read processing,
consensus generation, and Nextclade typing for influenza or SARS-CoV-2 data.

```text
single-end or paired-end FASTQ
  -> fastp read cleaning
  -> BWA alignment and SAMtools filtering/deduplication
  -> 3-base BAM trimming with BamUtil
  -> iVar consensus generation
  -> Nextclade typing and quality assessment
  -> typing CSV, Nextclade files, consensus FASTA, and BAM
```

## Inputs

Required workflow inputs include:

- `file1Path`: read 1 FASTQ.
- `REF`: one or more reference files, including a `.fa`, `.fasta`, or `.fna`
  reference sequence. BWA and FASTA indexes are built when absent.
- `NEXTCLADE_DATASET`: Nextclade dataset files. `reference.fasta` is required;
  annotation, tree, and pathogen JSON files are used when supplied.
- `sample`, `pathogen`, `MIN_LENGTH`, `MIN_QUAL`, `THREADS`, and
  `docker_image`.

Optional inputs include read 2 (`file2Path`), `HA_REFNAME`, `task_cpu`, and
legacy metadata fields retained by the workflow interface.

Influenza runs require `HA_REFNAME` to identify the HA reference contig.
SARS-CoV-2 pathogen aliases are normalized to the workflow's SARS-CoV-2
branch. H3N2 uses its dedicated Nextclade output-column mapping.

## Outputs

- `result.csv`: summarized clade/subclade, quality, coverage, and depth.
- `nextclade.tsv`: Nextclade tabular results.
- `nextclade.json`: Nextclade JSON results.
- `consensus.fa`: generated consensus sequence.
- `final.bam`: filtered alignment BAM.

BioAgent copies completed WDL outputs to `data/output/` as declared in
`runner.yaml`.
