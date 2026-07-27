"""Pipeline execution route rules."""

from __future__ import annotations

import re
from typing import Any

from agent_core.router import IntentRoute

from .common import extract_labeled_value, extract_quoted_or_labeled_path


DEFAULT_GENERIC_SHELL = "generic_shell"
DEFAULT_GENERIC_SNAKEMAKE = "generic_snakemake"
DEFAULT_GENERIC_WDL = "generic_wdl"
BACTERIAL_ANNOTATION_PIPELINE = "bacterial_annotation"
RNA_SECONDARY_STRUCTURE_PIPELINE = "rna_secondary_structure"


def _is_bacterial_annotation_request(user_request: str) -> bool:
    return bool(
        re.search(
            r"\b(?:annotate_bacterial_genome|"
            r"annotate\s+(?:an?\s+|this\s+|the\s+)?bacterial\s+genome|"
            r"bacterial\s+genome\s+annotation)\b",
            user_request,
            flags=re.IGNORECASE,
        )
    )


def _is_rna_secondary_structure_request(user_request: str) -> bool:
    return bool(
        re.search(
            r"\b(?:predict_rna_secondary_structure|"
            r"predict(?:ing|ion)?\s+(?:an?\s+|the\s+)?rna\s+secondary\s+structure|"
            r"predict(?:ing|ion)?\s+(?:an?\s+|the\s+)?secondary\s+structure\s+(?:of|for)\s+rna|"
            r"rna\s+secondary\s+structure\s+prediction|fold\s+(?:an?\s+|the\s+)?rna)\b",
            user_request,
            flags=re.IGNORECASE,
        )
    )


def _extract_pipeline_name(user_request: str) -> str | None:
    quoted = re.search(
        r"\bpipeline[_ -]?name\b\s*(?::|=)?\s*(['\"])(.+?)\1",
        user_request,
        flags=re.IGNORECASE,
    )
    if quoted:
        return _clean_pipeline_name(quoted.group(2))

    bare = re.search(
        r"\bpipeline[_ -]?name\b\s*(?::|=)?\s*([A-Za-z0-9_.-]+)",
        user_request,
        flags=re.IGNORECASE,
    )
    if bare:
        return _clean_pipeline_name(bare.group(1))

    direct = re.search(
        r"\b(?:run|execute|start)\s+(?:the\s+)?pipeline\s+([A-Za-z0-9_.-]+)\b",
        user_request,
        flags=re.IGNORECASE,
    )
    return _clean_pipeline_name(direct.group(1)) if direct else None


def _clean_pipeline_name(value: str | None) -> str | None:
    if not value:
        return None
    return value.strip(" .,:;") or None


def route_pipeline(user_request: str) -> IntentRoute | None:
    bacterial_annotation = _is_bacterial_annotation_request(user_request)
    rna_secondary_structure = _is_rna_secondary_structure_request(user_request)
    if not bacterial_annotation and not rna_secondary_structure and not re.search(
        r"\b(example pipeline|test pipeline|shell pipeline|snakemake pipeline|wdl pipeline|pipeline skill|run pipeline|execute pipeline|start pipeline)\b",
        user_request,
        flags=re.IGNORECASE,
    ):
        return None

    is_snakemake = bool(re.search(r"\bsnakemake\b", user_request, re.IGNORECASE))
    is_wdl = bool(re.search(r"\bwdl\b", user_request, re.IGNORECASE))
    args: dict[str, Any] = {}

    label = extract_labeled_value(user_request, "label")
    if label:
        args["label"] = label
    output_dir = (
        extract_labeled_value(user_request, "output_dir")
        or extract_labeled_value(user_request, "output")
    )
    if output_dir:
        args["output_dir"] = output_dir
    pipeline_name = _extract_pipeline_name(user_request)
    if bacterial_annotation and not pipeline_name:
        args["pipeline_name"] = BACTERIAL_ANNOTATION_PIPELINE
    elif rna_secondary_structure and not pipeline_name:
        args["pipeline_name"] = RNA_SECONDARY_STRUCTURE_PIPELINE
    elif pipeline_name:
        args["pipeline_name"] = pipeline_name
    elif is_wdl:
        args["pipeline_name"] = DEFAULT_GENERIC_WDL
    elif is_snakemake:
        args["pipeline_name"] = DEFAULT_GENERIC_SNAKEMAKE
    else:
        args["pipeline_name"] = DEFAULT_GENERIC_SHELL

    input_overrides = _extract_runner_input_overrides(user_request, args["pipeline_name"])
    if input_overrides:
        args["input_overrides"] = input_overrides

    path = None
    if not input_overrides:
        path = (
            extract_labeled_value(user_request, "input_path")
            or extract_labeled_value(user_request, "input")
            or extract_quoted_or_labeled_path(user_request)
        )
    if path:
        args["input_path"] = path

    config_overrides = _extract_runner_config_overrides(user_request, args["pipeline_name"])
    if bacterial_annotation and "annotator" not in config_overrides:
        annotator_match = re.search(
            r"\b(?:with|using|via)\s+(prokka|bakta)\b",
            user_request,
            flags=re.IGNORECASE,
        )
        if annotator_match:
            config_overrides["annotator"] = annotator_match.group(1).lower()
    if config_overrides:
        args["config_overrides"] = config_overrides

    if re.search(r"\bdry[- ]?run\b", user_request, re.IGNORECASE):
        args["dry_run"] = True

    cores_match = re.search(
        r"\b(?:cores?|threads?)\s*(?::|=)?\s*(\d+)\b|\b(\d+)\s*(?:cores?|threads?)\b",
        user_request,
        re.IGNORECASE,
    )
    if cores_match:
        cores = max(1, int(cores_match.group(1) or cores_match.group(2)))
        args["cores"] = cores
        if bacterial_annotation:
            config_overrides = dict(args.get("config_overrides") or {})
            config_overrides.setdefault("cpus", cores)
            args["config_overrides"] = config_overrides

    return IntentRoute(
        mode="direct_skill",
        skill_name="pipeline_runner",
        arguments=args,
        reason=(
            "Matched a bacterial genome annotation request."
            if bacterial_annotation
            else (
                "Matched an RNA secondary structure prediction request."
                if rna_secondary_structure
                else "Matched an explicit approved pipeline execution request."
            )
        ),
    )


