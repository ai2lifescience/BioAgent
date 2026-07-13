"""Artifact conventions, session workspaces, and artifact storage."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import re
from typing import Any
from uuid import uuid4

from .memory import AgentSession, InMemoryStateStore


DEFAULT_RUNS_DIR = os.getenv("BIOAGENT_RUNS_DIR", "runtime/runs")
DEFAULT_SESSIONS_DIR = os.getenv("BIOAGENT_SESSIONS_DIR", "runtime/sessions")
DEFAULT_MAX_SESSION_ARTIFACTS = 100
PROJECT_ROOT = Path(__file__).resolve().parents[1]


ARTIFACT_KIND_BY_KEY = {
    "fasta_path": "fasta",
    "fasta_paths": "fasta",
    "structure_path": "structure",
    "structure_paths": "structure",
    "metadata_path": "metadata",
    "metadata_paths": "metadata",
    "report_path": "report",
    "image_path": "image",
    "image_paths": "image",
    "genome_map_path": "image",
    "session_input_path": "input",
    "upload_path": "upload",
    "runner_config_path": "config",
    "raw_config_path": "config",
    "config_path": "config",
    "metrics_path": "metrics",
    "output_dir": "directory",
}

ARTIFACT_KIND_BY_SUFFIX = {
    ".fa": "fasta",
    ".faa": "fasta",
    ".fasta": "fasta",
    ".fna": "fasta",
    ".fq": "sequence",
    ".fastq": "sequence",
    ".sam": "sequence_alignment",
    ".bam": "sequence_alignment",
    ".bai": "sequence_alignment_index",
    ".bed": "genomic_interval",
    ".vcf": "variant",
    ".gz": "compressed",
    ".bgz": "compressed",
    ".zip": "compressed",
    ".bcif": "structure",
    ".cif": "structure",
    ".mmcif": "structure",
    ".pdb": "structure",
    ".csv": "metadata",
    ".tsv": "metadata",
    ".md": "report",
    ".markdown": "report",
    ".svg": "image",
    ".json": "config",
    ".yaml": "config",
    ".yml": "config",
    ".txt": "text",
    ".log": "text",
}

SUFFIX_ARTIFACT_KEYS = {
    "",
    "artifact",
    "artifacts",
    "created_file",
    "created_files",
    "file",
    "files",
    "path",
    "paths",
}

ARTIFACT_CONTENT_TYPES = {
    ".bcif": "application/octet-stream",
    ".cif": "chemical/x-mmcif; charset=utf-8",
    ".mmcif": "chemical/x-mmcif; charset=utf-8",
    ".pdb": "chemical/x-pdb; charset=utf-8",
    ".svg": "image/svg+xml; charset=utf-8",
    ".csv": "text/csv; charset=utf-8",
    ".tsv": "text/tab-separated-values; charset=utf-8",
    ".fa": "text/plain; charset=utf-8",
    ".faa": "text/plain; charset=utf-8",
    ".fasta": "text/plain; charset=utf-8",
    ".fna": "text/plain; charset=utf-8",
    ".fq": "text/plain; charset=utf-8",
    ".fastq": "text/plain; charset=utf-8",
    ".sam": "text/plain; charset=utf-8",
    ".bam": "application/octet-stream",
    ".bai": "application/octet-stream",
    ".bed": "text/plain; charset=utf-8",
    ".vcf": "text/plain; charset=utf-8",
    ".gz": "application/gzip",
    ".bgz": "application/gzip",
    ".zip": "application/zip",
    ".md": "text/markdown; charset=utf-8",
    ".markdown": "text/markdown; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".yaml": "text/yaml; charset=utf-8",
    ".yml": "text/yaml; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
    ".log": "text/plain; charset=utf-8",
}

STRUCTURE_ARTIFACT_SUFFIXES = tuple(
    suffix for suffix, kind in ARTIFACT_KIND_BY_SUFFIX.items() if kind == "structure"
)
STRUCTURE_VIEWER_SUFFIXES = (".cif", ".mmcif", ".pdb")
IMAGE_ARTIFACT_SUFFIXES = tuple(
    suffix for suffix, kind in ARTIFACT_KIND_BY_SUFFIX.items() if kind == "image"
)
SERVABLE_ARTIFACT_SUFFIXES = tuple(sorted(ARTIFACT_CONTENT_TYPES))

RESULT_COUNT_KEYS = (
    "matched_count",
    "downloaded_count",
    "record_count",
    "source_count",
    "chunk_count",
    "citation_count",
    "hit_count",
    "atom_count",
    "chain_count",
    "residue_count",
    "ligand_count",
    "model_count",
    "genome_length",
    "feature_count",
    "gene_count",
    "cds_count",
    "orf_count",
    "bytes",
    "returncode",
)
RESULT_ID_KEYS = ("collection_name", "rid", "pdb_id", "file_format")
RESULT_PATH_KEYS = tuple(ARTIFACT_KIND_BY_KEY)
COMPACT_RESULT_KEYS = (
    "tool",
    "status",
    "summary",
    "needs_input",
    "pipeline_name",
    "requested_inputs",
    "output_records",
    "config_overrides",
    "staged_config_paths",
    *RESULT_COUNT_KEYS,
    *RESULT_ID_KEYS,
    *RESULT_PATH_KEYS,
)


def artifact_kind(path: str, key: str = "") -> str | None:
    """Return the artifact kind for an output key/path pair."""
    if "://" in path:
        return None
    if key in ARTIFACT_KIND_BY_KEY:
        return ARTIFACT_KIND_BY_KEY[key]
    if key not in SUFFIX_ARTIFACT_KEYS:
        return None
    return ARTIFACT_KIND_BY_SUFFIX.get(Path(path).suffix.lower())


def collect_artifact_candidates(value: Any) -> list[dict[str, str]]:
    """Find output values that should be tracked as session artifacts."""
    candidates: list[dict[str, str]] = []

    def visit(item: Any, key: str = "") -> None:
        if isinstance(item, dict):
            for subkey, subitem in item.items():
                visit(subitem, str(subkey))
            return
        if isinstance(item, list):
            for subitem in item:
                visit(subitem, key)
            return
        if not isinstance(item, str) or not item.strip():
            return
        kind = artifact_kind(item, key)
        if kind:
            candidates.append({"path": item, "kind": kind, "key": key})

    visit(value)
    return candidates


def collect_output_paths(value: Any) -> list[str]:
    """Collect path-like output values for evidence summaries."""
    paths: list[str] = []

    def append(path: str) -> None:
        if path and path not in paths:
            paths.append(path)

    def visit(item: Any, key: str = "") -> None:
        if isinstance(item, dict):
            for subkey, subitem in item.items():
                visit(subitem, str(subkey))
            return
        if isinstance(item, list):
            for subitem in item:
                visit(subitem, key)
            return
        if not isinstance(item, str):
            return
        if key.endswith("_path") or key.endswith("_paths") or key == "output_dir":
            append(item)

    visit(value)
    return paths


def artifact_content_type(path: str | Path) -> str:
    """Return the HTTP content type for a known artifact path."""
    suffix = Path(path).suffix.lower()
    return ARTIFACT_CONTENT_TYPES.get(suffix, "application/octet-stream")


def is_structure_artifact(path: str | Path) -> bool:
    return Path(path).suffix.lower() in STRUCTURE_ARTIFACT_SUFFIXES


def can_view_structure_artifact(path: str | Path) -> bool:
    return Path(path).suffix.lower() in STRUCTURE_VIEWER_SUFFIXES


def can_serve_artifact(path: str | Path) -> bool:
    return Path(path).suffix.lower() in SERVABLE_ARTIFACT_SUFFIXES


def artifact_suffix_config() -> dict[str, list[str]]:
    return {
        "servable_suffixes": list(SERVABLE_ARTIFACT_SUFFIXES),
        "structure_artifact_suffixes": list(STRUCTURE_ARTIFACT_SUFFIXES),
        "structure_suffixes": list(STRUCTURE_VIEWER_SUFFIXES),
        "image_suffixes": list(IMAGE_ARTIFACT_SUFFIXES),
    }


def allowed_artifact_suffix_message() -> str:
    return "viewable artifact suffixes: " + ", ".join(SERVABLE_ARTIFACT_SUFFIXES)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_path_component(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._")
    return safe or "session"


def _safe_filename(value: str) -> str:
    name = Path(value or "upload").name
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("._")
    return safe or "upload.bin"


def _unique_upload_path(upload_dir: Path, safe_name: str) -> Path:
    candidate = upload_dir / safe_name
    if not candidate.exists():
        return candidate

    path = Path(safe_name)
    stem = path.stem or "upload"
    suffix = path.suffix
    for index in range(2, 1000):
        candidate = upload_dir / f"{stem}_{index}{suffix}"
        if not candidate.exists():
            return candidate
    return upload_dir / f"{stem}_{uuid4().hex[:8]}{suffix}"


def _project_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate.resolve()
    return (PROJECT_ROOT / candidate).resolve()


def _display_path(path: str | Path) -> str:
    resolved = _project_path(path)
    try:
        return str(resolved.relative_to(PROJECT_ROOT.resolve()))
    except ValueError:
        return str(resolved)


class SessionArtifactStore:
    """Manage per-run workspaces and reusable artifacts for chat sessions."""

    def __init__(
        self,
        state_store: InMemoryStateStore,
        runs_dir: str | Path = DEFAULT_RUNS_DIR,
        sessions_dir: str | Path = DEFAULT_SESSIONS_DIR,
        max_session_artifacts: int = DEFAULT_MAX_SESSION_ARTIFACTS,
    ) -> None:
        self.state_store = state_store
        self.runs_dir = Path(runs_dir)
        self.sessions_dir = Path(sessions_dir)
        self.max_session_artifacts = max(1, int(max_session_artifacts))

    def prepare_run(self, session: AgentSession) -> dict[str, Any]:
        """Create run metadata without eagerly creating directories."""
        run_id = str(uuid4())
        runtime_dir = self.runs_dir / run_id
        session_dir = self.sessions_dir / _safe_path_component(session.session_id)
        artifact_dir = session_dir / "artifacts"
        session.metadata.setdefault("artifacts", [])
        session.metadata["run"] = {
            "run_id": run_id,
            "runtime_dir": str(runtime_dir),
            "session_dir": str(session_dir),
            "artifact_dir": str(artifact_dir),
        }
        return dict(session.metadata["run"])

    @staticmethod
    def user_context(session: AgentSession) -> dict[str, Any]:
        """Return the runtime context passed from a skill to its tools."""
        run = dict(session.metadata.get("run") or {})
        return {
            "session_id": session.session_id,
            "artifacts": list(session.metadata.get("artifacts") or []),
            **run,
        }

    def register_result(self, session: AgentSession, record: dict[str, Any]) -> None:
        """Register file-like values produced by one skill and its tools."""
        candidates: list[dict[str, str]] = []
        result = record.get("result")
        if isinstance(result, dict):
            candidates.extend(collect_artifact_candidates(result))
        for tool_call in record.get("tool_calls") or []:
            if not isinstance(tool_call, dict):
                continue
            tool_result = tool_call.get("result")
            if isinstance(tool_result, dict):
                candidates.extend(collect_artifact_candidates(tool_result))

        if not candidates:
            return

        artifacts = list(session.metadata.get("artifacts") or [])
        known_paths = {str(item.get("path")) for item in artifacts if isinstance(item, dict)}
        run = session.metadata.get("run") or {}
        for candidate in candidates:
            path = candidate["path"]
            if path in known_paths:
                continue
            known_paths.add(path)
            artifacts.append(
                {
                    "id": f"artifact_{len(artifacts) + 1}",
                    "kind": candidate["kind"],
                    "path": path,
                    "source_key": candidate["key"],
                    "source_skill": record.get("skill"),
                    "run_id": run.get("run_id"),
                    "label": Path(path).name,
                }
            )

        session.metadata["artifacts"] = artifacts[-self.max_session_artifacts :]

    @staticmethod
    def for_run(session: AgentSession, run_id: str | None) -> list[dict[str, Any]]:
        """Return artifacts associated with one run."""
        artifacts = [
            dict(item)
            for item in session.metadata.get("artifacts") or []
            if isinstance(item, dict)
        ]
        if not run_id:
            return artifacts
        return [item for item in artifacts if item.get("run_id") == run_id]

    def store_upload(
        self,
        session_id: str | None,
        filename: str,
        data: bytes,
        content_type: str = "",
    ) -> dict[str, Any]:
        """Store one uploaded user file as an immutable session artifact."""
        if not data:
            raise ValueError("Uploaded file is empty.")

        with self.state_store.locked_session(
            session_id=session_id,
            user_request="",
        ) as (session, _created):
            upload_id = f"upload_{uuid4().hex[:12]}"
            session_dir = self.sessions_dir / _safe_path_component(session.session_id)
            upload_dir = _project_path(session_dir / "artifacts" / "uploads")
            upload_dir.mkdir(parents=True, exist_ok=True)

            safe_name = _safe_filename(filename)
            file_path = _unique_upload_path(upload_dir, safe_name)
            file_path.write_bytes(data)

            artifact = {
                "id": f"artifact_{len(session.metadata.get('artifacts') or []) + 1}",
                "kind": "upload",
                "path": _display_path(file_path),
                "source_key": "upload_path",
                "source_skill": "web_upload",
                "run_id": None,
                "label": filename or safe_name,
                "upload_id": upload_id,
                "filename": filename or safe_name,
                "safe_filename": file_path.name,
                "size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "content_type": content_type,
            }

            artifacts = list(session.metadata.get("artifacts") or [])
            artifacts.append(artifact)
            session.metadata["artifacts"] = artifacts[-self.max_session_artifacts :]
            session.updated_at = _now()
            return {**artifact, "session_id": session.session_id}

    def list_uploads(self, session_id: str | None) -> dict[str, Any]:
        """Return uploaded artifacts for one session."""
        clean_session_id = str(session_id or "").strip()
        if not clean_session_id:
            return {"session_id": None, "uploads": []}
        session = self.state_store.get_session(clean_session_id)
        if session is None:
            return {"session_id": clean_session_id, "uploads": []}
        with self.state_store.session_lock(clean_session_id):
            session = self.state_store.get_session(clean_session_id)
            if session is None:
                return {"session_id": clean_session_id, "uploads": []}
            uploads = [
                dict(item)
                for item in session.metadata.get("artifacts") or []
                if isinstance(item, dict) and item.get("kind") == "upload"
            ]
        return {"session_id": clean_session_id, "uploads": uploads}

    def delete_upload(self, session_id: str, upload_id_or_artifact_id: str) -> bool:
        """Delete one uploaded artifact from session metadata and disk."""
        clean_session_id = str(session_id or "").strip()
        identifier = str(upload_id_or_artifact_id or "").strip()
        if not clean_session_id or not identifier:
            return False
        session = self.state_store.get_session(clean_session_id)
        if session is None:
            return False

        with self.state_store.session_lock(clean_session_id):
            session = self.state_store.get_session(clean_session_id)
            if session is None:
                return False
            artifacts = [
                item
                for item in session.metadata.get("artifacts") or []
                if isinstance(item, dict)
            ]
            target = next(
                (
                    item
                    for item in artifacts
                    if item.get("kind") == "upload"
                    and identifier in {str(item.get("id")), str(item.get("upload_id"))}
                ),
                None,
            )
            if not target:
                return False

            session.metadata["artifacts"] = [item for item in artifacts if item is not target]
            session.updated_at = _now()

            session_dir = self.sessions_dir / _safe_path_component(clean_session_id)
            upload_root = _project_path(session_dir / "artifacts" / "uploads")
            target_path = _project_path(str(target.get("path") or ""))
            try:
                target_path.relative_to(upload_root)
            except ValueError:
                return True

            try:
                if target_path.exists() and target_path.is_file():
                    target_path.unlink()
            except OSError:
                return False
            return True
