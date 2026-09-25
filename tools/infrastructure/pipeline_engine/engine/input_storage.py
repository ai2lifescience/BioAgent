"""Optional object-storage staging for remote Cromwell inputs.

The Cromwell REST API receives the WDL and input JSON, but it does not copy
local files referenced by that JSON.  This module uploads local file values to
an S3-compatible bucket and rewrites those values to either ``s3://`` URIs or
the corresponding shared-mount paths. The feature is opt-in through
``CROMWELL_INPUT_STORAGE_URI`` so local and shared-filesystem execution keep
their existing behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any, Protocol
from urllib.parse import urlsplit


class InputUploader(Protocol):
    """Small uploader interface used by the adapter and its offline tests."""

    backend: str
    base_uri: str

    def upload(self, source: Path, object_key: str) -> str:
        """Upload ``source`` and return the URI Cromwell should localize."""

    def cromwell_path(self, uri: str, object_key: str) -> str:
        """Return the value to place in Cromwell's WDL inputs JSON."""


@dataclass
class S3InputUploader:
    """S3 or S3-compatible uploader backed by boto3."""

    bucket: str
    prefix: str
    client: Any
    mount_prefix: str | None = None

    backend: str = "s3"

    @property
    def base_uri(self) -> str:
        return f"s3://{self.bucket}/{self.prefix}".rstrip("/")

    @classmethod
    def from_environment(cls) -> "S3InputUploader | None":
        value = str(os.environ.get("CROMWELL_INPUT_STORAGE_URI") or "").strip()
        if not value:
            return None
        parsed = urlsplit(value)
        if parsed.scheme.lower() != "s3" or not parsed.netloc:
            raise ValueError(
                "CROMWELL_INPUT_STORAGE_URI must be an s3://bucket/prefix URI. "
                "The bucket must be readable by Cromwell's execution backend."
            )
        try:
            import boto3  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError(
                "CROMWELL_INPUT_STORAGE_URI is configured, but boto3 is not installed. "
                "Install the project requirements before using S3 input staging."
            ) from exc
        endpoint = str(os.environ.get("CROMWELL_INPUT_STORAGE_ENDPOINT") or "").strip() or None
        region = str(os.environ.get("CROMWELL_INPUT_STORAGE_REGION") or "").strip() or None
        access_key = str(os.environ.get("CROMWELL_INPUT_STORAGE_ACCESS_KEY") or "").strip()
        secret_key = str(os.environ.get("CROMWELL_INPUT_STORAGE_SECRET_KEY") or "").strip()
        session_token = str(os.environ.get("CROMWELL_INPUT_STORAGE_SESSION_TOKEN") or "").strip() or None
        credentials = None
        if access_key or secret_key:
            if not access_key or not secret_key:
                raise ValueError(
                    "CROMWELL_INPUT_STORAGE_ACCESS_KEY and "
                    "CROMWELL_INPUT_STORAGE_SECRET_KEY must be supplied together."
                )
            credentials = {
                "aws_access_key_id": access_key,
                "aws_secret_access_key": secret_key,
            }
            if session_token:
                credentials["aws_session_token"] = session_token
        from botocore.config import Config  # type: ignore[import-not-found]

        client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            region_name=region,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
            ),
            **(credentials or {}),
        )
        mount_prefix = str(os.environ.get("CROMWELL_INPUT_STORAGE_MOUNT_PREFIX") or "").strip() or None
        if mount_prefix is not None and not mount_prefix.startswith("/"):
            raise ValueError("CROMWELL_INPUT_STORAGE_MOUNT_PREFIX must be an absolute path.")
        return cls(
            bucket=parsed.netloc,
            prefix=parsed.path.strip("/"),
            client=client,
            mount_prefix=mount_prefix.rstrip("/") if mount_prefix else None,
        )

    def upload(self, source: Path, object_key: str) -> str:
        key = "/".join(part for part in (self.prefix, object_key) if part)
        self.client.upload_file(str(source), self.bucket, key)
        return f"s3://{self.bucket}/{key}"

    def cromwell_path(self, uri: str, object_key: str) -> str:
        """Use the shared mount when configured; otherwise retain the S3 URI."""
        if not self.mount_prefix:
            return uri
        key = "/".join(part for part in (self.prefix, object_key) if part)
        return f"{self.mount_prefix}/{self.bucket}/{key}"


def _safe_name(value: str) -> str:
    name = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._")
    return name or "input.bin"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _object_key(source: Path, pipeline_name: str, run_id: str, digest: str) -> str:
    return "/".join((
        "bioagent",
        _safe_name(pipeline_name),
        _safe_name(run_id),
        f"{digest[:16]}-{_safe_name(source.name)}",
    ))


def upload_local_file_values(
    inputs_path: Path,
    uploader: InputUploader,
    *,
    pipeline_name: str,
    run_id: str,
) -> list[dict[str, Any]]:
    """Upload local file values in a WDL inputs JSON and rewrite it in place.

    Strings that are not existing local regular files are preserved.  This is
    intentional: mounted reference database paths can remain as paths that
    already exist inside the remote task environment.
    """
    try:
        payload = json.loads(inputs_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"Could not read generated WDL inputs JSON: {inputs_path}") from exc

    uploaded: dict[str, dict[str, Any]] = {}
    cromwell_path_by_source: dict[Path, str] = {}

    def rewrite(value: Any) -> Any:
        if isinstance(value, dict):
            return {key: rewrite(item) for key, item in value.items()}
        if isinstance(value, list):
            return [rewrite(item) for item in value]
        if not isinstance(value, str) or not value.strip():
            return value
        candidate = Path(value).expanduser()
        if not candidate.is_file():
            return value
        source = candidate.resolve()
        if source in cromwell_path_by_source:
            return cromwell_path_by_source[source]
        digest = _sha256(source)
        object_key = _object_key(source, pipeline_name, run_id, digest)
        uri = uploader.upload(source, object_key)
        cromwell_path = (
            uploader.cromwell_path(uri, object_key)
            if hasattr(uploader, "cromwell_path")
            else uri
        )
        cromwell_path_by_source[source] = cromwell_path
        uploaded[str(source)] = {
            "uri": uri,
            "cromwell_path": cromwell_path,
            "size": source.stat().st_size,
            "sha256": digest,
        }
        return cromwell_path

    rewritten = rewrite(payload)
    inputs_path.write_text(json.dumps(rewritten, indent=2) + "\n", encoding="utf-8")
    return list(uploaded.values())


def write_upload_manifest(
    path: Path,
    uploader: InputUploader,
    uploaded: list[dict[str, Any]],
) -> None:
    path.write_text(
        json.dumps(
            {"backend": uploader.backend, "base_uri": uploader.base_uri, "uploaded": uploaded},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


__all__ = [
    "InputUploader",
    "S3InputUploader",
    "upload_local_file_values",
    "write_upload_manifest",
]
