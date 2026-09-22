"""Execute one SDK FunctionTool operation and record JSON-only evidence."""
from __future__ import annotations

import asyncio
import __main__
import inspect
import multiprocessing
import os
import signal
from typing import Any

from .context import OperationContext
from .evidence import EvidenceCollector


def _calculate(send, handler, arguments: dict[str, Any], metadata: dict[str, Any], name: str) -> None:
    if hasattr(os, "setsid"):
        os.setsid()
    try:
        value = handler(context=OperationContext(name, metadata), **arguments)
        send.send((True, value))
    except Exception as exc:
        send.send((False, f"{type(exc).__name__}: {exc}"))
    finally:
        send.close()


async def calculate(handler, arguments: dict[str, Any], metadata: dict[str, Any], name: str):
    """Run blocking domain code outside the SDK event loop."""
    method = "spawn"
    main_file = str(getattr(__main__, "__file__", "") or "")
    if (not main_file or not os.path.exists(main_file)) and "fork" in multiprocessing.get_all_start_methods():
        method = "fork"
    ctx = multiprocessing.get_context(method)
    recv, send = ctx.Pipe(duplex=False)
    process = ctx.Process(target=_calculate, args=(send, handler, arguments, metadata, name))
    process.start()
    send.close()
    try:
        while not recv.poll():
            if not process.is_alive():
                raise RuntimeError("Calculation worker exited without a result.")
            await asyncio.sleep(0.02)
        ok, value = recv.recv()
        if not ok:
            raise ValueError(value)
        return value
    finally:
        recv.close()
        if process.is_alive():
            try:
                if hasattr(os, "killpg"):
                    os.killpg(process.pid, signal.SIGKILL)
                else:
                    process.terminate()
            except ProcessLookupError:
                pass
        await asyncio.to_thread(process.join, 2)
        if process.is_alive():
            process.kill()
            await asyncio.to_thread(process.join)
        process.close()


async def invoke(context, name: str, handler, arguments: dict[str, Any], output_type):
    """Run, validate, redact, and record one typed operation result."""
    metadata = {key: value for key, value in context.user_context().items() if key != "_agent_context"}
    context.record("tool_started", tool=name)
    try:
        operation_context = OperationContext(name, metadata)
        value = await handler(context=operation_context, **arguments) if inspect.iscoroutinefunction(handler) else await calculate(handler, arguments, metadata, name)
        result = output_type.model_validate(context.public(value))
    except asyncio.CancelledError:
        context.record("tool_cancelled", tool=name)
        raise

    public_result = result.data.model_dump(mode="json")
    record = {
        "tool": name,
        "arguments": context.public(arguments),
        "result": public_result,
        "status": result.status,
        "error": result.error.message if result.error else None,
        "error_type": result.error.code if result.error else None,
        "tool_calls": [],
    }
    context.tool_results.append(context.public(record))
    result.evidence = EvidenceCollector().collect([record])["citations"]
    known = {item.get("path"): item for item in context.files}
    for item in result.files:
        known[item.path] = item.model_dump(mode="json")
        context.record("artifact_created", tool=name, **item.model_dump(mode="json"))
    context.files = sorted(known.values(), key=lambda item: (item.get("modified_at", 0), item.get("path", "")))
    context.record("tool_finished", tool=name, status=result.status)
    return result
