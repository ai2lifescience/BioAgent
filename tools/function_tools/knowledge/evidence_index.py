"""Create an immutable, persistent vector index from evidence artifacts."""
from __future__ import annotations

import json
from typing import Annotated, Literal

from agents import RunContextWrapper
from pydantic import Field

from harness.context import AgentRunContext
from tools.infrastructure.tool_support.artifacts import artifact, destination, load_evidence, output
from tools.infrastructure.tool_support.decorators import bio_function_tool
from tools.infrastructure.tool_support.operations import invoke
from tools.infrastructure.tool_support.results import FunctionContract as Contract, FunctionResult as Result

import sqlite3
from tools.infrastructure.tool_support.embeddings import embed_texts
from models.config import DEFAULT_EMBEDDING_MODEL


class IndexResult(Contract):
    index_path: str
    sources: int
    chunks: int
    embedding_model: str
    schema_version: Literal[1] = 1


def _operation(*, evidence_paths: list[str], chunk_chars: int, overlap: int, context):
    if overlap >= chunk_chars:
        raise ValueError("overlap must be smaller than chunk_chars.")
    records = load_evidence(context, evidence_paths)
    if not records:
        raise ValueError("Indexing requires nonempty evidence.")
    chunks = []
    for item in records:
        for offset in range(0, len(item.text), chunk_chars - overlap):
            text = item.text[offset:offset + chunk_chars]
            if text.strip():
                chunks.append((item, text))
            if offset + chunk_chars >= len(item.text):
                break
    if not chunks or len(chunks) > 4000:
        raise ValueError("Select evidence producing between 1 and 4000 chunks.")
    vectors = []
    for start in range(0, len(chunks), 64):
        vectors.extend(embed_texts([text for _, text in chunks[start:start + 64]], model=DEFAULT_EMBEDDING_MODEL))
    if len(vectors) != len(chunks) or not vectors[0] or any(len(v) != len(vectors[0]) for v in vectors):
        raise ValueError("Embedding provider returned inconsistent vectors.")
    target = destination(context, "evidence.sqlite")
    try:
        with sqlite3.connect(target) as database:
            database.execute("CREATE TABLE metadata (schema_version INTEGER, embedding_model TEXT)")
            database.execute("INSERT INTO metadata VALUES (1, ?)", (DEFAULT_EMBEDDING_MODEL,))
            database.execute("CREATE TABLE chunks (ordinal INTEGER PRIMARY KEY, source TEXT NOT NULL, excerpt TEXT NOT NULL, vector TEXT NOT NULL)")
            database.executemany("INSERT INTO chunks (source, excerpt, vector) VALUES (?, ?, ?)", [(item.model_dump_json(), text, json.dumps(vector, allow_nan=False)) for (item, text), vector in zip(chunks, vectors)])
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    file = artifact(context, target)
    return output({"index_path": file["path"], "sources": len(records), "chunks": len(chunks), "embedding_model": DEFAULT_EMBEDDING_MODEL}, file)


@bio_function_tool(timeout=300)
async def evidence_index(
    ctx: RunContextWrapper[AgentRunContext],
    evidence_paths: Annotated[list[str], Field(min_length=1, max_length=10)],
    chunk_chars: Annotated[int, Field(ge=200, le=4000)] = 1200,
    overlap: Annotated[int, Field(ge=0, le=1000)] = 180,
) -> Result[IndexResult]:
    """Embed evidence into a new persistent workspace index. Uses the configured embedding API; return index_path for evidence_retrieve."""
    return await invoke(ctx.context, "evidence_index", _operation, {"evidence_paths": evidence_paths, "chunk_chars": chunk_chars, "overlap": overlap}, Result[IndexResult])


__all__ = ["evidence_index"]
