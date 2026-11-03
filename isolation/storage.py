"""Account/session quota accounting and disk reservations shared by server writers."""
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import shutil
import time
import re
import tempfile
from uuid import uuid4

from auth import current_principal
from .files import inventory, open_regular, copy_stream
from .limits import limits


@contextmanager
def storage_lock(access):
    access.metadata_root.mkdir(parents=True, exist_ok=True)
    with (access.metadata_root / '.storage.lock').open('a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def reservations(access):
    path = access.metadata_root / '.storage-reservations.json'
    rows = json.loads(path.read_text()) if path.exists() else {}
    return {key: row for key, row in rows.items() if row['expires'] > time.time()}


def save_reservations(access, rows):
    path = access.metadata_root / '.storage-reservations.json'
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(rows))
    os.replace(temporary, path)


def _stored_bytes(access, session_id):
    """Count storage for an ID already authorized by the caller, including tombstones."""
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', session_id):
        raise ValueError('Invalid session_id.')
    total = 0
    for root in (access.workspaces_root / session_id, access.metadata_root / '.pipelines' / session_id):
        if root.is_symlink():
            raise ValueError('Storage roots cannot be symbolic links.')
        if root.exists():
            total += sum(inventory(root).values())
    return total


def usage(access, session_id):
    access.ownership.require(session_id)
    return _stored_bytes(access, session_id)


def _account_usage(access):
    # Tombstones still belong to this account. Count retained files without
    # granting access to deleted sessions or ignoring their storage charges.
    return sum(_stored_bytes(access, identifier)
               for identifier in access.ownership.owned_ids(include_deleted=True))


def check_quota(access, session_id, additional, *, exclude=None):
    access.ownership.require(session_id)
    budget = limits()
    rows = reservations(access)
    pending = [row for key, row in rows.items() if key != exclude and row['kind'] in {'upload', 'multipart'}]
    session = usage(access, session_id)
    account = _account_usage(access)
    if session + additional + sum(row['size'] for row in pending if row['session_id'] == session_id) > budget.session_bytes:
        raise ValueError(f'Session storage quota exceeded ({budget.session_bytes} bytes). Delete unused files or increase the configured quota.')
    if account + additional + sum(row['size'] for row in pending if row['user_id'] == current_principal().user_id) > budget.account_bytes:
        raise ValueError(f'Account storage quota exceeded ({budget.account_bytes} bytes).')


def reserve(access, session_id, size, *, kind='upload', seconds=86400):
    with storage_lock(access):
        if session_id: access.ownership.require(session_id)
        if kind == 'upload':
            check_quota(access, session_id, size)
        rows = reservations(access)
        if kind == 'multipart':
            account = _account_usage(access)
            pending = sum(row['size'] for row in rows.values() if row['kind'] in {'upload', 'multipart'} and row['user_id'] == current_principal().user_id)
            if account + pending + size > limits().account_bytes: raise ValueError('Account storage quota exceeded.')
        disk_size = size * 2  # Staging and atomic publication may coexist.
        if shutil.disk_usage(access.metadata_root).free - sum(row.get('disk_size', row['size']) for row in rows.values()) - disk_size < limits().free_disk_bytes:
            raise ValueError('Insufficient unreserved disk space for this operation.')
        identifier = uuid4().hex
        rows[identifier] = {'session_id': session_id, 'user_id': current_principal().user_id,
                            'size': size, 'disk_size': disk_size, 'kind': kind, 'expires': time.time() + seconds}
        save_reservations(access, rows)
        return identifier


def release(access, identifier):
    with storage_lock(access):
        rows = reservations(access)
        rows.pop(identifier, None)
        save_reservations(access, rows)


def publish(access, session_id, filename, source, size, *, reservation=None, stable_name=True):
    """Atomically publish a complete regular upload after quota and ownership checks."""
    from tools.infrastructure.workspace import workspace_file_metadata
    if size <= 0 or size > limits().file_bytes:
        raise ValueError(f'File size must be between 1 and {limits().file_bytes} bytes.')
    root = access.workspace(session_id)
    safe = re.sub(r'[^A-Za-z0-9_.-]+', '_', Path(filename).name).strip('._') or 'upload.bin'
    safe = safe[:200]
    relative = 'uploads/' + (reservation if reservation and stable_name else uuid4().hex) + '_' + safe
    with storage_lock(access):
        existing = root / relative
        previous_size = existing.stat().st_size if existing.is_file() and not existing.is_symlink() else 0
        check_quota(access, session_id, max(0, size - previous_size), exclude=reservation)
        directory = root / 'uploads'
        if directory.is_symlink(): raise ValueError('Upload directory cannot be a symlink.')
        directory.mkdir(parents=True, exist_ok=True)
        if shutil.disk_usage(directory).free - size < limits().free_disk_bytes:
            raise ValueError('Insufficient workspace disk space for atomic publication.')
        fd, temporary = tempfile.mkstemp(prefix='.upload-', dir=directory)
        try:
            with os.fdopen(fd, 'wb') as target, open_regular(source.parent, source.name) as incoming:
                actual = copy_stream(incoming, target, size)
            if actual['size'] != size: raise ValueError('Upload length changed.')
            destination = root / relative
            os.replace(temporary, destination)
        finally:
            Path(temporary).unlink(missing_ok=True)
    return {'session_id': session_id, 'path': relative, 'workspace_path': relative, 'name': safe,
            'size': size, 'sha256': actual['sha256'], **workspace_file_metadata(destination, uploaded=True)}
