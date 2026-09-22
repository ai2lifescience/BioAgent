"""Self-contained SDK capability: evidence_retrieve."""
from __future__ import annotations

import json
import re
from typing import Annotated
import sqlite3
import math
from tools.infrastructure.tool_support.embeddings import embed_texts

from agents import RunContextWrapper
from pydantic import Field

from harness.context import AgentRunContext
from tools.infrastructure.tool_support.artifacts import input_path, load_evidence, output, write_json
from tools.infrastructure.tool_support.decorators import bio_function_tool
from tools.infrastructure.tool_support.evidence_models import EvidenceRecord
from tools.infrastructure.tool_support.operations import invoke
from tools.infrastructure.tool_support.results import FunctionContract as Contract, FunctionResult as Result


class EvidenceResult(Contract):
    question: str
    sources: list[EvidenceRecord]
    returned: int
    total: int
    truncated: bool
    evidence_path: str


def _operation(*, question: str, evidence_paths: list[str] | None, top_k: int, context, index_path: str | None = None):
    if bool(evidence_paths) == bool(index_path):
        raise ValueError("Provide either evidence_paths or index_path.")
    if index_path:
        return _retrieve_index(question=question, index_path=index_path, top_k=top_k, context=context)
    records = load_evidence(context, evidence_paths)
    terms = set(re.findall(r"\w+", question.lower()))
    def score(item):
        tokens = re.findall(r"\w+", (item.title + " " + item.text).lower())
        return sum(token in terms for token in tokens) / max(1, len(tokens)) ** 0.5
    ranked = sorted((item for item in records if score(item) > 0), key=lambda item: (-score(item), item.id))
    selected = []
    for item in ranked[:top_k]:
        text = item.text
        positions = [text.lower().find(term) for term in terms if term in text.lower()]
        start = max(0, min(positions, default=0) - 200)
        selected.append(item.model_copy(update={"text": text[start:start + 2000]}))
    # Persist the selected excerpts so synthesis can consume them without the
    # model copying or inventing evidence. No embedding/indexing side effects.
    file = write_json(context, "evidence.json", {"schema_version": 1, "sources": [r.model_dump(mode="json") for r in selected]})
    return output({"question": question, "sources": [r.model_dump(mode="json") for r in selected],
                   "returned": len(selected), "total": len(ranked), "truncated": len(ranked) > len(selected) or any(len(r.text) > 2000 for r in ranked[:top_k]),
                   "evidence_path": file["path"]}, file)


def _retrieve_index(*, question: str, index_path: str, top_k: int, context):
    path = input_path(context, index_path, (".sqlite",), max_bytes=128 * 1024 * 1024)
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as database:
        metadata = database.execute("SELECT schema_version, embedding_model FROM metadata").fetchall()
        if len(metadata) != 1 or metadata[0][0] != 1:
            raise ValueError("Unsupported evidence index version.")
        rows = database.execute("SELECT source, excerpt, vector FROM chunks LIMIT 4001").fetchall()
    if not rows or len(rows) > 4000:
        raise ValueError("Evidence index has an invalid chunk count.")
    query = embed_texts([question], model=metadata[0][1])[0]
    def cosine(vector):
        if len(vector) != len(query) or not all(math.isfinite(x) for x in vector + query):
            raise ValueError("Evidence index vector dimensions or values are invalid.")
        denominator = math.sqrt(sum(x*x for x in vector) * sum(x*x for x in query))
        return sum(a*b for a,b in zip(vector,query)) / denominator if denominator else 0.0
    ranked = sorted([(cosine(json.loads(vector)), EvidenceRecord.model_validate_json(source), excerpt) for source, excerpt, vector in rows], key=lambda item: (-item[0], item[1].id))
    unique = {}
    for score, item, excerpt in ranked:
        if item.id not in unique:
            unique[item.id] = item.model_copy(update={"text": excerpt[:2000]})
    selected = list(unique.values())[:top_k]
    file = write_json(context, "evidence.json", {"schema_version": 1, "sources": [item.model_dump(mode="json") for item in selected]})
    return output({"question": question, "sources": [item.model_dump(mode="json") for item in selected], "returned": len(selected), "total": len(unique), "truncated": len(unique) > len(selected) or any(len(text) > 2000 for _, _, text in ranked), "evidence_path": file["path"]}, file)


@bio_function_tool(timeout=120)
async def evidence_retrieve(
    ctx: RunContextWrapper[AgentRunContext],
    question: Annotated[str, Field(min_length=1, max_length=2000)],
    evidence_paths: Annotated[list[str] | None, Field(min_length=1, max_length=10)] = None,
    top_k: Annotated[int, Field(ge=1, le=20)] = 5,
    index_path: str | None = None,
) -> Result[EvidenceResult]:
    """Select evidence excerpts by keyword from evidence_paths or by vector similarity from a persistent index_path. Vector retrieval uses the configured embedding API."""
    return await invoke(ctx.context, "evidence_retrieve", _operation, {"question": question, "evidence_paths": evidence_paths, "top_k": top_k, "index_path": index_path}, Result[EvidenceResult])


__all__ = ["evidence_retrieve"]
