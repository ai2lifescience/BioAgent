# virmut BioAgent pipeline

Virmut calls and summarizes nucleotide variants in assembled viral genomes.
It accepts one single-record query FASTA or a directory of such FASTA files,
aligns them to a selected reference with `minimap2`, writes per-sample SNP
calls, builds a SNP matrix, and creates a compact variant summary. When there
are sufficient samples and variable sites, it also attempts IQ-TREE inference.

## Inputs

- `genomes`: one query FASTA (`.fasta`, `.fa`, or `.fna`) or a directory of
  query FASTAs. Each FASTA must contain exactly one sequence record.
- `reference`: local reference FASTA for the default `params.reference_mode:
  local`.
- `params.reference_mode`: `local`, `species`, or `taxonid`.
- `params.threads`: thread count used by the selected execution path.

For `species` or `taxonid` reference selection, set `VIRUS_DB` and
`VIRUS_METADATA` to the local reference FASTA and metadata files. These modes
are not needed for a normal local-reference analysis.

## Requirements

- Bash and Python 3.9 or newer;
- PyYAML and Biopython in the Python environment used by `run.sh`;
- `minimap2` on `PATH` for genome alignment;
- IQ-TREE (`iqtree2` or `iqtree`) only when phylogeny is wanted.

The core outputs do not depend on IQ-TREE. One-sample or no-SNP jobs therefore
remain successful even when no tree is written.

## Run

BioAgent calls `run.sh` with a generated runtime YAML. A direct run uses the
same format:

```bash
./run.sh config.yaml
```

For BioAgent, provide `pipeline_name: virmut`, `genomes`, and, for local mode,
`reference`. The bundled example files are a synthetic 12 kb reference/query
pair with five introduced SNPs and are intended only as a lightweight
integration fixture.

## Parameters and outputs

The main parameters are `mode` (`fasta` is the bundled and tested mode),
`reference_mode`, `species`, `taxonid`, and `threads`. Paths such as
`input_path`, `reference_path`, and `output_dir` are top-level configuration
values managed by BioAgent rather than biological tuning parameters.

Required outputs are:

- `matrix.tsv`: cross-sample SNP matrix;
- `variants.tsv`: called and annotated variants;
- `variants_summary.txt`: readable aggregate summary.

Optional outputs are `tree.fasta`, `tree.treefile`, `tree.iqtree`, and
`tree.log`. Their absence alone is not an error when there is insufficient
signal for tree construction.

## Included layout

- `runner.yaml`: BioAgent input/output contract;
- `config.yaml`: default paths and runtime parameters;
- `run.sh`: shell entrypoint;
- `workflow.py`: consolidated pipeline implementation;
- `data/input`: small synthetic test inputs;
- `data/output/README.md`: explanation of runtime-produced files.

See [`../../DATABASE_REQUIREMENTS.md`](../../DATABASE_REQUIREMENTS.md) for the
exact default server paths used by the viral reference database modes. Those
large reference files are server-managed and are not included in this package.
