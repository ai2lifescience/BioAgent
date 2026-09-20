# Bacterial read variant analysis

BactMut FASTQ maps bacterial reads to a reference with minimap2, sorts and
measures coverage with samtools, calls variants with bcftools, filters
low-coverage/recombination-dense positions, builds a cross-sample SNP matrix,
and optionally runs IQ-TREE.

## Requirements

The entrypoint uses the Conda environment named `bactmut`. Provide Bash, Python
3.9 or newer with PyYAML, and these required executables:

- `minimap2`, `samtools`, and `bcftools`;
- `iqtree2` or `iqtree` only for optional phylogeny.

For example:

```bash
conda create -n bactmut -c conda-forge -c bioconda \
  python=3.11 pyyaml minimap2 samtools bcftools
conda install -n bactmut -c bioconda iqtree
```

The default local-reference mode needs no database. `species` and `taxonid`
modes require GTDB representative FASTA and metadata paths in
`GTDB_DB_PATH` and `GTDB_METADATA_PATH`.

## Inputs and parameters

`input_path` accepts one single-end FASTQ or a directory containing single-end
and paired-end files with `.fastq`, `.fq`, `.fastq.gz`, or `.fq.gz` suffixes.
Common pair names `_R1`/`_R2`, `.R1`/`.R2`, `_1`/`_2`, and `.1`/`.2` are
recognized. `reference_path` is required for local mode.

Tune `params.reference_mode`, `threads`, `min_coverage`, `window_size`,
`step_size`, `sd_threshold`, and `verbose` in the runtime YAML. The pipeline
converts SAM to BAM explicitly before sorting and does not depend on ambiguous
format autodetection.

## Standalone installation and run

```bash
chmod +x run.sh
cp config.yaml config.local.yaml
# Edit input_path, reference_path, output_dir, and params.
./run.sh config.local.yaml
```

The same configuration can be passed to `workflow.py` directly when the
`bactmut` environment is already active:

```bash
conda run --no-capture-output -n bactmut python workflow.py config.local.yaml
```

## Outputs

Required outputs are `report.md`, `metrics.json`, `matrix.tsv`, `variants.tsv`,
and `variants_summary.txt`. Per-sample SAM/BAM/VCF files are retained under
`bcftools`/the work directory. `final_tree.nwk`, `tree.fasta`, IQ-TREE reports,
and logs are optional; a single sample or no surviving SNPs does not make the
run fail.

## BioAgent use and limits

Use `pipeline_name: bacterial_read_variant_analysis` with `reads` and a local
`reference` when required:

```text
Run bacterial_read_variant_analysis with its bundled example data and collect the results.
```

Results depend on read quality, mapping/reference choice, depth, filtering
thresholds, and database versions. This is a bacterial variant-comparison
workflow, not a clinical interpretation or resistance call.
