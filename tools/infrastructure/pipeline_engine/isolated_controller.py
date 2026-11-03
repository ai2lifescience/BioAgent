"""Durable host supervision for isolated local engine plugins."""
import asyncio
from pathlib import Path
import subprocess
import sys
from threading import Thread

from auth import OwnershipStore, Principal, database, principal_scope
from isolation import WorkspaceAccess, supervisor
from .store import JobStore, now
from . import service
from .isolated_worker import _operation


def start(private, identifier, access):
    store = JobStore(private)
    row = store.get(identifier)
    if row['status'] != 'planned': return row
    service.verify(private, row['plan'])
    supervisor.ensure_available()
    from .broker import _lock, ACTIVE
    with _lock(private.parent / '.launch.lock'):
        active = [job for folder in private.parent.iterdir() if folder.is_dir() for job in JobStore(folder).list() if job['status'] in ACTIVE or job.get('submission_unknown')]
        if len(active) >= 16 or sum(job['plan']['owner_user_id'] == row['plan']['owner_user_id'] for job in active) >= 2:
            raise ValueError('Pipeline job limit reached (2 per account, 16 server-wide).')
        row = store.update(identifier, expected={'planned'}, status='queued', started_at=now(), execution_backend='docker')
    try:
        process = subprocess.Popen([sys.executable, '-B', '-m', __name__, str(access.metadata_root.resolve()), str(access.workspaces_root.resolve()), private.name, identifier],
                                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        identity = service.identity(process.pid)
        Thread(target=process.wait, daemon=True).start()
        return store.update(identifier, controller_pid=process.pid, controller_identity=identity)
    except Exception as exc:
        return store.update(identifier, status='failed', finished_at=now(), error=str(exc))


def status(private, identifier):
    store = JobStore(private); row = store.get(identifier)
    if row['status'] in {'queued', 'running', 'cancelling'} and row.get('controller_pid'):
        if service.identity(row['controller_pid']) != row.get('controller_identity'):
            row = store.update(identifier, status='interrupted', finished_at=now(), error='Pipeline controller stopped; execution was not resubmitted.')
    return row


async def execute(access, session_id, identifier):
    private = access.metadata_root / '.pipelines' / session_id
    store = JobStore(private)
    row = store.get(identifier)
    access.ownership.require(session_id)
    if row['status'] == 'cancelling':
        store.update(identifier, expected={'cancelling'}, status='cancelled', finished_at=now())
        return
    if row['status'] != 'queued': return
    row = store.update(identifier, expected={'queued'}, status='running')
    private_access = WorkspaceAccess(access.ownership, access.metadata_root / '.pipelines')
    metadata = {'session_id': session_id, 'owner_user_id': row['plan']['owner_user_id'],
                'session_dir': str(private), 'workspace_dir': str(private / 'outputs')}
    task = asyncio.create_task(supervisor.calculate(_operation, {'record': row}, metadata, 'pipeline_execute', access=private_access, quota_access=access))
    try:
        while not task.done():
            if store.get(identifier)['status'] == 'cancelling':
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                store.update(identifier, status='cancelled', finished_at=now())
                return
            await asyncio.wait({task}, timeout=.2)
        result = await task
        access.ownership.require(session_id)
        if store.get(identifier)['status'] == 'cancelling':
            store.update(identifier, expected={'cancelling'}, status='cancelled', finished_at=now())
        else:
            store.update(identifier, expected={'running'}, status='succeeded', finished_at=now(), result=result)
    except Exception as exc:
        store.update(identifier, status='timed_out' if isinstance(exc, asyncio.TimeoutError) else 'failed', finished_at=now(), error=str(exc) or 'Pipeline exceeded its worker deadline.')
    finally:
        if not task.done(): task.cancel()
        await asyncio.gather(task, return_exceptions=True)


def main():
    metadata, workspaces, session_id, identifier = sys.argv[1:]
    ownership = OwnershipStore(Path(metadata))
    with database(ownership.path) as db:
        owner = db.execute('SELECT user_id FROM owners WHERE session_id=? AND deleted=0', (session_id,)).fetchone()
    if owner is None: raise ValueError('Session has no active owner.')
    access = WorkspaceAccess(ownership, Path(workspaces))
    with principal_scope(Principal(owner['user_id'])):
        asyncio.run(execute(access, session_id, identifier))


if __name__ == '__main__': main()
