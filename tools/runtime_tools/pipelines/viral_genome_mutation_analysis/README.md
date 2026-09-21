# Viral genome mutation analysis

Virmut compares assembled viral genomes with a reference using minimap2,
extracts nucleotide variants, builds a SNP matrix and summary, and optionally
runs IQ-TREE when enough samples and variable sites are available.

## Requirements

- Bash and Python 3.9 or newer with PyYAML;
- `minimap2` on `PATH` for genome alignment;
- `iqtree2` or `iqtree` only for optional phylogeny.

The core matrix, variant, and summary outputs do not require IQ-TREE. The
standard `local` reference mode needs no database. `species` and `taxonid`
modes require a local reference FASTA and metadata configured with `VIRUS_DB`
and `VIRUS_METADATA` (or the equivalent paths used by the runtime config).

## Inputs and parameters

- `input_path`: one query FASTA or a directory of single-record FASTA files
  (`.fasta`, `.fa`, `.fna`);
- `reference_path`: required in `params.reference_mode: local`;
- `params.mode` (the tested mode is `fasta`), `reference_mode`, `species`,
  `taxonid`, and `threads`.

Each query FASTA must contain exactly one sequence record. Reference selection
is conditional: local mode uses `reference_path`, while the database modes use
the configured environment files.

## Standalone installation and run

```bash
chmod +x run.sh
cp config.yaml config.local.yaml
# Edit input_path, reference_path, output_dir, and params.
./run.sh config.local.yaml
```

The same configuration can be passed to `python workflow.py config.local.yaml`
when Python and the external tools are already active. The bundled example is a
small synthetic reference/query pair with introduced SNPs.

## Outputs

Required outputs are `matrix.tsv`, `variants.tsv`, and
`variants_summary.txt`. Optional outputs are `tree.fasta`, `tree.treefile`,
`tree.iqtree`, and `tree.log`; no tree is an error only when the input has
insufficient samples or variable sites.

## BioAgent use and limits

Use `pipeline_name: viral_genome_mutation_analysis` with `genomes` and a local
`reference` when required:

```text
Run viral_genome_mutation_analysis with its bundled example data and collect the results.
```

This is assembled-genome comparison. Reference choice, alignment behavior,
coverage/filter settings, and optional IQ-TREE availability affect results; it
is not a clinical or epidemiological conclusion by itself.
