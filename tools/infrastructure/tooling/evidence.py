"""Evidence collection and bounded result projection for agent outputs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

RESULT_COUNT_KEYS = (
    "matched_count",
    "downloaded_count",
    "record_count",
    "source_count",
    "chunk_count",
    "citation_count",
    "hit_count",
    "atom_count",
    "chain_count",
    "residue_count",
    "ligand_count",
    "model_count",
    "genome_length",
    "feature_count",
    "gene_count",
    "cds_count",
    "orf_count",
    "bytes",
    "returncode",
)
RESULT_ID_KEYS = ("collection_name", "rid", "pdb_id", "file_format")
RESULT_PATH_KEYS = (
    "fasta_path",
    "fasta_paths",
    "structure_path",
    "structure_paths",
    "metadata_path",
    "metadata_paths",
    "report_path",
    "image_path",
    "image_paths",
    "genome_map_path",
    "session_input_path",
    "upload_path",
    "runner_config_path",
    "raw_config_path",
    "config_path",
    "metrics_path",
    "bakta_json_path",
    "inference_path",
    "hypotheticals_path",
    "plot_svg_path",
    "plot_png_path",
    "plot_path",
    "output_dir",
)
COMPACT_RESULT_KEYS = (
    "job_id",
    "plan_id",
    "logs",
    "bundle_path",
    "metrics",
    "tables",
    "needs_parameters",
    "required_parameters",
    "parameter_errors",
    "tool",
    "status",
    "summary",
    "needs_input",
    "pipeline_name",
    "presentation",
    "requested_inputs",
    "output_records",
    "config_overrides",
    "staged_config_paths",
    "workspace_paths",
    "sources",
    "matches",
    "groups",
    "missing_values",
    "dtypes",
    "sample",
    "changed_files",
    "test_result",
    "command",
    "operation",
    "source_count",
    *RESULT_COUNT_KEYS,
    *RESULT_ID_KEYS,
    *RESULT_PATH_KEYS,
)


def collect_output_paths(value: Any) -> list[str]:
    """Collect path-like output values for evidence summaries."""

    paths: list[str] = []

    def append(path: str) -> None:
        if path and path not in paths:
            paths.append(path)

    def visit(item: Any, key: str = "") -> None:
        if isinstance(item, dict):
            for subkey, subitem in item.items():
                visit(subitem, str(subkey))
            return
        if isinstance(item, list):
            for subitem in item:
                visit(subitem, key)
            return
        if isinstance(item, str) and (
            key.endswith("_path") or key.endswith("_paths") or key in {"output_dir", "changed_files"}
        ):
            append(item)

    visit(value)
    return paths

QUERY_KEYS = (
    "term",
    "terms",
    "genes",
    "accessions",
    "query",
    "question",
    "species",
    "species_name",
    "organism",
)
DATABASE_KEYS = ("db", "database")
EVIDENCE_LIST_KEYS = ("sources", "citations", "records", "results", "retrieved_chunks", "hits")


def _append_unique(values: list[Any], value: Any) -> None:
    if value not in values:
        values.append(value)


def _collect_file_paths(value: Any, files: list[str]) -> None:
    for path in collect_output_paths(value):
        _append_unique(files, path)


def _collect_urls(value: Any, urls: list[str]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "url" and isinstance(item, str) and item:
                _append_unique(urls, item)
            else:
                _collect_urls(item, urls)
    elif isinstance(value, list):
        for item in value:
            _collect_urls(item, urls)


def _collect_query_terms(value: dict[str, Any], evidence: dict[str, Any]) -> None:
    for key in QUERY_KEYS:
        item = value.get(key)
        if isinstance(item, list):
            for subitem in item:
                if subitem:
                    _append_unique(evidence["query_terms"], str(subitem))
        elif item:
            _append_unique(evidence["query_terms"], str(item))


def _collect_databases(value: dict[str, Any], evidence: dict[str, Any]) -> None:
    for key in DATABASE_KEYS:
        item = value.get(key)
        if item:
            _append_unique(evidence["databases"], str(item))
    collection_name = value.get("collection_name")
    if collection_name:
        _append_unique(evidence["databases"], f"chroma:{collection_name}")


def _candidate_item(item: dict[str, Any]) -> dict[str, Any]:
    metadata = item.get("metadata")
    if isinstance(metadata, dict):
        return {**metadata, **item}
    return item


def _collect_record_id(item: dict[str, Any], evidence: dict[str, Any]) -> None:
    candidate = _candidate_item(item)
    if candidate.get("pmid"):
        _append_unique(evidence["record_ids"], f"PMID:{candidate['pmid']}")
        return
    if candidate.get("accession"):
        _append_unique(evidence["record_ids"], str(candidate["accession"]))
        return
    if candidate.get("identifier"):
        _append_unique(evidence["record_ids"], str(candidate["identifier"]))
        return
    if candidate.get("rid"):
        _append_unique(evidence["record_ids"], f"BLAST:{candidate['rid']}")
        return
    record_id = candidate.get("id") or candidate.get("doc_id")
    if record_id and not str(record_id).startswith("S"):
        _append_unique(evidence["record_ids"], str(record_id))


def _collect_citation(item: dict[str, Any], evidence: dict[str, Any]) -> None:
    candidate = _candidate_item(item)
    if not any(candidate.get(key) for key in ("title", "name", "source", "url", "pmid", "year")):
        return
    citation = {
        "id": candidate.get("id"),
        "title": candidate.get("title") or candidate.get("name"),
        "source": candidate.get("source") or candidate.get("database"),
        "pmid": candidate.get("pmid"),
        "url": candidate.get("url"),
        "year": candidate.get("year"),
    }
    _append_unique(evidence["citations"], citation)


def _collect_evidence_items(result: dict[str, Any], evidence: dict[str, Any]) -> None:
    for key in EVIDENCE_LIST_KEYS:
        items = result.get(key)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            _collect_record_id(item, evidence)
            _collect_citation(item, evidence)
            query_translation = item.get("query_translation")
            if query_translation:
                _append_unique(evidence["query_terms"], str(query_translation))


def _output_record(tool: str, arguments: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    output = {"tool": tool}
    for key in COMPACT_RESULT_KEYS:
        if key in result:
            output[key] = result[key]
    if not output.keys() - {"tool"} and arguments:
        output["arguments"] = arguments
    return output


def _tool_output_record(tool_call: dict[str, Any]) -> dict[str, Any]:
    output = {
        "tool": tool_call.get("tool"),
        "status": tool_call.get("status"),
        "category": tool_call.get("category"),
        "risk_level": tool_call.get("risk_level"),
    }
    if tool_call.get("error"):
        output["error"] = tool_call.get("error")

    result = tool_call.get("result")
    if isinstance(result, dict):
        for key in COMPACT_RESULT_KEYS:
            if key in result:
                output[key] = result[key]
    return {key: value for key, value in output.items() if value not in (None, "", [])}


def _collect_tool_call(tool_call: dict[str, Any], evidence: dict[str, Any]) -> None:
    tool = tool_call.get("tool")
    if tool:
        _append_unique(evidence["tools"], str(tool))

    arguments = tool_call.get("arguments") or {}
    result = tool_call.get("result") or {}
    if isinstance(arguments, dict):
        _collect_file_paths(arguments, evidence["files"])
        _collect_query_terms(arguments, evidence)
        _collect_databases(arguments, evidence)

    if isinstance(result, dict):
        _collect_file_paths(result, evidence["files"])
        _collect_urls(result, evidence["urls"])
        _collect_query_terms(result, evidence)
        _collect_databases(result, evidence)
        _collect_evidence_items(result, evidence)

    if tool_call.get("status") == "error":
        _append_unique(
            evidence["tool_errors"],
            {
                "tool": tool,
                "error": tool_call.get("error"),
                "error_type": tool_call.get("error_type"),
            },
        )
    evidence["tool_outputs"].append(_tool_output_record(tool_call))


def _collect_record_tool_calls(record: dict[str, Any], evidence: dict[str, Any]) -> None:
    tool_calls = record.get("tool_calls") or []
    if not isinstance(tool_calls, list):
        return
    for tool_call in tool_calls:
        if isinstance(tool_call, dict):
            _collect_tool_call(tool_call, evidence)


@dataclass
class EvidenceCollector:
    """Collect record IDs, URLs, query terms, citations, and files from results."""

    retrieval_date: str = field(default_factory=lambda: date.today().isoformat())

    def collect(self, tool_results: list[dict[str, Any]]) -> dict[str, Any]:
        evidence: dict[str, Any] = {
            "retrieval_date": self.retrieval_date,
            "tools": [],
            "databases": [],
            "query_terms": [],
            "record_ids": [],
            "citations": [],
            "urls": [],
            "files": [],
            "outputs": [],
            "tool_outputs": [],
            "tool_errors": [],
        }

        for record in tool_results:
            tool = str(record.get("tool") or "")
            arguments = record.get("arguments") or {}
            result = record.get("result") or {}
            if tool:
                _append_unique(evidence["tools"], tool)
            if isinstance(arguments, dict):
                _collect_file_paths(arguments, evidence["files"])
                _collect_query_terms(arguments, evidence)
                _collect_databases(arguments, evidence)
            if not isinstance(result, dict):
                evidence["outputs"].append({"tool": tool, "result": result})
                _collect_record_tool_calls(record, evidence)
                continue

            _collect_file_paths(result, evidence["files"])
            _collect_urls(result, evidence["urls"])
            _collect_query_terms(result, evidence)
            _collect_databases(result, evidence)
            _collect_evidence_items(result, evidence)
            evidence["outputs"].append(_output_record(tool, arguments, result))
            _collect_record_tool_calls(record, evidence)

        return evidence
