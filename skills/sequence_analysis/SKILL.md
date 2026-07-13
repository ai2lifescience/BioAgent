# Sequence Analysis Skill

## Purpose
Analyze DNA, RNA, protein, or FASTA input with deterministic local computation.

## When to use
Use for GC content, sequence length, base/residue counts, FASTA summaries, or
ORF detection.

## Available tools
- sequence_analyze

## Workflow
1. Determine whether the input is a raw sequence or FASTA file.
2. Call `sequence_analyze`.
3. Summarize sequence type, length, GC content, counts, and ORFs.

## Rules
- Do not use the LLM to calculate sequence metrics.
- Report uncertainty when the sequence type is mixed or unknown.
