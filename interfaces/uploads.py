"""Disk-spooled multipart parsing and owned, resumable uploads."""
from contextlib import contextmanager
from email.parser import BytesParser
import json
import os
from pathlib import Path
import re
import tempfile
import time

from auth import AccessDenied
from isolation.limits import limits
from isolation.storage import reserve, release, publish


@contextmanager
def multipart(stream, length, boundary, directory):
    """Parse bounded multipart chunks without retaining file bodies in memory."""
    if not boundary or len(boundary) > 200 or b'\r' in boundary or b'\n' in boundary:
        raise ValueError('Invalid multipart boundary.')
    remaining, buffer = length, b''
    def fill():
        nonlocal remaining, buffer
        if not remaining:
            return False
        chunk = stream.read(min(65536, remaining))
        if not chunk:
            raise ValueError('Incomplete upload body.')
        remaining -= len(chunk)
        buffer += chunk
        return True
    def take_until(marker, maximum):
        nonlocal buffer
        while marker not in buffer:
            if len(buffer) > maximum or not fill():
                raise ValueError('Invalid or oversized multipart headers.')
        value, buffer = buffer.split(marker, 1)
        if len(value) > maximum:
            raise ValueError('Multipart headers exceed their limit.')
        return value
    with tempfile.TemporaryDirectory(dir=directory) as temporary:
        fill()
        if take_until(b'\r\n', 2048) != b'--' + boundary:
            raise ValueError('Invalid multipart start.')
        parts = []
        marker = b'\r\n--' + boundary
        while True:
            if len(parts) >= 128:
                raise ValueError('At most 128 multipart fields are accepted.')
            headers = BytesParser().parsebytes(take_until(b'\r\n\r\n', 16384) + b'\r\n\r\n')
            name = headers.get_param('name', header='content-disposition')
            filename = headers.get_filename()
            target = Path(temporary) / str(len(parts))
            size = 0
            with target.open('wb') as output:
                while True:
                    index = buffer.find(marker)
                    if index >= 0:
                        while len(buffer) < index + len(marker) + 2 and fill(): pass
                        suffix = buffer[index + len(marker):index + len(marker) + 2]
                        if suffix in {b'--', b'\r\n'}:
                            output.write(buffer[:index]); size += index
                            buffer = buffer[index + len(marker) + 2:]
                            break
                        # A boundary-shaped byte sequence inside a file is ordinary data.
                        count = index + 2
                    else:
                        count = max(0, len(buffer) - len(marker) - 2)
                    if count:
                        output.write(buffer[:count]); size += count; buffer = buffer[count:]
                    if size > (limits().file_bytes if filename is not None else 4096):
                        raise ValueError('Multipart field exceeds its limit.')
                    if marker in buffer:
                        continue
                    if not fill():
                        raise ValueError('Incomplete multipart body.')
            if size > (limits().file_bytes if filename is not None else 4096):
                raise ValueError('Multipart field exceeds its limit.')
            parts.append({'name': name, 'filename': filename, 'path': target, 'size': size,
                          'content_type': headers.get_content_type()})
            if suffix == b'--':
                while fill():
                    if buffer.strip(): raise ValueError('Unexpected multipart epilogue.')
                    buffer = b''
                if buffer.strip(): raise ValueError('Unexpected multipart epilogue.')
                break
        yield parts


class Uploads:
    def __init__(self, access):
        self.access = access
        self.root = access.metadata_root / '.uploads'
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.cleanup()

    def cleanup(self):
        import fcntl
        import shutil
        for folder in self.root.iterdir():
            if not folder.is_dir() or folder.is_symlink(): continue
            try:
                with (folder / 'lock').open('a') as stream:
                    fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    state = folder / 'state.json'
                    if not state.exists(): continue
                    row = json.loads(state.read_text())
                    if row['expires'] >= time.time(): continue
                    shutil.rmtree(folder)
                    release(self.access, row['upload_id'])
            except (BlockingIOError, FileNotFoundError):
                continue

    def create(self, session_id, filename, size):
        size = int(size)
        if not 0 < size <= limits().file_bytes:
            raise ValueError(f'File exceeds the {limits().file_bytes} byte upload limit.')
        identifier = reserve(self.access, session_id, size)
        folder = self.root / identifier
        try:
            folder.mkdir(mode=0o700)
            row = {'upload_id': identifier, 'session_id': session_id, 'filename': str(filename),
                   'size': size, 'offset': 0, 'expires': time.time() + 86400}
            self._save(folder, row)
            (folder / 'data').touch()
            return row
        except BaseException:
            release(self.access, identifier)
            raise

    def _save(self, folder, row):
        temporary = folder / 'state.tmp'
        temporary.write_text(json.dumps(row))
        os.replace(temporary, folder / 'state.json')

    @contextmanager
    def locked(self, identifier):
        import fcntl
        if not re.fullmatch('[a-f0-9]{32}', identifier): raise AccessDenied('Upload not found.')
        folder = self.root / identifier
        try:
            lock = (folder / 'lock').open('a')
        except FileNotFoundError:
            raise AccessDenied('Upload not found.') from None
        with lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            row = json.loads((folder / 'state.json').read_text())
            self.access.ownership.require(row['session_id'])
            if row['expires'] < time.time(): raise ValueError('Upload expired; start a new upload.')
            yield folder, row

    def status(self, identifier):
        with self.locked(identifier) as (_, row): return row

    def append(self, identifier, offset, source, length):
        with self.locked(identifier) as (folder, row):
            if row.get('file'): return row
            if offset != row['offset']: raise ValueError(f'Upload offset mismatch; resume at {row["offset"]}.')
            if length <= 0 or length > limits().upload_chunk_bytes or offset + length > row['size']:
                raise ValueError('Upload chunk exceeds its limit or declared file size.')
            # Roll back interrupted writes to the last committed offset.
            with (folder / 'data').open('r+b') as target:
                target.truncate(offset); target.seek(offset)
                left = length
                try:
                    while left:
                        chunk = source.read(min(left, 1024 * 1024))
                        if not chunk: raise ValueError('Incomplete upload chunk.')
                        target.write(chunk); left -= len(chunk)
                except BaseException:
                    target.truncate(offset)
                    raise
            row['offset'] += length
            self._save(folder, row)
            return row

    def complete(self, identifier):
        with self.locked(identifier) as (folder, row):
            if row.get('file'): return row['file']
            if row['offset'] != row['size']: raise ValueError('Upload is incomplete.')
            row['file'] = publish(self.access, row['session_id'], row['filename'], folder / 'data', row['size'], reservation=identifier)
            self._save(folder, row)
            (folder / 'data').unlink(missing_ok=True)
            release(self.access, identifier)
            return row['file']

    def cancel(self, identifier):
        with self.locked(identifier) as (folder, row):
            (folder / 'data').unlink(missing_ok=True)
            row['expires'] = 0; self._save(folder, row)
            release(self.access, identifier)
