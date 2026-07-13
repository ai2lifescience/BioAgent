# Database Lookup Skill

## Purpose
Search biological databases and return normalized record summaries.

## When to use
Use when the user asks for UniProt entries, PDB structures, protein records,
accessions, or public biological database lookup.

## Available tools
- bio_database_search

## Workflow
1. Identify the requested database.
2. Extract the biological query.
3. Call `bio_database_search`.
4. Return accessions/IDs, names, organisms, and URLs.

## Rules
- Do not claim that a database was searched unless the tool succeeded.
- Return URLs and IDs so evidence can be traced.
