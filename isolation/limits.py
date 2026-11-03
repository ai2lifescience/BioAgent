"""Storage budgets, distinct from bounded JSON/model responses (all sizes in bytes)."""
from dataclasses import asdict, dataclass
import os

MiB = 1024 ** 2
GiB = 1024 ** 3


def setting(name, default):
    value = int(os.getenv('AGENT_' + name, default))
    if value <= 0:
        raise ValueError('AGENT_' + name + ' must be positive.')
    return value


@dataclass(frozen=True)
class Limits:
    upload_bytes: int
    file_bytes: int
    session_bytes: int
    account_bytes: int
    worker_bytes: int
    worker_files: int
    preview_bytes: int
    scan_bytes: int
    free_disk_bytes: int
    upload_chunk_bytes: int


def limits():
    return Limits(setting('MAX_UPLOAD_BYTES', 256 * MiB), setting('MAX_FILE_BYTES', 5 * GiB),
                  setting('SESSION_STORAGE_BYTES', 20 * GiB), setting('ACCOUNT_STORAGE_BYTES', 50 * GiB),
                  setting('WORKER_STORAGE_BYTES', 10 * GiB), setting('WORKER_MAX_FILES', 100_000),
                  setting('PREVIEW_BYTES', 64 * 1024), setting('SEARCH_SCAN_BYTES', 256 * MiB),
                  setting('MIN_FREE_DISK_BYTES', GiB), setting('UPLOAD_CHUNK_BYTES', 8 * MiB))


def public_limits():
    return asdict(limits())
