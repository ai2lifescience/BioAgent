# BLAST Search Skill

## Purpose
Submit sequence similarity searches through the NCBI BLAST URL API, or poll an existing BLAST RID.

## When to use
Use only when the user explicitly asks for BLAST or sequence similarity search.

## Available tools
- blast_search

## Workflow
1. Validate the sequence and requested BLAST program/database.
2. Call `blast_search`.
3. If `wait=false`, return RID, status, database, and polling guidance.
4. If `wait=true` or a RID is provided, return parsed compact hit summaries when NCBI results are ready.

## Rules
- Do not run BLAST unless the user explicitly requests it.
- Default to submission without waiting unless the user asks to wait, poll, or return hits/results.
