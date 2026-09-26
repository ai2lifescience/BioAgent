"""Optional object-storage transfer for remote Cromwell inputs and outputs.

The Cromwell REST API receives the WDL and input JSON, but it does not copy
local files referenced by that JSON.  This module uploads local file values to
an S3-compatible bucket and maps them to paths on the Cromwell/task hosts.
Declared outputs are downloaded through the S3 API. BioAgent does not need
the server-side storage mount on its own host. Local miniwdl execution does
not use this transport.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
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


class OutputDownloader(Protocol):
    """Downloader interface used when Cromwell returns remote output paths."""

    backend: str
    base_uri: str

    def download(self, source: str, target: Path) -> bool:
        """Download ``source`` to ``target`` when it belongs to this backend."""


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
        client = _s3_client_from_environment("CROMWELL_INPUT_STORAGE")
        mount_prefix = (
            str(os.environ.get("CROMWELL_INPUT_STORAGE_MOUNT_PREFIX") or "").strip() or None
        )
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
        """Map an uploaded object to Cromwell's server-side storage path."""
        if not self.mount_prefix:
            return uri
        key = "/".join(part for part in (self.prefix, object_key) if part)
        return f"{self.mount_prefix}/{self.bucket}/{key}"


@dataclass
class S3OutputStorage:
    """S3 or S3-compatible output mapper and downloader.

    Cromwell returns the path it saw on its execution host.  The path can be
    translated to the object-storage URI either through the server-side mount path
    or through one of Cromwell's execution-directory prefixes.  This mirrors
    the mapping used by the Mscan backend while keeping output collection
    independent of a client-side shared mount.
    """

    bucket: str
    prefix: str
    client: Any
    mount_prefix: str | None = None
    execution_prefixes: tuple[str, ...] = ()
    downloaded: list[dict[str, Any]] = field(default_factory=list, init=False)

    backend: str = "s3"

    def __post_init__(self) -> None:
        self.prefix = self.prefix.strip("/")
        if self.mount_prefix is not None:
            self.mount_prefix = self.mount_prefix.rstrip("/")
            if not self.mount_prefix.startswith("/"):
                raise ValueError(
                    "CROMWELL_OUTPUT_STORAGE_MOUNT_PREFIX must be an absolute non-root path."
                )
        self.execution_prefixes = tuple(prefix.rstrip("/") for prefix in self.execution_prefixes)
        if any(not prefix.startswith("/") for prefix in self.execution_prefixes):
            raise ValueError(
                "CROMWELL_OUTPUT_STORAGE_EXECUTION_PATH_PREFIXES must contain absolute non-root paths."
            )

    @property
    def base_uri(self) -> str:
        return f"s3://{self.bucket}/{self.prefix}".rstrip("/")

    @classmethod
    def from_environment(cls) -> "S3OutputStorage | None":
        value = str(os.environ.get("CROMWELL_OUTPUT_STORAGE_URI") or "").strip()
        if not value:
            return None
        parsed = urlsplit(value)
        if parsed.scheme.lower() != "s3" or not parsed.netloc:
            raise ValueError(
                "CROMWELL_OUTPUT_STORAGE_URI must be an s3://bucket/prefix URI. "
                "The bucket must contain the outputs written by Cromwell."
            )
        client = _s3_client_from_environment(
            "CROMWELL_OUTPUT_STORAGE",
            fallback_prefix="CROMWELL_INPUT_STORAGE",
        )
        mount_prefix = str(
            os.environ.get("CROMWELL_OUTPUT_STORAGE_MOUNT_PREFIX") or ""
        ).strip() or None
        if mount_prefix is not None and not mount_prefix.startswith("/"):
            raise ValueError("CROMWELL_OUTPUT_STORAGE_MOUNT_PREFIX must be an absolute path.")
        prefixes_value = str(
            os.environ.get("CROMWELL_OUTPUT_STORAGE_EXECUTION_PATH_PREFIXES") or ""
        )
        execution_prefixes = tuple(
            prefix.rstrip("/")
            for prefix in (item.strip() for item in prefixes_value.split(","))
            if prefix
        )
        return cls(
            bucket=parsed.netloc,
            prefix=parsed.path.strip("/"),
            client=client,
            mount_prefix=mount_prefix.rstrip("/") if mount_prefix else None,
            execution_prefixes=execution_prefixes,
        )

    def uri_for_path(self, source: str | Path) -> str | None:
        """Map a Cromwell output path or URI to an S3 URI."""
        value = str(source).strip()
        if not value:
            return None
        parsed = urlsplit(value)
        if parsed.scheme.lower() == "s3" and parsed.netloc:
            candidate = f"s3://{parsed.netloc}/{parsed.path.lstrip('/')}".rstrip("/")
            base = self.base_uri
            if candidate == base or candidate.startswith(base + "/"):
                return candidate
            return None
        if parsed.scheme and parsed.scheme.lower() == "file":
            value = parsed.path
        elif parsed.scheme:
            return None
        normalized = value.rstrip("/")
        candidates: list[tuple[int, str]] = []
        for prefix in (self.mount_prefix, *self.execution_prefixes):
            if not prefix:
                continue
            if normalized == prefix or normalized.startswith(prefix + "/"):
                candidates.append((len(prefix), normalized[len(prefix):].lstrip("/")))
        if not candidates:
            return None
        suffix = max(candidates, key=lambda item: item[0])[1]
        return f"{self.base_uri}/{suffix}".rstrip("/")

    def download(self, source: str, target: Path) -> bool:
        """Download a mapped S3 output, returning false for unrelated paths."""
        uri = self.uri_for_path(source)
        if not uri:
            return False
        parsed = urlsplit(uri)
        if not parsed.path.lstrip("/"):
            raise ValueError(f"Cromwell output must identify an S3 object: {uri}")
        target.parent.mkdir(parents=True, exist_ok=True)
        # Only a completed download becomes a declared artifact. Failed
        # transfers cannot be mistaken for valid outputs on a later attempt.
        with NamedTemporaryFile(
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".part",
            delete=False,
        ) as handle:
            staging = Path(handle.name)
        try:
            self.client.download_file(parsed.netloc, parsed.path.lstrip("/"), str(staging))
            staging.replace(target)
        except Exception as exc:
            raise RuntimeError(f"Could not download Cromwell output {uri}: {exc}") from exc
        finally:
            staging.unlink(missing_ok=True)
        self.downloaded.append({"uri": uri, "path": str(target), "size": target.stat().st_size})
        return True


