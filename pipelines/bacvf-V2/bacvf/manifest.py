"""Run provenance helpers."""

from __future__ import annotations

import hashlib
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


def utc_now() -> str:
    """Return an ISO-8601 UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    """Stream a file SHA-256 without loading it into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def input_records(paths: Iterable[Path]) -> list[dict[str, Any]]:
    """Collect stable input provenance."""
    records: list[dict[str, Any]] = []
    for path in paths:
        stat = path.stat()
        records.append(
            {
                "name": path.name,
                "size": stat.st_size,
                "sha256": sha256_file(path),
            }
        )
    return records


def runtime_record() -> dict[str, str]:
    """Return Python and operating-system provenance."""
    return {
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "executable_name": Path(sys.executable).name,
    }


def database_manifest(path: Path | None, warnings: list[str]) -> dict[str, Any] | None:
    """Record a deployment manifest or a warning-backed file summary."""
    if path is None:
        warnings.append("Database manifest is not configured; strict provenance is unavailable.")
        return None
    if not path.is_file():
        warnings.append(f"Database manifest is missing: {path.name}")
        return None
    import json

    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        warnings.append(f"Database manifest could not be read: {exc}")
        return None
    return payload if isinstance(payload, dict) else {"content": payload}
