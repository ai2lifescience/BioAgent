# PhiX174 NCBI Retrieval Usage

This folder provides the `ncbi_retrieval` skill workflow. The workflow calls the
`ncbi_fetch` tool to download NCBI Entrez records as FASTA files plus metadata
CSV files.

## Default PhiX174 Download

Calling the underlying `ncbi_fetch` tool with no arguments downloads PhiX174
gene A and gene G nucleotide records.

```python
from bio_data.ncbi import fetch_ncbi

result = fetch_ncbi()

print(result["output_dir"])
print(result["fasta_paths"])
print(result["metadata_paths"])
```

Default output folder:

```text
runtime/downloads/ncbi_phix174
```

## Explicit Python Usage

```python
from bio_data.ncbi import fetch_ncbi

result = fetch_ncbi(
    term='"Escherichia phage phiX174"[Organism]',
    genes=["A", "G"],
    max_records=10,
)
```

To set the output folder yourself:

```python
result = fetch_ncbi(
    term='"Escherichia phage phiX174"[Organism]',
    genes=["A", "G"],
    output_dir="runtime/downloads/ncbi_phix174",
)
```

## Agent Usage

From the repository root:

```bash
python -m interfaces.cli "download 10 records phiX174 genes A G"
```

You can also call the agent from Python:

```python
from agent_core import BioAgentOrchestrator

result = BioAgentOrchestrator().run("download 10 records phiX174 genes A G")
print(result["answer"])
```

The agent recognizes simple NCBI requests containing words like `download`,
`fetch`, `retrieve`, or `search`. PhiX174 can be written as `phiX174`,
`phix174`, or `phi X 174`.

## Outputs

Successful downloads produce:

- `*.fasta`: sequence records
- `*.metadata.csv`: metadata table

The result dictionary also includes `output_dir`, `fasta_paths`, and
`metadata_paths`.
