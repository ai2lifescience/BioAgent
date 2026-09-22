"""Direct bounded workspace file editing."""
from __future__ import annotations

from typing import Annotated

from agents import RunContextWrapper
from pydantic import Field

from harness.context import AgentRunContext
from tools.infrastructure.tool_support.decorators import bio_function_tool
from tools.infrastructure.tool_support.operations import invoke
from tools.infrastructure.tool_support.results import FunctionContract, FunctionResult


import hashlib
import os
from pathlib import Path
import tempfile
from tools.infrastructure.workspace import resolve_session_path
from tools.infrastructure.tool_support.artifacts import artifact, output

class EditResult(FunctionContract):
    path: str
    changed_files: list[str]
    sha256: str
    bytes: int
    summary: str


def _operation(*, path, content, expected_sha256=None, context):
    target = resolve_session_path(context, path)
    encoded = content.encode("utf-8")
    if len(encoded) > 1_000_000:
        raise ValueError("Edited files are limited to 1 MB.")
    if target.is_dir():
        raise ValueError("The edit path is a directory.")
    if expected_sha256 is not None:
        digest = hashlib.sha256(target.read_bytes()).hexdigest() if target.is_file() else None
        if digest != expected_sha256:
            raise ValueError("The file changed since inspection; refresh it before editing.")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("wb", dir=target.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(encoded)
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    file = artifact(context, target)
    return output({"path": file["path"], "changed_files": [file["path"]],
        "sha256": hashlib.sha256(encoded).hexdigest(), "bytes": len(encoded),
        "summary": f"Updated {file['path']}."}, file)


@bio_function_tool()
async def code_edit(
    ctx: RunContextWrapper[AgentRunContext],
    path: Annotated[str, Field(description="Workspace-relative file to create or replace.")],
    content: Annotated[str, Field(max_length=1000000, description="Complete replacement text for the file.")],
    expected_sha256: Annotated[str | None, Field(description="Optional hash from a prior read.")] = None,
) -> FunctionResult[EditResult]:
    """Create or replace one workspace file without SDK approval."""
    return await invoke(ctx.context, "code_edit", _operation,
                              {"path": path, "content": content, "expected_sha256": expected_sha256}, FunctionResult[EditResult])


__all__ = ["code_edit"]
