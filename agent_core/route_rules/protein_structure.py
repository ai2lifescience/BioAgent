"""Protein structure analysis route rules."""

from __future__ import annotations

import re

from agent_core.router import IntentRoute

from .common import extract_quoted_or_labeled_path


def route_protein_structure_analysis(user_request: str) -> IntentRoute | None:
    if not re.search(
        r"\b(analy[sz]e|inspect|summari[sz]e|describe|read|show|list|count)\b",
        user_request,
        re.IGNORECASE,
    ):
        return None
    if not re.search(
        r"\b(structure|pdb|mmcif|cif|chains?|ligands?|residues?|atoms?)\b|\.(?:cif|mmcif|pdb)\b",
        user_request,
        re.IGNORECASE,
    ):
        return None

    path = extract_quoted_or_labeled_path(user_request)
    if path and path.lower().endswith((".cif", ".mmcif", ".pdb")):
        return IntentRoute(
            mode="direct_skill",
            skill_name="protein_structure_analysis",
            arguments={"structure_path": path},
            reason="Matched a protein structure analysis request for a local PDB/mmCIF file.",
        )

    pdb_id = _extract_pdb_id(user_request)
    if pdb_id:
        return IntentRoute(
            mode="direct_skill",
            skill_name="protein_structure_analysis",
            arguments={"pdb_id": pdb_id},
            reason="Matched a protein structure analysis request for a PDB ID.",
        )

    if re.search(
        r"\b(latest|last|previous|downloaded|just downloaded|that structure|the structure)\b",
        user_request,
        re.IGNORECASE,
    ):
        return IntentRoute(
            mode="direct_skill",
            skill_name="protein_structure_analysis",
            arguments={"artifact_ref": "latest_structure"},
            reason="Matched a protein structure analysis request for the latest session structure artifact.",
        )

    return None


def _extract_pdb_id(text: str) -> str | None:
    labeled = re.search(
        r"\b(?:pdb(?:\s+id)?|structure)\b\s*(?:of|for|:|=)?\s*([0-9][A-Za-z0-9]{3})\b",
        text,
        re.IGNORECASE,
    )
    if labeled:
        return labeled.group(1).upper()
    standalone = re.search(r"\b([0-9][A-Za-z0-9]{3})\b", text)
    return standalone.group(1).upper() if standalone else None
