# DNA analysis shell template

> Pipeline dependencies belong to the pipeline container. The BioAgent environment does not install workflow tools.

This educational shell template turns one FASTQ file, a reference FASTA, and a
sample metadata table into a deterministic set of QC, comparison, report, and
figure artifacts. Its positional comparison is a format demonstration, not a
validated aligner or variant caller.

Run it through the runtime with:

```text
Run template_bio with its bundled example data and collect the results.
```

The `runner.yaml` file is the complete agent-facing contract. Parameters such as
`min_length`, `min_mean_quality`, and `emit_phylogenetic_tree` are declared there.
