# Protein Structure Analysis Skill

## Purpose
Analyze local PDB or mmCIF protein structure files with Biopython and return compact structure statistics.
If the user provides only a PDB ID, download the structure as mmCIF first and then analyze it.

## When to use
Use when the user asks to analyze, inspect, summarize, or describe a downloaded PDB/mmCIF protein structure.

## Available tools
- protein_structure_analyze

## Workflow
1. Resolve the requested structure file path.
2. If the user gives a PDB ID, call `pdb_download` with `file_format="cif"` unless another text format is requested.
3. If the user asks for the latest structure, use the newest session structure artifact.
4. Call `protein_structure_analyze`.
5. Return atom count, chains, residues, ligands, water count, model count, method, and resolution when available.

## Rules
- This is a compact structural summary, not a molecular modeling engine.
- Use `pdb_download` inside this skill when the user gives a PDB ID and asks to analyze it.
- Use `file_inspection` for generic file previews.
