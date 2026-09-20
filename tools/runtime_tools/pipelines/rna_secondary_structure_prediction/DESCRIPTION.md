# RNA Secondary Structure Pipeline Description

## Function

The pipeline accepts nucleotide FASTA, converts DNA letter `T` to RNA letter
`U`, validates IUPAC nucleotide symbols, and runs ViennaRNA RNAfold once per
record with plot generation disabled.

```text
nucleotide FASTA
  -> sequence and length validation
  -> RNAfold minimum-free-energy prediction
  -> result parsing and length checks
  -> table, dot-bracket, metrics, report, and log
```

This predicts an equilibrium minimum-free-energy secondary structure. It does
not model pseudoknots, RNA tertiary structure, cellular conditions, or
experimental probing constraints.

## Input and parameters

- Required `rna` slot: `.fa`, `.fasta`, or `.fna` with at most 1,000 records.
- `temperature_c`: folding temperature, default 37 °C.
- `max_sequence_length`: per-record safety limit, default 10,000 nt.

## Outputs

- `structures.tsv`: sequence ID, length, MFE, and dot-bracket structure.
- `structures.dbn`: FASTA-like sequences and dot-bracket structures.
- `metrics.json`: structured run metadata and prediction metrics.
- `report.md`: human-readable prediction summary.
- `rnafold.log`: command, version, return code, stdout, and stderr per record.

User values are sent as subprocess arguments or standard input; no shell is
invoked and arbitrary RNAfold arguments are not accepted.

## Mock fixtures

`data/input/example_rna.fasta` and every file in `data/output/` are synthetic
contract fixtures. They allow developers to inspect expected formats without
requiring ViennaRNA during repository checkout.
