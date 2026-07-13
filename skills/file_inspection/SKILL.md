# File Inspection Skill

## Purpose
Inspect local biological output files.

## When to use
Use when the user asks to inspect, read, summarize, verify, or preview a FASTA,
CSV, TSV, Markdown, or text file.

## Available tools
- file_inspect

## Workflow
1. Identify the local file path.
2. Call `file_inspect`.
3. Return file type, size, line count, record/row count, and relevant preview.

## Rules
- Do not modify files.
- Report file-not-found errors directly.
