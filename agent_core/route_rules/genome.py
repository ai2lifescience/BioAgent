"""Genome map route rules."""

from __future__ import annotations

import re

from agent_core.router import IntentRoute

from .common import extract_labeled_value, extract_quoted_or_labeled_path


PATH_PATTERN = re.compile(
    r"([A-Za-z0-9_./-]+\.(?:genbank|fasta|gff3|gbk|fna|faa|gff|fa|gb))",
    re.IGNORECASE,
)


def route_genome_map(user_request: str) -> IntentRoute | None:
    if not re.search(
        r"\b(genome|genomic|gene|feature|orf|annotation)\b",
        user_request,
        re.IGNORECASE,
    ):
        return None
    has_map_action = re.search(
        r"\b(map|layout|visuali[sz]e|draw|plot|diagram|circular|linear)\b",
        user_request,
        re.IGNORECASE,
    )
    has_file_context = PATH_PATTERN.search(user_request) or re.search(
        r"\b(latest|last|previous|downloaded|that fasta|the fasta|this fasta|this genome|genbank|gff)\b",
        user_request,
        re.IGNORECASE,
    )
    if not has_map_action and not (
        re.search(r"\bshow\b", user_request, re.IGNORECASE) and has_file_context
    ):
        return None

    args: dict[str, object] = {}
    for path in _extract_genome_paths(user_request):
        lower = path.lower()
        if lower.endswith((".gb", ".gbk", ".genbank")):
            args["genbank_path"] = path
        elif lower.endswith((".gff", ".gff3")):
            args["gff_path"] = path
        elif lower.endswith((".fasta", ".fa", ".fna", ".faa")):
            args["fasta_path"] = path

    if "linear" in user_request.lower():
        args["layout"] = "linear"
    elif "circular" in user_request.lower():
        args["layout"] = "circular"

    label = extract_labeled_value(user_request, "label")
    if label:
        args["label"] = label

    if not any(key in args for key in ("fasta_path", "genbank_path")):
        if re.search(r"\b(latest|last|previous|downloaded|that fasta|the fasta|this genome)\b", user_request, re.IGNORECASE):
            args["artifact_ref"] = "latest_fasta"
        else:
            args["artifact_ref"] = "latest_fasta"

    return IntentRoute(
        mode="direct_skill",
        skill_name="genome_map",
        arguments=args,
        reason="Matched a genome feature map request.",
    )


def _extract_genome_paths(user_request: str) -> list[str]:
    paths = []
    quoted_or_single = extract_quoted_or_labeled_path(user_request)
    if quoted_or_single and PATH_PATTERN.search(quoted_or_single):
        paths.append(quoted_or_single)
    for match in PATH_PATTERN.finditer(user_request):
        path = match.group(1)
        if path not in paths:
            paths.append(path)
    return paths
