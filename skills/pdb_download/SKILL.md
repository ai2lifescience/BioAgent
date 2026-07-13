# PDB Download Skill

## Purpose
Download structure files from RCSB PDB into the active BioAgent session artifacts.

## When to use
Use when the user asks to download, fetch, save, or retrieve a specific PDB structure file by PDB ID.

## Available tools
- pdb_download

## Workflow
1. Validate the PDB ID and requested file format.
2. Use `pdb_download` to retrieve the structure file from RCSB.
3. Store the downloaded file under the session artifact structure directory unless the user provides an output directory.
4. Return the local structure path and source URL.

## Rules
- Default to `cif` format unless the user asks for `pdb` or `bcif`.
- Do not use this skill for general PDB search; use `database_lookup` for search.
