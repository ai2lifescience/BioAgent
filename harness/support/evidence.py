"""Evidence collection for biological agent outputs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from .artifacts import COMPACT_RESULT_KEYS, collect_output_paths


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


def _output_record(skill: str, arguments: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    output = {"skill": skill}
    for key in COMPACT_RESULT_KEYS:
        if key in result:
            output[key] = result[key]
    if not output.keys() - {"skill"} and arguments:
        output["arguments"] = arguments
    return output


def _tool_output_record(tool_call: dict[str, Any]) -> dict[str, Any]:
    output = {
        "skill": tool_call.get("skill"),
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
                "skill": tool_call.get("skill"),
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

    def collect(self, skill_results: list[dict[str, Any]]) -> dict[str, Any]:
        evidence: dict[str, Any] = {
            "retrieval_date": self.retrieval_date,
            "skills": [],
            "databases": [],
            "query_terms": [],
            "record_ids": [],
            "citations": [],
            "urls": [],
            "files": [],
            "outputs": [],
            "tools": [],
            "tool_outputs": [],
            "tool_errors": [],
        }

        for record in skill_results:
            skill = str(record.get("skill") or "")
            arguments = record.get("arguments") or {}
            result = record.get("result") or {}
            if skill:
                _append_unique(evidence["skills"], skill)
            if isinstance(arguments, dict):
                _collect_file_paths(arguments, evidence["files"])
                _collect_query_terms(arguments, evidence)
                _collect_databases(arguments, evidence)
            if not isinstance(result, dict):
                evidence["outputs"].append({"skill": skill, "result": result})
                _collect_record_tool_calls(record, evidence)
                continue

            _collect_file_paths(result, evidence["files"])
            _collect_urls(result, evidence["urls"])
            _collect_query_terms(result, evidence)
            _collect_databases(result, evidence)
            _collect_evidence_items(result, evidence)
            evidence["outputs"].append(_output_record(skill, arguments, result))
            _collect_record_tool_calls(record, evidence)

        return evidence
