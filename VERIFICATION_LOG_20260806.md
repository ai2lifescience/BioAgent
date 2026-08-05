# BioAgent six-pipeline verification log

Date: 2026-08-06

This record documents the final server-side validation of the packaged
pipelines. Tests were run from `/data/wutt/xjp/BioAgent-clean` through
`python -m interfaces.cli` unless stated otherwise. Successful runs returned
BioAgent `Status: ok` and exit code `0`.

## Packaged-content check

The final archive was inspected locally before documentation updates. It
contains exactly the six delivered pipeline directories and their self-contained
`runner.yaml`, `config.yaml`, `run.sh`, `workflow.py`, input fixtures, and
output-placeholders. Content checks confirmed all final fixes:

- BacARG, BacFunc, and BacVF include 22,844 bp Prokka-capable test inputs.
- BactMut FASTA and FASTQ accept a single file as well as a directory.
- BactMut FASTQ uses the dedicated `bactmut` Conda environment and explicit
  SAM-to-BAM conversion.
- Virmut uses the consolidated single-file workflow and a 12,000 bp
  alignable reference fixture.

## Test results

| Pipeline | Command/input | Result and verified outputs |
| --- | --- | --- |
| `bacarg-V2` | `input_data: pipelines/bacarg-V2/data/input/example_contigs.fasta` | Full BioAgent run succeeded. `arg_hits.tsv`, `arg_hits.jsonl`, `qc.json`, and `status.json` existed. |
| `bacfunc-V2` | Direct full genome-mode run of the bundled contig fixture with 8 threads | Completed in 3m 02.685s. Produced `gene_annotations.tsv`, `annotation_terms.tsv`, raw eggNOG annotations/hits/seed orthologs, QC, manifest, and status. `doctor` also returned `READY`. |
| `bacvf-V2` | `input_data: pipelines/bacvf-V2/data/input/example_contigs.fasta` | Full BioAgent run succeeded. `vf_hits.tsv`, `vf_hits.jsonl`, `qc.json`, and `status.json` existed. |
| `bactmut_fasta` | One bundled query FASTA plus bundled local reference | Full BioAgent run succeeded. Report, metrics, SNP matrix, variants, summary, and detailed call tables existed. Optional tree files were absent as expected for the one-sample fixture. |
| `bactmut_fastq` | One bundled FASTQ plus bundled local reference | Full BioAgent run succeeded after creating the dedicated `bactmut` environment with minimap2 2.31, samtools 1.24, and bcftools 1.24. Required report, metrics, matrix, variants, and summary existed. |
| `virmut` | One bundled 12 kb query FASTA and an explicitly supplied bundled local reference | Full BioAgent run succeeded. `matrix.tsv`, `variants.tsv`, and `variants_summary.txt` existed. The final rerun recorded `reference_path` as a staged `input_overrides` value, confirming that the BioAgent reference input is wired correctly. Optional tree outputs were absent as expected for one sample. |

## Environment note

The server's pre-existing `bioagent` environment contained legacy samtools and
bcftools command interfaces incompatible with the FASTQ calling workflow. A
separate `bactmut` Conda environment was created from the Tsinghua mirror with
Python 3.11, PyYAML, minimap2, samtools, and bcftools. The pipeline entrypoint
now selects that environment explicitly.

## Scope and interpretation

These are integration tests of pipeline discovery, generated runtime
configuration, entrypoints, external tool invocation, and declared output
contracts. The synthetic fixtures prove execution paths and output production;
they do not constitute biological validation on a real cohort. Tree output is
optional and is correctly skipped for one-sample fixtures.
