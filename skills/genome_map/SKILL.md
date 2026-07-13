# Genome Map Skill

## Purpose
Create SVG genome feature maps from GenBank, GFF+FASTA, or FASTA files.

## When To Use
Use when the user asks to show genome structure, draw a genome map, visualize
gene layout, display ORFs, or create a circular/linear genome feature map.

## Available Tools
- genome_map

## Workflow
1. Resolve the requested GenBank, GFF, or FASTA path.
2. If the user asks for the latest genome/FASTA, use the newest session FASTA artifact.
3. Call `genome_map`.
4. Return summary statistics and the SVG image path.

## Rules
- This is a 1D genome feature map, not a 3D PDB/mmCIF structure viewer.
- For plain FASTA without annotations, map predicted ORFs.
- For rich biological annotations, prefer GenBank or GFF+FASTA inputs.
