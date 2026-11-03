"""One disposable tool invocation with optional bounded broker messages."""
from __future__ import annotations

import asyncio
from contextlib import redirect_stdout
import importlib
import inspect
import json
import os
from pathlib import Path
import sys

from .protocol import MAX_WIRE


def main() -> int:
    try:
        # Any library's incidental cache/state stays in the private tmpfs.
        os.chdir('/tmp')
        wire = sys.stdin.buffer.readline(MAX_WIRE + 1)
        if len(wire) > MAX_WIRE:
            raise ValueError("Worker request exceeds its size limit.")
        request = json.loads(wire)
        root = Path('/workspace')
        if not request.get('staged'):
            raise ValueError('This worker requires disk staging; rebuild the worker image.')
        # Only operator-selected numeric limits are inherited, never host credentials.
        keys = {'file_bytes': 'MAX_FILE_BYTES', 'preview_bytes': 'PREVIEW_BYTES', 'scan_bytes': 'SEARCH_SCAN_BYTES', 'worker_bytes': 'WORKER_STORAGE_BYTES'}
        for key, env in keys.items():
            os.environ['AGENT_' + env] = str(int(request['limits'][key]))
        # Import only application-owned functions. This name is supplied by the
        # server's registered tool, never by the model or an HTTP request.
        module, attribute = request['handler'].split(':', 1)
        pipeline = module == 'tools.infrastructure.pipeline_engine.isolated_worker' and attribute == '_operation' and request['name'] == 'pipeline_execute'
        if not pipeline and (not module.startswith('tools.function_tools.') or attribute not in {'_calculate', '_operation'}):
            raise ValueError('Unregistered worker handler.')
        reader, writer = sys.stdin.buffer, sys.stdout.buffer
        with redirect_stdout(sys.stderr):
            module = importlib.import_module(module)
            if request.get('network'):
                from .network_client import install
                install(module, request['name'], reader, writer)
            if request.get('embeddings'):
                from .embeddings import install as install_embeddings
                install_embeddings(module, reader, writer)
            handler = getattr(module, attribute)
            from tools.infrastructure.tool_support.context import OperationContext
            value = handler(context=OperationContext(request['name'], request['metadata']), **request['arguments'])
            if inspect.isawaitable(value):
                value = asyncio.run(value)
        output = {'ok': True, 'value': value}
    except Exception as exc:
        output = {'ok': False, 'error': f'{type(exc).__name__}: {exc}'}
    wire = json.dumps(output, ensure_ascii=True, allow_nan=False).encode()
    if len(wire) > MAX_WIRE:
        wire = b'{"ok":false,"error":"Worker response exceeds its size limit."}'
    sys.stdout.buffer.write(wire)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
