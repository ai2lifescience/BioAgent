# NCBI Retrieval Skill

## Purpose
Search NCBI Entrez and retrieve public biological records as FASTA plus metadata
CSV files.

## When to use
Use when the user asks to download, fetch, search, or retrieve NCBI records,
FASTA sequences, nucleotide/protein data, genes, accessions, or metadata.

## Available tools
- ncbi_fetch

## Workflow
1. Resolve the organism, accession, gene list, database, and date filters.
2. Call `ncbi_fetch`.
3. Verify that FASTA and metadata paths are present when records were downloaded.
4. Return query details, counts, file paths, and limitations.

## Rules
- Use exact Entrez terms when the user supplies them.
- Keep multiple genes/accessions in one skill call when possible.
- Do not invent records if NCBI returns zero matches.