def _extract_runner_input_overrides(user_request: str, pipeline_name: str) -> dict[str, str]:
    input_specs = _load_input_specs(pipeline_name)
    overrides: dict[str, str] = {}
    for slot, spec in input_specs.items():
        candidates = [
            slot,
            str(spec.get("config_key") or ""),
            str(spec.get("label") or ""),
        ]
        for candidate in candidates:
            if not candidate:
                continue
            value = extract_labeled_value(user_request, candidate)
            if value:
                overrides[slot] = value
                break
    return overrides


def _load_input_specs(pipeline_name: str) -> dict[str, dict[str, Any]]:
    try:
        from tools.pipeline_runner.config import load_runner_config
        from tools.pipeline_runner.inputs import pipeline_input_specs
        from tools.pipeline_runner.paths import resolve_pipeline_dir

        pipeline_dir = resolve_pipeline_dir(pipeline_name)
        runner_config, _path = load_runner_config(pipeline_dir)
    except Exception:
        return {}
    return pipeline_input_specs(runner_config)


def _extract_runner_config_overrides(user_request: str, pipeline_name: str) -> dict[str, Any]:
    allowed_keys = _load_param_override_keys(pipeline_name)
    if not allowed_keys:
        return {}

    overrides: dict[str, Any] = {}
    for key in allowed_keys:
        value = _extract_override_value(user_request, key)
        if value is not None:
            overrides[key] = value
    return overrides


def _load_param_override_keys(pipeline_name: str) -> list[str]:
    try:
        from tools.pipeline_runner.config import load_pipeline_config, load_runner_config
        from tools.pipeline_runner.paths import resolve_pipeline_dir

        pipeline_dir = resolve_pipeline_dir(pipeline_name)
        runner_config, _path = load_runner_config(pipeline_dir)
        raw_config, _raw_path = load_pipeline_config(pipeline_dir, runner_config)
    except Exception:
        return []
    param_overrides = runner_config.get("param_overrides")
    if isinstance(param_overrides, dict) and param_overrides:
        return [str(key) for key in param_overrides]
    params = raw_config.get("params")
    if isinstance(params, dict):
        return [str(key) for key in params]
    return []


def _extract_override_value(user_request: str, key: str) -> Any | None:
    quoted = re.search(
        rf"\b{re.escape(key)}\b\s*(?::|=)?\s*(['\"])(.+?)\1",
        user_request,
        flags=re.IGNORECASE,
    )
    if quoted:
        return _split_override_value(quoted.group(2))

    bare = re.search(
        rf"\b{re.escape(key)}\b\s*(?::|=)?\s*([A-Za-z0-9_.-]+(?:\s*,\s*[A-Za-z0-9_.-]+)*)",
        user_request,
        flags=re.IGNORECASE,
    )
    if not bare:
        return None
    return _split_override_value(bare.group(1))


def _split_override_value(value: str) -> Any:
    parts = [part.strip(" .,:;") for part in value.split(",") if part.strip(" .,:;")]
    if len(parts) > 1:
        return parts
    return parts[0] if parts else None
