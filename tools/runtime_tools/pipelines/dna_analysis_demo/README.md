> **Runtime boundary:** Pipeline2Agent runs this bundle through its declared container boundary. Workflow tools and databases belong to that container; the agent environment does not install them.

# Generic Bioinformatics Pipeline Demo

This runnable example turns FASTQ reads, a reference FASTA, and sample metadata
into a fuller DNA-analysis artifact set: filtered reads, demonstration SAM and
VCF files, consensus sequence, QC/result tables, figures, metrics, and Markdown
and HTML reports.

It requires Python 3.9+, PyYAML, and Matplotlib. It uses no network access and
invokes no external bioinformatics programs.

Pipeline behavior and file contracts are documented in
[`DESCRIPTION.md`](DESCRIPTION.md).

## Run the included example directly

From the repository root:

```bash
bash pipelines/dna_analysis_demo/run.sh pipelines/dna_analysis_demo/config.yaml
```

Example inputs are under `data/input/`; the default run writes 16 artifacts to
`data/output/`, including a Newick tree and PNG tree figure.

## Run through BioAgent

In the web UI or CLI, provide all three named inputs:

```text
Run pipeline with pipeline_name: dna_analysis_demo reads: "pipelines/dna_analysis_demo/data/input/example_reads.fastq" reference: "pipelines/dna_analysis_demo/data/input/example_reference.fasta" metadata: "pipelines/dna_analysis_demo/data/input/example_samples.tsv"
```

Optional runtime settings are `sample_id`, `min_length`,
`min_mean_quality`, `min_base_quality`, `min_alt_fraction`, `min_alt_depth`,
`plot_dpi`, and `emit_phylogenetic_tree`.

Tree emission is enabled by default. To omit the reference-versus-consensus
demonstration tree, add:

```text
emit_phylogenetic_tree false
```

## Real-data note

This is a teaching and integration demo. Its positional comparison is not a
replacement for BWA/minimap2 plus a validated variant-calling workflow.
