"""Host supervisor for disposable Docker tool workers.

The model client and account/queue databases stay on the trusted server. No
application workspace, socket, environment, or credential is mounted into a worker.
Only private per-invocation staging directories are mounted; JSON carries metadata.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from threading import Thread, Event
import time
from uuid import uuid4

from auth import ExecutionUnavailable, current_principal
from .protocol import MAX_WIRE
from .network import NETWORK_TOOLS
from .embeddings import TOOLS as EMBEDDING_TOOLS
from .files import inventory, stage_files, import_staged, scratch_usage
from .limits import limits, public_limits, setting
from .storage import reserve, release, storage_lock, check_quota
from .policy import IMAGE, WORKER_TIMEOUT, ISOLATED_TOOLS, SERVICE_TOOLS, WorkspaceAccess

_available: tuple[str, float] | None = None
DEADLINE_LABEL = 'io.bioagent.worker-deadline'


def ensure_available() -> None:
    global _available
    image = os.getenv('AGENT_WORKER_IMAGE', IMAGE)
    if _available and _available[0] == image and time.monotonic() - _available[1] < 10:
        return
    try:
        if not shutil.which('docker'):
            raise RuntimeError('Docker is not installed.')
        result = subprocess.run(['docker', 'image', 'inspect', image], capture_output=True, timeout=10)
        if result.returncode:
            raise RuntimeError('Worker image or Docker daemon is unavailable.')
        images = json.loads(result.stdout)
        if not images or (images[0].get('Config', {}).get('Labels') or {}).get('io.bioagent.worker-protocol') != '3':
            raise RuntimeError('Worker image predates the current tool adapters.')
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        raise ExecutionUnavailable(
            'Isolated workers are unavailable. Build with: docker build -f isolation/deploy/Dockerfile '
            '-t bioagent-worker:local . (No fallback to host execution.)'
        ) from exc
    _available = (image, time.monotonic())


def command(name: str) -> list[str]:
    return [
        'docker', 'run', '--rm', '--name', name, '--pull=never', '-i', '--init',
        '--label', f'{DEADLINE_LABEL}={time.time() + WORKER_TIMEOUT + 15}',
        '--network=none', '--read-only', '--cap-drop=ALL', '--security-opt=no-new-privileges',
        f'--user={os.getuid() or 10001}:{os.getgid() or 10001}', '--pids-limit=64', f'--cpus={os.getenv("AGENT_WORKER_CPUS", "1")}',
        f'--memory={setting("WORKER_MEMORY_BYTES", 1024 ** 3)}', f'--memory-swap={setting("WORKER_MEMORY_BYTES", 1024 ** 3)}',
        '--ulimit=nofile=256:256', f'--ulimit=fsize={limits().file_bytes}:{limits().file_bytes}', '--log-driver=none',
        '--env=OPENBLAS_NUM_THREADS=1', '--env=OMP_NUM_THREADS=1', '--env=MKL_NUM_THREADS=1',
        os.getenv('AGENT_WORKER_IMAGE', IMAGE),
    ]


def reap_expired_workers() -> None:
    """Clean up labelled orphans left by a killed controller or server restart."""
    try:
        listed = subprocess.run(['docker', 'ps', '-aq', '--filter', f'label={DEADLINE_LABEL}'],
                                capture_output=True, text=True, timeout=10)
        if listed.returncode or not listed.stdout.strip():
            return
        records = subprocess.run(['docker', 'inspect', *listed.stdout.split()],
                                 capture_output=True, text=True, timeout=10)
        if records.returncode:
            return
        for record in json.loads(records.stdout):
            deadline = float(record['Config']['Labels'][DEADLINE_LABEL])
            if deadline < time.time():
                subprocess.run(['docker', 'rm', '-f', record['Id']],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        # Requests still fail closed when Docker is unavailable; retry cleanup.
        return


def _cleanup_staging(metadata_root):
    parent = metadata_root / '.worker-stage'
    if not parent.exists(): return
    try:
        active = subprocess.run(['docker', 'ps', '--format', '{{.Names}}'], capture_output=True, text=True, timeout=10)
        if active.returncode: return  # Never remove a possibly live mount when Docker is unavailable.
        names = set(active.stdout.splitlines())
        for folder in parent.iterdir():
            if not folder.is_dir() or folder.is_symlink(): continue
            marker = folder / 'lease.json'
            if not marker.is_file(): continue
            lease = json.loads(marker.read_text())
            if lease['deadline'] < time.time() and lease['container'] not in names:
                shutil.rmtree(folder)
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        return


def start_worker_reaper(metadata_root: Path | None = None) -> Event:
    stopped = Event()
    def reap():
        while not stopped.is_set():
            reap_expired_workers()
            if metadata_root is not None:
                _cleanup_staging(metadata_root)
            stopped.wait(30)
    Thread(target=reap, daemon=True, name='isolated-worker-cleanup').start()
    return stopped


def _remap(value, source: str, target: str):
    if isinstance(value, str):
        return value.replace(source, target)
    if isinstance(value, dict):
        return {k: _remap(v, source, target) for k, v in value.items()}
    if isinstance(value, list):
        return [_remap(v, source, target) for v in value]
    return value


@asynccontextmanager
async def workspace_lock(session_id: str, *, access: WorkspaceAccess):
    directory = access.metadata_root / '.worker-locks'
    directory.mkdir(parents=True, exist_ok=True)
    # Session IDs have already been validated by session_root().
    with (directory / session_id).open('a') as lock:
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                await asyncio.sleep(.05)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


async def _read_limited(reader, limit: int) -> bytes:
    data = bytearray()
    while chunk := await reader.read(65536):
        data.extend(chunk)
        if len(data) > limit:
            raise ValueError('Isolated worker exceeded its output limit.')
    return bytes(data)


async def _stop(name: str) -> None:
    # --rm covers normal exits; forced removal also kills all descendants after
    # timeout, cancellation, malformed output, or a lost Docker CLI connection.
    process = await asyncio.create_subprocess_exec('docker', 'rm', '-f', name,
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
    try:
        await asyncio.wait_for(process.wait(), 15)
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()


def _selected_files(root, arguments, name):
    names = inventory(root)
    if name == 'code_inspection' and arguments.get('operation', 'tree') == 'tree': return []
    requested = set()
    def visit(value):
        if isinstance(value, dict):
            for item in value.values(): visit(item)
        elif isinstance(value, list):
            for item in value: visit(item)
        elif isinstance(value, str) and len(value) < 4096:
            path = value.removeprefix(str(root) + '/')
            if path in names:
                requested.add(path)
            elif '/' not in path:
                requested.update(key for key in names if Path(key).name == path)
            elif path and path != '.' and any(key.startswith(path.rstrip('/') + '/') for key in names):
                requested.update(key for key in names if key.startswith(path.rstrip('/') + '/'))
    visit(arguments)
    if not requested and ((name == 'workspace_search' and not arguments.get('path')) or
                          (name == 'code_inspection' and arguments.get('operation') == 'search')):
        requested.update(names)
    # Source code may depend on sibling modules/configuration; omit unrelated data artifacts.
    if name == 'code_test':
        requested.update(key for key in names if not key.startswith(('uploads/', 'outputs/')) or Path(key).suffix in {'.py', '.toml', '.ini', '.cfg'})
        import shlex
        for word in shlex.split(arguments.get('command', '')): visit(word)
    # Feature documents can refer to another workspace input.
    if name == 'genome_render_map':
        for key in list(requested):
            if key.endswith('.json') and names[key] <= 1024 * 1024:
                try: visit(json.loads((root / key).read_text()))
                except (ValueError, OSError): pass
    return sorted(requested)


async def calculate(handler, arguments: dict, metadata: dict, name: str, *, access: WorkspaceAccess, quota_access: WorkspaceAccess | None = None):
    pipeline = name == 'pipeline_execute' and handler.__module__ == 'tools.infrastructure.pipeline_engine.isolated_worker' and handler.__name__ == '_operation'
    if not pipeline and (name not in ISOLATED_TOOLS or name in SERVICE_TOOLS):
        raise ExecutionUnavailable(f'{name} has no isolated execution adapter.')
    identifier = str(metadata.get('session_id') or '')
    access.ownership.require(identifier)
    quota_access = quota_access or access
    if quota_access.metadata_root.resolve() != access.metadata_root.resolve():
        raise ExecutionUnavailable('Worker quota accounting must use the same ownership store.')
    quota_access.ownership.require(identifier)
    if metadata.get('owner_user_id') != current_principal().user_id:
        raise ExecutionUnavailable('Worker owner does not match the authenticated account.')
    root = access.workspace(identifier)
    root.mkdir(parents=True, exist_ok=True)
    if Path(str(metadata.get('session_dir'))).resolve() != root.resolve():
        raise ExecutionUnavailable('Worker workspace does not match the owned session.')
    await asyncio.to_thread(ensure_available)
    lock_id = identifier + '-' + arguments['record']['job_id'] if pipeline else identifier
    async with workspace_lock(lock_id, access=access):
        reservation = reserve(quota_access, identifier, limits().worker_bytes, kind='worker', seconds=WORKER_TIMEOUT + 300)
        staging_parent = access.metadata_root / '.worker-stage'
        staging_parent.mkdir(mode=0o700, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(dir=staging_parent)
        stage = Path(temporary.name)
        work = stage / 'workspace'
        scratch = stage / 'tmp'
        work.mkdir(); scratch.mkdir()
        container = 'bioagent-tool-' + uuid4().hex
        (stage / 'lease.json').write_text(json.dumps({'container': container, 'deadline': time.time() + WORKER_TIMEOUT + 300}))
        try:
            before = stage_files(root, work, _selected_files(root, arguments, name))
            if os.getuid() == 0:
                for directory, dirs, files in os.walk(stage):
                    os.chown(directory, 10001, 10001)
                    for filename in files: os.chown(Path(directory) / filename, 10001, 10001)
        except BaseException:
            temporary.cleanup(); release(access, reservation)
            raise
        try:
            worker_metadata = dict(metadata)
            if name == 'code_inspection' and arguments.get('operation', 'tree') == 'tree':
                worker_metadata['file_inventory'] = inventory(root)
            request = {
                'handler': f'{handler.__module__}:{handler.__name__}', 'name': name,
                'arguments': arguments,
                'metadata': _remap(worker_metadata, str(root), '/workspace'),
                'staged': True,
                'limits': public_limits(),
                'network': name in NETWORK_TOOLS,
                'embeddings': name in EMBEDDING_TOOLS,
            }
            payload = json.dumps(request, allow_nan=False).encode()
            if len(payload) > MAX_WIRE:
                raise ValueError('Worker input exceeds its size limit.')
            argv = command(container)
            argv[-1:-1] = ['--mount', f'type=bind,src={work},dst=/workspace', '--mount', f'type=bind,src={scratch},dst=/tmp']
            if pipeline:
                from tools.infrastructure.pipeline_engine import contracts
                plugin, _, _ = contracts.definition(arguments['record']['plan']['pipeline_name'])
                # Only the operator-installed definition is mounted, read-only.
                # Session inputs/results still use private staging directories.
                argv[-1:-1] = ['--mount', f'type=bind,src={plugin.resolve()},dst=/app/tools/runtime_tools/pipelines/{plugin.name},readonly']
            process = await asyncio.create_subprocess_exec(*argv,
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                limit=MAX_WIRE + 1)
            async def feed():
                process.stdin.write(payload + b'\n')
                await process.stdin.drain()
                if name not in NETWORK_TOOLS | EMBEDDING_TOOLS:
                    process.stdin.close()
            async def receive():
                from .network import fetch
                for count in range(65):
                    line = await process.stdout.readline()
                    if len(line) > MAX_WIRE:
                        raise ValueError('Worker response exceeds its limit.')
                    reply = json.loads(line)
                    if not isinstance(reply, dict) or not ({'network_request', 'embedding_request'} & reply.keys()):
                        return line
                    if count == 64:
                        raise ValueError('Worker exceeded its broker request limit.')
                    access.ownership.require(identifier)
                    try:
                        if 'embedding_request' in reply:
                            from .embeddings import calculate as embed
                            result = await asyncio.to_thread(embed, reply['embedding_request'], name)
                        else:
                            result = await asyncio.to_thread(fetch, reply['network_request'], name)
                    except ValueError as exc:
                        result = {'error': str(exc)}
                    except Exception:
                        result = {'error': 'Public network request failed; retry later.'}
                    wire = json.dumps(result, allow_nan=False).encode() + b'\n'
                    if len(wire) > MAX_WIRE:
                        raise ValueError('Broker response exceeds its wire limit.')
                    process.stdin.write(wire)
                    await process.stdin.drain()
                raise ValueError('Worker exceeded its request limit.')
            async def watch_storage():
                def inspect_storage():
                    if pipeline:
                        used = sum(inventory(work, max_bytes=limits().worker_bytes).values())
                        scratch_usage(scratch, max_bytes=limits().worker_bytes - used)
                    else:
                        inventory(stage, max_bytes=limits().worker_bytes)
                while process.returncode is None:
                    try:
                        await asyncio.to_thread(inspect_storage)
                    except FileNotFoundError:
                        pass
                    await asyncio.sleep(.2)
            tasks = [asyncio.create_task(feed()), asyncio.create_task(receive()),
                     asyncio.create_task(_read_limited(process.stderr, 1024 * 1024)), asyncio.create_task(process.wait()), asyncio.create_task(watch_storage())]
            try:
                _, stdout, stderr, code, _ = await asyncio.wait_for(asyncio.gather(*tasks), timeout=WORKER_TIMEOUT)
                if code:
                    raise ValueError(f'Isolated worker exited with code {code}: {stderr.decode(errors="replace")[-2000:]}')
                reply = json.loads(stdout)
                if not isinstance(reply, dict) or reply.get('ok') is not True:
                    raise ValueError(str(reply.get('error', 'Invalid worker response')) if isinstance(reply, dict) else 'Invalid worker response')
                await _stop(container)  # No live container process may mutate files during validation.
                access.ownership.require(identifier)
                with storage_lock(access):
                    after_size = sum(inventory(work, max_bytes=limits().worker_bytes).values())
                    check_quota(quota_access, identifier, max(0, after_size - sum(item['size'] for item in before.values())))
                    import_staged(root, before, work)
                return _remap(reply.get('value'), '/workspace', str(root))
            finally:
                for task in tasks:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                await asyncio.shield(_stop(container))
                if process.returncode is None:
                    process.kill()
                await process.wait()
        finally:
            temporary.cleanup()
            release(access, reservation)