def _s3_client_from_environment(prefix: str, fallback_prefix: str | None = None) -> Any:
    """Build a boto3 S3 client using a storage prefix and optional fallback."""
    try:
        import boto3  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError(
            f"{prefix}_URI is configured, but boto3 is not installed. "
            "Install the project requirements before using S3 object storage."
        ) from exc

    def setting(name: str) -> str:
        value = str(os.environ.get(f"{prefix}_{name}") or "").strip()
        if value or not fallback_prefix:
            return value
        return str(os.environ.get(f"{fallback_prefix}_{name}") or "").strip()

    endpoint = setting("ENDPOINT") or None
    region = setting("REGION") or None
    # Credentials fall back as a group, never mixing output and input keys.
    credential_prefix = prefix
    if fallback_prefix and not any(
        str(os.environ.get(f"{prefix}_{name}") or "").strip()
        for name in ("ACCESS_KEY", "SECRET_KEY", "SESSION_TOKEN")
    ):
        credential_prefix = fallback_prefix
    access_key = str(os.environ.get(f"{credential_prefix}_ACCESS_KEY") or "").strip()
    secret_key = str(os.environ.get(f"{credential_prefix}_SECRET_KEY") or "").strip()
    session_token = str(os.environ.get(f"{credential_prefix}_SESSION_TOKEN") or "").strip() or None
    credentials = None
    if access_key or secret_key or session_token:
        if not access_key or not secret_key:
            raise ValueError(
                f"{prefix}_ACCESS_KEY and {prefix}_SECRET_KEY must be supplied together."
            )
        credentials = {
            "aws_access_key_id": access_key,
            "aws_secret_access_key": secret_key,
        }
        if session_token:
            credentials["aws_session_token"] = session_token
    from botocore.config import Config  # type: ignore[import-not-found]

    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name=region,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        **(credentials or {}),
    )


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
    "OutputDownloader",
    "S3InputUploader",
    "S3OutputStorage",
    "upload_local_file_values",
    "write_upload_manifest",
]
