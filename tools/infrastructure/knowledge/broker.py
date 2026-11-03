"""Fixed, ownership-checked knowledge operations for isolated sessions.

Queue/database and embedding credentials stay in the service process. Retrieval
artifacts are staged and quota-checked before publication to the user's workspace.
No model-supplied handler or executable is accepted at this boundary.
"""
import asyncio
import importlib
from pathlib import Path
import tempfile

from auth import current_principal
from isolation.files import inventory, import_staged
from isolation.storage import reserve, release, storage_lock, check_quota
from isolation.supervisor import workspace_lock
from tools.infrastructure.tool_support.context import OperationContext

TOOLS = frozenset({'knowledge_ingest', 'knowledge_status', 'knowledge_retrieve'})
MAX_ARTIFACT_BYTES = 8 * 1024 * 1024


async def calculate(name, arguments, metadata, *, access):
    if name not in TOOLS:
        raise ValueError('Unknown knowledge operation.')
    session_id = str(metadata.get('session_id') or '')
    root = access.workspace(session_id)
    if (metadata.get('owner_user_id') != current_principal().user_id
            or Path(str(metadata.get('session_dir'))).resolve() != root.resolve()):
        raise ValueError('Knowledge workspace does not match its authenticated owner.')
    root.mkdir(parents=True, exist_ok=True)
    handler = importlib.import_module(f'tools.function_tools.knowledge.{name}')._operation
    if name != 'knowledge_retrieve':
        return await asyncio.to_thread(handler, context=OperationContext(name, metadata), **arguments)
    async with workspace_lock(session_id, access=access):
        reservation = reserve(access, session_id, MAX_ARTIFACT_BYTES, kind='worker', seconds=300)
        try:
            with tempfile.TemporaryDirectory(dir=access.metadata_root, prefix='.knowledge-') as directory:
                stage = Path(directory)
                context = OperationContext(name, {**metadata, 'session_dir': str(stage), 'workspace_dir': str(stage / 'outputs')})
                # Shield fixed host work from cancellation so its staging directory
                # is not removed while a thread is still writing the result.
                task = asyncio.create_task(asyncio.to_thread(handler, context=context, **arguments))
                try:
                    result = await asyncio.shield(task)
                except asyncio.CancelledError:
                    await task
                    raise
                access.ownership.require(session_id)
                with storage_lock(access):
                    size = sum(inventory(stage, max_bytes=MAX_ARTIFACT_BYTES).values())
                    check_quota(access, session_id, size)
                    import_staged(root, {}, stage)
                return result
        finally:
            release(access, reservation)
