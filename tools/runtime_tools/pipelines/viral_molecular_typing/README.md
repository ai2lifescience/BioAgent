# Viral molecular typing

> Pipeline dependencies and databases belong to the pipeline container. The BioAgent environment does not install workflow tools.

Process viral reads, generate a consensus and alignment, and run configured Nextclade molecular typing.

## Inputs

- `read1` (required, `run_molecular_typing.file1Path`): Read 1 FASTQ input.. Accepted: .fastq, .fq, .fastq.gz, .fq.gz.
- `read2` (optional, `run_molecular_typing.file2Path`): Optional read 2 FASTQ input for paired-end processing.. Accepted: .fastq, .fq, .fastq.gz, .fq.gz.

## Outputs

- `result_csv`: `data/output/result.csv` — Typing result CSV produced by this workflow..
- `nextclade_tsv`: `data/output/nextclade.tsv` — Nextclade TSV produced by this workflow..
- `nextclade_json`: `data/output/nextclade.json` — Nextclade JSON produced by this workflow..
- `consensus_fa`: `data/output/consensus.fa` — HA consensus FASTA produced by this workflow..
- `final_bam`: `data/output/final.bam` — Final BAM produced by this workflow..

## Run

Ask the agent to run `viral_molecular_typing` with the inputs above. For the bundled example, say:

```text
Run viral_molecular_typing with its bundled example data and collect the results.
```

The `runner.yaml` file is the agent-facing input/output contract. The runtime stages inputs and writes declared outputs inside the per-run workspace.
