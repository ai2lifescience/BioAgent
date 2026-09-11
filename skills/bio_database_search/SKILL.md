# Database Lookup Skill

## Purpose
Search biological databases and return normalized record summaries.

## When to use
Use when the user asks for UniProt proteins, InterPro domains, KEGG entries,
QuickGO terms or annotations, PDB structures, AlphaFold DB predictions,
accessions, or public biological database lookup.

## Available tools
- bio_database_search

## Workflow
1. Identify the requested database and operation.
2. Extract the accession, identifier, or biological query.
3. Include a taxonomy ID when the database operation needs one.
4. Call `bio_database_search`.
5. Return normalized records and provenance.

## Rules
- Do not claim that a database was searched unless the tool succeeded.
- Return URLs and IDs so evidence can be traced.
- Prefer exact identifiers over natural-language queries.
- Do not create arbitrary API URLs from user input.
- AlphaFold DB lookup retrieves existing predictions; it does not run AlphaFold.
- InterPro API lookup retrieves existing records; novel sequences require InterProScan.

## Operations

- InterPro: `entry_search`, `entry_details`, or `protein_domains`.
- KEGG: `info`, `list`, `find`, `get`, `conv`, or `link`; the query supplies
  the remaining KEGG REST path, such as `eco:b0002` or `genes/shiga toxin`.
- QuickGO: `term_search`, `term_details`, `annotation_search`, or
  `gene_product_search`.
- PDB: `search` or `entry_details`; exact four-character IDs default to details.
- AlphaFold DB: exact UniProt accession lookup, with optional CIF/PDB download.
