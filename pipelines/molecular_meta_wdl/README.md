# Molecular Meta WDL Pipeline

This folder exposes the molecular typing WDL workflow through BioAgent's
standard pipeline runner.

Files:

- `runner.yaml`: BioAgent-facing metadata, input slots, parameter overrides,
  and output mapping.
- `workflow.wdl`: WDL workflow for read cleaning, alignment, trimming, and
  typing.
- `inputs.json`: default WDL workflow inputs.
- `options.json`: optional WDL engine options metadata copied into each run.
- `data/molecular_demo_h1n1.fastq.gz`: example read input.

Web UI example:

```text
Run pipeline with pipeline_name: molecular_meta_wdl
```

BioAgent will ask for explicit runtime files. The WDL workflow needs `read1`,
`reference`, and `nextclade_dataset`; `read2` is optional. For `reference` and
`nextclade_dataset`, provide one or more file paths separated by commas or
semicolons:

```text
Run pipeline with pipeline_name: molecular_meta_wdl read1: "runtime/sessions/<session_id>/artifacts/uploads/sample.fastq.gz" reference: "path/to/ref.fasta" nextclade_dataset: "path/to/reference.fasta,path/to/genome_annotation.gff3,path/to/pathogen.json"
```

Runtime parameters can be overridden by name, for example:

```text
Run pipeline with pipeline_name: molecular_meta_wdl read1: "sample.fastq.gz" reference: "ref.fasta" nextclade_dataset: "reference.fasta,genome_annotation.gff3" sample: "sample_001" pathogen: H1N1 threads: 8
```
