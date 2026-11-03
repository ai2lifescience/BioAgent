"""Streaming regular-file snapshots. No file contents travel in JSON."""
from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import stat
import shutil
import tempfile

from .limits import limits
from .protocol import relative_path

CHUNK = 1024 * 1024


@contextmanager
def open_regular(root, name):
    """Open every component without following links, including parent directories."""
    parts = relative_path(name).parts
    descriptors = []
    try:
        fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        descriptors.append(fd)
        for part in parts[:-1]:
            fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            descriptors.append(fd)
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise ValueError('Only regular files are accepted; links and devices are rejected.')
            yield stream
    finally:
        for fd in reversed(descriptors):
            os.close(fd)


def copy_stream(source, target, maximum):
    size = 0
    digest = hashlib.sha256()
    while chunk := source.read(min(CHUNK, maximum - size + 1)):
        size += len(chunk)
        if size > maximum:
            raise ValueError(f'File exceeds the {maximum} byte limit.')
        digest.update(chunk)
        target.write(chunk)
    return {'size': size, 'sha256': digest.hexdigest()}


def fingerprint(root, name):
    digest = hashlib.sha256()
    with open_regular(root, name) as stream:
        size = 0
        while chunk := stream.read(CHUNK):
            size += len(chunk)
            digest.update(chunk)
    return {'size': size, 'sha256': digest.hexdigest()}


def inventory(root, *, max_bytes=None, max_files=None):
    """Bound metadata traversal; never read whole files or dereference links."""
    budget = limits()
    max_files = budget.worker_files if max_files is None else max_files
    result, total, entries = {}, 0, 0
    def failed(error): raise error
    for directory, dirs, names in os.walk(root, followlinks=False, onerror=failed):
        entries += len(dirs) + len(names)
        if entries > max_files:
            raise ValueError(f'Workspace exceeds {max_files} filesystem entries.')
        for name in dirs + names:
            path = Path(directory) / name
            info = path.lstat()
            if stat.S_ISDIR(info.st_mode):
                continue
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise ValueError('Only regular files are accepted; links and devices are rejected.')
            total += info.st_size
            if max_bytes is not None and total > max_bytes:
                raise ValueError(f'Storage exceeds the {max_bytes} byte budget.')
            key = path.relative_to(root).as_posix()
            relative_path(key)
            result[key] = info.st_size
    return result


def stage_files(root, destination, names):
    before, total = {}, 0
    budget = limits()
    for name in names:
        target = destination / relative_path(name)
        target.parent.mkdir(parents=True, exist_ok=True)
        with open_regular(root, name) as source, target.open('wb') as output:
            before[name] = copy_stream(source, output, min(budget.file_bytes, budget.worker_bytes - total))
        total += before[name]['size']
    return before


def scratch_usage(root, *, max_bytes, max_files=None):
    """Count private engine scratch space without following temporary links.

    This is accounting only, never an import/export inventory. Workspace imports
    still use inventory/open_regular and reject all links.
    """
    max_files = limits().worker_files if max_files is None else max_files
    total, entries = 0, 0
    def failed(error): raise error
    for _, dirs, names, descriptor in os.fwalk(root, follow_symlinks=False, onerror=failed):
        entries += len(dirs) + len(names)
        if entries > max_files:
            raise ValueError(f'Scratch space exceeds {max_files} filesystem entries.')
        for name in dirs + names:
            try: info = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
            except FileNotFoundError: continue  # Engines may clean scratch concurrently.
            if stat.S_ISDIR(info.st_mode): continue
            if not (stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode)):
                raise ValueError('Scratch space contains a device or special file.')
            total += info.st_size
            if total > max_bytes:
                raise ValueError(f'Storage exceeds the {max_bytes} byte budget.')
    return total


def import_staged(root, before, staging):
    """Validate all changes before publishing; concurrent uploads survive."""
    sizes = inventory(staging, max_bytes=limits().worker_bytes)
    after = {name: fingerprint(staging, name) for name in sizes}
    changed = {name for name in before.keys() | after.keys() if before.get(name) != after.get(name)}
    for name in changed:
        target = root / relative_path(name)
        current = fingerprint(root, name) if target.exists() or target.is_symlink() else None
        if current != before.get(name):
            raise ValueError('Workspace changed during execution; no worker files were imported. Retry the operation.')
        for parent in target.parents:
            if parent == root:
                break
            if parent.is_symlink() or (parent.exists() and not parent.is_dir()):
                raise ValueError('Worker output has an invalid parent directory.')
    required = sum(after[name]['size'] for name in changed if name in after)
    if shutil.disk_usage(root).free - required < limits().free_disk_bytes:
        raise ValueError('Insufficient workspace disk space for output publication.')
    for name in sorted(changed):
        target = root / relative_path(name)
        if name not in after:
            target.unlink(missing_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix='.worker-', dir=target.parent)
        try:
            with os.fdopen(fd, 'wb') as output, open_regular(staging, name) as source:
                actual = copy_stream(source, output, limits().file_bytes)
            if actual != after[name]:
                raise ValueError('Staged file changed before publication.')
            os.replace(temporary, target)
        finally:
            Path(temporary).unlink(missing_ok=True)
    return after
