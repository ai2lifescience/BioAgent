# Species Report Skill

## Purpose
Build a trusted-source species or organism knowledge report.

## When to use
Use when the user asks for species knowledge, organism information, PubMed/RAG
research, source-backed synthesis, or a Markdown report.

## Available tools
- `pubmed_collect`
- `trusted_web_collect`
- `rag_chunk`
- `rag_store`
- `rag_retrieve`
- `rag_citations`
- `species_model_opinions`
- `species_report_synthesis`
- `markdown_report_writer`

## Workflow
1. Resolve the species or organism name.
2. Collect PubMed sources with `pubmed_collect`.
3. Collect trusted web sources with `trusted_web_collect`.
4. Chunk source text with `rag_chunk`.
5. Store chunks with `rag_store`, retrieve evidence with `rag_retrieve`, and build citations with `rag_citations`.
6. Ask configured LLMs for direct opinions with `species_model_opinions`.
7. Synthesize and save a Markdown report with `species_report_synthesis` and `markdown_report_writer`.

## Rules
- Prefer trusted/authoritative sources.
- Preserve source URLs and PMIDs.
- Say when evidence is incomplete.
