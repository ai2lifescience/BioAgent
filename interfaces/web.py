"""Small stdlib HTTP web UI and API for Pipeline2Agent."""

from __future__ import annotations

import argparse
from io import StringIO
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
import re
import sys
from time import perf_counter
import time
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from Bio.PDB import MMCIFParser, PDBIO

from tools.infrastructure.workspace import (
    artifact_content_type,
    artifact_suffix_config,
    can_view_structure_artifact,
)
from interfaces.api import (
    create_session,
    delete_session,
    delete_workspace_file,
    handle_approval,
    enqueue_request,
    enqueue_approval,
    get_run,
    cancel_run,
    get_run_events,
    get_knowledge_job,
    get_knowledge_job_events,
    list_runs,
    list_sessions,
    list_session_messages,
    list_workspace_files,
    update_session_metadata,
)
from auth import AuthError, auth_mode, current_principal
from interfaces.auth import authenticated_request, configure_server
from harness.sandbox import relative_file_path, execution_access
from isolation.limits import limits, public_limits
from isolation.files import open_regular
from interfaces.uploads import Uploads, multipart, publish
from models.config import DEFAULT_AGENT_MODEL_KEY, DEFAULT_MAX_TURNS, DEFAULT_MODELS
from tools.infrastructure.pipeline_engine import service as pipeline_service
from harness.jobs import TERMINAL, get_queue
from web_bridge import configure_local_demo, handle_browser
from tools.infrastructure.knowledge.models import TERMINAL_JOB_STATUSES
from tools.infrastructure.workspace.public import public_payload


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIST_DIR = PROJECT_ROOT / "frontend" / "dist"
FRONTEND_ENTRYPOINTS = ("index.html", "assistant.html", "assistant-demo.html")
MAX_UPLOAD_BYTES = int(os.getenv("AGENT_MAX_UPLOAD_BYTES", str(256 * 1024 * 1024)))


def _frontend_asset_path(relative_path: str) -> Path | None:
    """Resolve a built asset without exposing source files or escaping dist."""
    try:
        decoded = unquote(relative_path, errors="strict")
        if (
            not decoded
            or decoded.startswith("/")
            or "\\" in decoded
            or "\x00" in decoded
            or any(part in {".", ".."} for part in decoded.split("/"))
        ):
            return None
        root = FRONTEND_DIST_DIR.resolve()
        candidate = (root / decoded).resolve()
        candidate.relative_to(root)
        return candidate if candidate.is_file() else None
    except (OSError, RuntimeError, UnicodeError, ValueError):
        return None


def _frontend_build_diagnostic() -> str:
    return (
        f"Frontend build is missing or incomplete in {FRONTEND_DIST_DIR}. "
        "From the repository root, run `npm --prefix frontend ci` followed by "
        "`npm --prefix frontend run build`. The JSON API remains available."
    )


def _frontend_content_type(path: Path) -> str:
    # JavaScript's system MIME mapping varies across hosts; modules require a
    # JavaScript MIME type rather than text/plain or application/octet-stream.
    content_type = {
        ".js": "application/javascript",
        ".mjs": "application/javascript",
        ".css": "text/css",
        ".svg": "image/svg+xml",
    }.get(path.suffix.lower()) or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    if content_type.startswith("text/") or content_type in {"application/javascript", "application/json"}:
        return f"{content_type}; charset=utf-8"
    return content_type


def _model_options() -> list[dict[str, str]]:
    return [
        {
            "key": key,
            "label": str(config.get("label", key)),
            "model": str(config.get("model", key)),
            "deployment": str(config.get("deployment", "Unknown")),
            "cost_tier": str(config.get("cost_tier", "Unknown")),
        }
        for key, config in DEFAULT_MODELS.items()
    ]


def _progress_line(start: float, message: str) -> str:
    elapsed = perf_counter() - start
    return f"[{elapsed:0.1f}s] {message}"


def _runtime_info(
    result: dict[str, Any],
    elapsed_seconds: float,
    logs: list[str],
    status: str = "done",
    model_key: str | None = None,
    max_turns: int | None = None,
) -> dict[str, Any]:
    evidence = result.get("evidence") or {}
    trace = result.get("trace") or []
    run = result.get("run") or {}
    last_event = trace[-1] if trace else {}
    tools = evidence.get("tools") or []
    files = evidence.get("files") or []
    return {
        "status": result.get("status", status),
        "elapsed_seconds": round(elapsed_seconds, 2),
        "model_key": model_key,
        "session_id": result.get("session_id"),
        "run_id": run.get("run_id"),
        "runtime_dir": run.get("runtime_dir"),
        "runtime": result.get("runtime", "agents_sdk"),
        "max_turns": max_turns,
        "tools": tools,
        "files": files,
        "file_count": len(files),
        "tool_count": len(tools),
        "trace_count": len(trace),
        "last_event": last_event.get("event"),
        "logs": logs,
    }


def _public_job(job: dict[str, Any]) -> dict[str, Any]:
    """Return queue metadata without the original prompt or host internals."""
    result = {
        key: job.get(key)
        for key in ("run_id", "session_id", "status", "model_key", "max_turns", "created_at", "updated_at", "error", "cancel_requested")
    }
    if job.get("result") is not None:
        result["result"] = public_payload(job["result"])
    if result.get("error"):
        result["error"] = public_payload(result["error"])
    return result


def _public_event(item: dict[str, Any]) -> dict[str, Any]:
    value = dict(item)
    value["payload"] = public_payload(value.get("payload", {}))
    return value


class AgentRequestHandler(BaseHTTPRequestHandler):
    """Browser UI and JSON API handler."""

    server_version = "Pipeline2AgentHTTP/1.1"

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        from web_bridge import response_headers
        for name, value in response_headers(self).items():
            self.send_header(name, value)
        if getattr(self, "_auth_cookie", None):
            self.send_header("Set-Cookie", self._auth_cookie)
        super().end_headers()

    def log_message(self, format: str, *args: Any) -> None:
        return

    @authenticated_request
    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in {"/", "/index.html"}:
            self._send_frontend_page("index.html")
            return
        if path == "/assistant/":
            # Keep relative asset/API URLs working when mounted behind a proxy.
            query = urlparse(self.path).query
            self.send_response(302)
            self.send_header("Location", "../assistant" + (f"?{query}" if query else ""))
            self.end_headers()
            return
        if path in {"/assistant", "/assistant.html"}:
            self._send_frontend_page("assistant.html")
            return
        if path in {"/assistant-demo", "/assistant-demo/", "/assistant-demo.html"}:
            self._send_frontend_page("assistant-demo.html")
            return
        if path == "/favicon.svg" or path.startswith("/static/"):
            asset = _frontend_asset_path(path[1:])
            if asset is None:
                self._send_json({"error": "not found"}, status=404)
            else:
                self._send_file(asset, _frontend_content_type(asset))
            return
        if path == "/health":
            self._send_json({"status": "ok"})
            return
        if path == "/config":
            from isolation import isolated_execution
            from tools.capabilities import describe
            pipelines = pipeline_service.catalog(compact=True)
            self._send_json(
                {
                    "default_model_key": DEFAULT_AGENT_MODEL_KEY,
                    "default_max_turns": DEFAULT_MAX_TURNS,
                    "models": _model_options(),
                    "files": artifact_suffix_config(),
                    "storage_limits": public_limits(),
                    "isolated_execution": isolated_execution(),
                    # Onboarding lists all workflows; execution authorization is
                    # enforced separately by the isolated pipeline broker.
                    "pipelines": pipelines,
                    "capabilities": describe(pipelines),
                }
            )
            return
        if path == "/sessions":
            self._send_json({"sessions": list_sessions()})
            return
        if path.startswith("/runs/"):
            self._handle_run_status(path)
            return
        if path.startswith("/knowledge/jobs/"):
            self._handle_knowledge_job(path)
            return
        if path == "/runs":
            session_id = (parse_qs(urlparse(self.path).query).get("session_id") or [None])[0]
            self._send_json({"runs": [_public_job(item) for item in list_runs(session_id)]})
            return
        if path.startswith("/sessions/") and path.endswith("/messages"):
            self._handle_session_messages(path)
            return
        if path == "/workspace":
            self._handle_workspace()
            return
        if path.startswith("/workspace/uploads/"):
            self._send_json(Uploads(execution_access()).status(path.rsplit("/", 1)[-1]))
            return
        if path == "/workspace/file":
            self._handle_workspace_file()
            return
        self._send_json({"error": "not found"}, status=404)

    @authenticated_request
    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if re.fullmatch(r'/runs/[a-f0-9]{32}/cancel', path):
            self._read_json()
            self._send_json(_public_job(cancel_run(path.split('/')[2])))
            return
        if path == "/sessions":
            self._send_json(create_session(), status=201)
            return
        if path.startswith("/website/"):
            handle_browser(self, path[len("/website/"):])
            return
        if path == '/workspace/pipeline-artifacts/materialize':
            from tools.infrastructure.pipeline_engine.broker import materialize
            body = self._read_json(); access = execution_access()
            file = materialize(access.workspace(body.get('session_id', '')), body.get('path', ''), access=access)
            self._send_json({'session_id': body['session_id'], 'files': [file]})
            return
        if path == "/workspace/uploads":
            body = self._read_json()
            row = Uploads(execution_access()).create(body.get('session_id', ''), body.get('filename', ''), body.get('size', 0))
            self._send_json(row, status=201)
            return
        if path.startswith('/workspace/uploads/') and path.endswith('/complete'):
            file = Uploads(execution_access()).complete(path.split('/')[-2])
            self._send_json({'session_id': file['session_id'], 'files': [file]})
            return
        if path == "/workspace/files":
            self._handle_workspace_upload()
            return
        if path == "/run_stream":
            self._handle_run_stream()
            return
        if path == "/approve":
            self._handle_approval()
            return
        if path in {"/approve_stream", "/approve_async"}:
            self._handle_approval_stream(stream=path == "/approve_stream")
            return
        if path != "/run":
            self._send_json({"error": "not found"}, status=404)
            return

        self._handle_run()

    @authenticated_request
    def do_PATCH(self) -> None:
        path = urlparse(self.path).path
        if path.startswith('/workspace/uploads/'):
            row = Uploads(execution_access()).append(path.rsplit('/', 1)[-1],
                int(self.headers.get('Upload-Offset', '-1')), self.rfile,
                int(self.headers.get('Content-Length', '0')))
            self._send_json(row)
            return
        prefix = "/sessions/"
        if not path.startswith(prefix):
            self._send_json({"error": "not found"}, status=404)
            return
        session_id = unquote(path[len(prefix):]).strip()
        if not session_id or "/" in session_id:
            self._send_json({"error": "session_id is required"}, status=400)
            return
        try:
            payload = self._read_json()
            title = payload.get("title") if "title" in payload else None
            pinned = payload.get("pinned") if "pinned" in payload else None
            if title is not None and not isinstance(title, str):
                self._send_json({"error": "title must be a string"}, status=400)
                return
            if pinned is not None and type(pinned) is not bool:
                self._send_json({"error": "pinned must be a boolean"}, status=400)
                return
            if title is None and pinned is None:
                self._send_json({"error": "title or pinned is required"}, status=400)
                return
            result = update_session_metadata(session_id, title=title, pinned=pinned)
            self._send_json(result)
        except AuthError:
            raise
        except Exception as exc:
            self._send_json({"error": str(exc), "error_type": type(exc).__name__}, status=400)

    def _handle_approval(self) -> None:
        try:
            payload = self._read_json()
            session_id = str(payload.get("session_id", "")).strip()
            if not session_id:
                self._send_json({"error": "session_id is required"}, status=400)
                return
            approved = payload.get("approved")
            if type(approved) is not bool:
                self._send_json({"error": "approved must be an explicit boolean"}, status=400)
                return
            approval_id = str(payload.get("approval_id", "")).strip() or None
            if not approval_id:
                self._send_json({"error": "approval_id is required"}, status=400)
                return
            logs: list[str] = []
            start = perf_counter()
            result = handle_approval(session_id, approved, approval_id, log_fn=logs.append)
            result["runtime"] = _runtime_info(
                result,
                perf_counter() - start,
                logs,
                model_key=result.get("model_key"),
                max_turns=result.get("max_turns"),
            )
            self._send_json(result)
        except AuthError:
            raise
        except Exception as exc:
            self._send_json({"error": str(exc), "error_type": type(exc).__name__}, status=400)

    def _handle_approval_stream(self, *, stream: bool = True) -> None:
        """Queue a decision; return its durable job or stream the resumed run."""
        try:
            payload = self._read_json()
            session_id = str(payload.get("session_id", "")).strip()
            if not session_id:
                self._send_json({"error": "session_id is required"}, status=400)
                return
            approved = payload.get("approved")
            if type(approved) is not bool:
                self._send_json({"error": "approved must be an explicit boolean"}, status=400)
                return
            approval_id = str(payload.get("approval_id", "")).strip() or None
            if not approval_id:
                self._send_json({"error": "approval_id is required"}, status=400)
                return

            job = enqueue_approval(session_id, approved, approval_id)
            if job is None:
                self._send_json({"error": "No pending approval for this session."}, status=400)
                return
        except ConnectionAbortedError:
            return
        except AuthError:
            raise
        except Exception as exc:
            self._send_json({"error": str(exc), "error_type": type(exc).__name__}, status=400)
            return
        if stream:
            self._stream_run(job["run_id"])
        else:
            self._send_json(_public_job(job), status=202)

    @authenticated_request
    def do_DELETE(self) -> None:
        path = urlparse(self.path).path
        if path.startswith('/workspace/uploads/'):
            Uploads(execution_access()).cancel(path.rsplit('/', 1)[-1])
            self._send_json({'cancelled': True})
            return
        if path.startswith("/workspace/files/"):
            self._handle_delete_workspace_file(path)
            return
        prefix = "/sessions/"
        if not path.startswith(prefix):
            self._send_json({"error": "not found"}, status=404)
            return
        session_id = path[len(prefix):].strip()
        if not session_id:
            self._send_json({"error": "session_id is required"}, status=400)
            return
        deleted = delete_session(session_id)
        self._send_json({"session_id": session_id, "deleted": deleted})

    def _handle_run(self) -> None:
        try:
            payload = self._read_json()
            request = str(payload.get("request", "")).strip()
            if not request:
                self._send_json({"error": "request is required"}, status=400)
                return
            model_key = payload.get("model_key") or DEFAULT_AGENT_MODEL_KEY
            session_id = str(payload.get("session_id") or "").strip() or None
            job = enqueue_request(
                request=request,
                session_id=session_id,
                model_key=model_key,
                max_turns=int(payload.get("max_turns", DEFAULT_MAX_TURNS)),
                website=payload.get("website") if isinstance(payload.get("website"), dict) else None,
            )
            self._send_json(_public_job(job), status=202)
        except AuthError:
            raise
        except Exception as exc:
            self._send_json(
                {
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                },
                status=400,
            )

    def _handle_run_stream(self) -> None:
        try:
            payload = self._read_json()
            request = str(payload.get("request", "")).strip()
            if not request:
                self._send_json({"error": "request is required"}, status=400)
                return

            model_key = payload.get("model_key") or DEFAULT_AGENT_MODEL_KEY
            session_id = str(payload.get("session_id") or "").strip() or None
            job = enqueue_request(
                request=request,
                session_id=session_id,
                model_key=model_key,
                max_turns=int(payload.get("max_turns", DEFAULT_MAX_TURNS)),
                website=payload.get("website") if isinstance(payload.get("website"), dict) else None,
            )
        except ConnectionAbortedError:
            return
        except AuthError:
            raise
        except Exception as exc:
            # Enqueue failures happen before SSE headers are sent. Once the
            # stream is established, _stream_run reports terminal errors itself.
            self._send_json({"error": str(exc), "error_type": type(exc).__name__}, status=400)
            return
        self._stream_run(job["run_id"])

    def _handle_workspace(self) -> None:
        parsed = urlparse(self.path)
        values = parse_qs(parsed.query)
        session_id = (values.get("session_id") or [""])[0].strip() or None
        result = list_workspace_files(session_id)
        files = result.get("files", [])
        self._send_json(
            {
                "session_id": session_id,
                "workspace": {
                    "file_count": len(files),
                    "files": files,
                    "capabilities": ["list", "upload", "read", "download", "delete"],
                },
            }
        )

    def _handle_session_messages(self, path: str) -> None:
        prefix = "/sessions/"
        session_id = unquote(path[len(prefix):-len("/messages")])
        if not session_id:
            self._send_json({"error": "session_id is required"}, status=400)
            return
        try:
            self._send_json(list_session_messages(session_id))
        except ValueError as exc:
            self._send_json({"error": str(exc)}, status=400)

    def _handle_workspace_upload(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0:
                self._send_json({"error": "upload body is required"}, status=400)
                return
            if length > MAX_UPLOAD_BYTES:
                self._send_json(
                    {
                        "error": f"upload is too large; max bytes: {MAX_UPLOAD_BYTES}",
                        "max_upload_bytes": MAX_UPLOAD_BYTES,
                    },
                    status=413,
                )
                return

            access = execution_access()
            boundary = _multipart_boundary(self.headers.get("Content-Type", ""))
            spool = access.metadata_root / '.upload-spool'
            spool.mkdir(mode=0o700, parents=True, exist_ok=True)
            files = []
            from isolation.storage import reserve, release
            reservation = reserve(access, None, length, kind='multipart', seconds=3600)
            try:
                with multipart(self.rfile, length, boundary, spool) as parts:
                    session_id = next((part['path'].read_text().strip() for part in parts
                                       if part['name'] == 'session_id' and part['filename'] is None), '')
                    if not session_id:
                        session_id = create_session()['session_id']
                    access.ownership.require(session_id)
                    for part in parts:
                        if part['filename']:
                            files.append(publish(access, session_id, part['filename'], part['path'], part['size'], reservation=reservation, stable_name=False))
            finally:
                release(access, reservation)

            if not files:
                self._send_json({"error": "no files were uploaded"}, status=400)
                return
            self._send_json({"session_id": session_id, "files": files})
        except AuthError:
            raise
        except Exception as exc:
            self._send_json(
                {
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                },
                status=400,
            )

    def _handle_run_status(self, path: str) -> None:
        parts = path.strip("/").split("/")
        if len(parts) not in {2, 3} or parts[0] != "runs":
            self._send_json({"error": "not found"}, status=404)
            return
        try:
            job = get_run(parts[1])
            if len(parts) == 3 and parts[2] == "events":
                after = int((parse_qs(urlparse(self.path).query).get("after") or ["-1"])[0])
                self._send_json({"run": _public_job(job), "events": [_public_event(item) for item in get_run_events(parts[1], after)]})
            else:
                self._send_json(_public_job(job))
        except (ValueError, TypeError) as exc:
            self._send_json({"error": str(exc)}, status=404)

    def _handle_knowledge_job(self, path: str) -> None:
        parts = path.strip("/").split("/")
        if len(parts) not in {3, 4} or parts[:2] != ["knowledge", "jobs"]:
            self._send_json({"error": "not found"}, status=404)
            return
        query = parse_qs(urlparse(self.path).query)
        session_id = (query.get("session_id") or [""])[0].strip()
        if not session_id:
            self._send_json({"error": "session_id is required"}, status=400)
            return
        job_id = unquote(parts[2]).strip()
        try:
            job = get_knowledge_job(job_id, session_id)
            if len(parts) == 4 and parts[3] == "events":
                after = int((query.get("after") or ["-1"])[0])
                events = get_knowledge_job_events(job_id, session_id, after)
                self._send_json({"job": public_payload(job), "events": [public_payload(item) for item in events]})
            elif len(parts) == 4 and parts[3] == "stream":
                self._stream_knowledge_job(job_id, session_id)
            elif len(parts) == 3:
                self._send_json(public_payload(job))
            else:
                self._send_json({"error": "not found"}, status=404)
        except (ValueError, TypeError) as exc:
            self._send_json({"error": str(exc)}, status=404)

    def _stream_knowledge_job(self, job_id: str, session_id: str) -> None:
        self._send_stream_headers()
        sequence = -1
        heartbeat_at = time.monotonic()
        while True:
            for item in get_knowledge_job_events(job_id, session_id, sequence):
                sequence = item["sequence"]
                if not self._send_stream_event(item["event"], public_payload(item["payload"])):
                    return
            job = get_knowledge_job(job_id, session_id)
            if job["status"] in TERMINAL_JOB_STATUSES:
                self._send_stream_event("result", public_payload(job))
                return
            if time.monotonic() - heartbeat_at >= 15:
                if not self._send_stream_event("heartbeat", {"job_id": job_id}):
                    return
                heartbeat_at = time.monotonic()
            time.sleep(0.25)

    def _stream_run(self, run_id: str) -> None:
        self._send_stream_headers()
        sequence = -1
        heartbeat_at = time.monotonic()
        while True:
            for item in get_run_events(run_id, sequence):
                sequence = item["sequence"]
                if not self._send_stream_event(item["event"], public_payload(item["payload"])):
                    return
            job = get_run(run_id)
            if job["status"] in TERMINAL:
                if job.get("result"):
                    payload = dict(job["result"])
                    payload["job_id"] = run_id
                    payload["run_status"] = job["status"]
                    payload.setdefault("runtime", {})
                    if isinstance(payload["runtime"], dict):
                        payload["runtime"].update({"job_id": run_id, "status": job["status"]})
                    if not self._send_stream_event("result", payload):
                        return
                else:
                    self._send_stream_event("error", {"error": job.get("error") or "Agent run failed.", "run_id": run_id})
                return
            if time.monotonic() - heartbeat_at >= 15:
                if not self._send_stream_event("heartbeat", {"run_id": run_id}):
                    return
                heartbeat_at = time.monotonic()
            time.sleep(0.25)


    def _handle_delete_workspace_file(self, path: str) -> None:
        workspace_path = unquote(path[len("/workspace/files/"):]).strip()
        if not workspace_path:
            self._send_json({"error": "workspace file path is required"}, status=400)
            return
        values = parse_qs(urlparse(self.path).query)
        session_id = (values.get("session_id") or [""])[0].strip()
        if not session_id:
            self._send_json({"error": "session_id is required"}, status=400)
            return
        deleted = delete_workspace_file(session_id, workspace_path)
        self._send_json({"session_id": session_id, "path": workspace_path, "deleted": deleted})

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length < 0 or length > 1024 * 1024:
            raise ValueError("JSON request body is too large.")
        raw = self.rfile.read(length)
        if not raw:
            return {}
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("JSON request body must be an object.")
        return payload

    def _handle_workspace_file(self) -> None:
        parsed = urlparse(self.path)
        values = parse_qs(parsed.query)
        requested_path = (values.get("path") or [""])[0].strip()
        session_id = (values.get("session_id") or [""])[0].strip()
        viewer_format = (values.get("viewer") or [""])[0].strip().lower()
        if not session_id:
            self._send_json({"error": "session_id is required"}, status=400)
            return
        try:
            file_path = relative_file_path(requested_path)
        except ValueError as exc:
            self._send_json({"error": str(exc)}, status=400)
            return
        access = execution_access()
        access.ownership.require(session_id)
        root = access.workspace(session_id)
        if file_path.parts[0] == 'pipeline-bundles':
            from tools.infrastructure.pipeline_engine.broker import bundle_stream
            if len(file_path.parts) != 3 or file_path.name != 'results.zip': raise ValueError('Invalid bundle path.')
            with bundle_stream(root, file_path.parts[1], access=access) as stream:
                self._stream_file(stream, 'application/zip')
            return
        if file_path.parts[0] == 'pipeline-artifacts':
            from tools.infrastructure.pipeline_engine.broker import remote_stream
            requested = self.headers.get('Range')
            if requested and not re.fullmatch(r'bytes=\d*-\d*', requested):
                self._send_json({'error': 'Only one byte range is supported.'}, status=416)
                return
            started = False
            try:
                with remote_stream(root, file_path.as_posix(), access=access, byte_range=requested) as (response, item):
                    started = True
                    self.send_response(206 if requested else 200)
                    self.send_header('Content-Type', artifact_content_type(file_path))
                    self.send_header('Content-Length', str(response['ContentLength']))
                    self.send_header('Accept-Ranges', 'bytes')
                    if response.get('ContentRange'): self.send_header('Content-Range', response['ContentRange'])
                    if artifact_content_type(file_path).startswith('text/html'):
                        self.send_header('Content-Security-Policy', "sandbox; default-src 'none'; img-src data:; style-src 'unsafe-inline'")
                    self.end_headers()
                    try:
                        while chunk := response['Body'].read(1024 * 1024): self.wfile.write(chunk)
                    except (BrokenPipeError, ConnectionResetError): pass
            except AuthError:
                raise
            except Exception as exc:
                if started:
                    self.close_connection = True
                elif isinstance(exc, ValueError):
                    self._send_json({'error': str(exc)}, status=416 if requested else 400)
                else:
                    self._send_json({'error': 'Remote artifact is temporarily unavailable.'}, status=502)
            return
        if viewer_format != 'pdb':
            try:
                with open_regular(root, file_path.as_posix()) as stream:
                    self._stream_file(stream, artifact_content_type(file_path), sandbox_html=True)
            except (FileNotFoundError, OSError, ValueError):
                self._send_json({'error': 'File not found.'}, status=404)
            return
        with open_regular(root, file_path.as_posix()) as stream:
            if os.fstat(stream.fileno()).st_size > 32 * 1024 * 1024:
                self._send_json({'error': 'Structure is too large for this viewer; download the original file.'}, status=413)
                return
            data = stream.read()
        if viewer_format == "pdb":
            if not can_view_structure_artifact(file_path):
                self._send_json({"error": "viewer=pdb is only available for structure artifacts"}, status=400)
                return
            try:
                self._send_text(_structure_viewer_pdb_text(data, file_path), "chemical/x-pdb; charset=utf-8")
            except AuthError:
                raise
            except Exception as exc:
                self._send_json({"error": str(exc), "error_type": type(exc).__name__}, status=500)
            return
        self._send_bytes(
            data,
            artifact_content_type(file_path),
            sandbox_html=True,
        )

    def _send_frontend_page(self, filename: str) -> None:
        page = _frontend_asset_path(filename)
        if page is None:
            self._send_text(_frontend_build_diagnostic(), "text/plain; charset=utf-8", status=503)
            return
        self._send_file(page, "text/html; charset=utf-8")

    def _send_file(
        self,
        path: Path,
        content_type: str,
        status: int = 200,
        sandbox_html: bool = False,
    ) -> None:
        if not path.exists() or not path.is_file():
            self._send_json({"error": "not found"}, status=404)
            return
        with path.open('rb') as stream:
            self._stream_file(stream, content_type, sandbox_html=sandbox_html, status=status)

    def _stream_file(self, stream, content_type, *, sandbox_html=False, status=200):
        size = os.fstat(stream.fileno()).st_size
        start, end = 0, size - 1
        requested = self.headers.get('Range')
        if requested:
            match = re.fullmatch(r'bytes=(\d*)-(\d*)', requested)
            try:
                if not match or not any(match.groups()) or not size: raise ValueError()
                left, right = match.groups()
                if left:
                    start = int(left); end = min(int(right), size - 1) if right else size - 1
                else:
                    count = int(right)
                    if count <= 0: raise ValueError()
                    start = max(0, size - count)
                if start > end or start >= size: raise ValueError()
            except ValueError:
                self.send_response(416)
                self.send_header('Content-Range', f'bytes */{size}')
                self.send_header('Content-Length', '0'); self.end_headers()
                return
            status = 206
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Accept-Ranges', 'bytes')
        if status == 206: self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
        if sandbox_html and content_type.startswith('text/html'):
            self.send_header('Content-Security-Policy', "sandbox; default-src 'none'; img-src data:; style-src 'unsafe-inline'")
        self.send_header('Content-Length', str(max(0, end - start + 1)))
        self.end_headers()
        stream.seek(start)
        remaining = max(0, end - start + 1)
        try:
            while remaining:
                chunk = stream.read(min(1024 * 1024, remaining))
                if not chunk: break
                self.wfile.write(chunk); remaining -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _send_bytes(
        self, data: bytes, content_type: str, status: int = 200, sandbox_html: bool = False,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        if sandbox_html and content_type.startswith("text/html"):
            self.send_header(
                "Content-Security-Policy",
                "sandbox; default-src 'none'; img-src data:; style-src 'unsafe-inline'",
            )
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            return

    def _send_text(self, text: str, content_type: str, status: int = 200) -> None:
        data = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            return

    def _send_stream_headers(self) -> None:
        self._streaming = True
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

    def _send_stream_event(self, event: str, payload: dict[str, Any]) -> bool:
        data = json.dumps(payload, ensure_ascii=False)
        frame = f"event: {event}\ndata: {data}\n\n".encode("utf-8")
        try:
            self.wfile.write(frame)
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            return False
        return True

    def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            return


def run_server(host: str = "127.0.0.1", port: int = 8000) -> None:
    configure_server(host)
    if any(_frontend_asset_path(filename) is None for filename in FRONTEND_ENTRYPOINTS):
        print(_frontend_build_diagnostic(), file=sys.stderr)
    get_queue().recover()
    server = ThreadingHTTPServer((host, port), AgentRequestHandler)
    if auth_mode() == "local":
        configure_local_demo(server.server_port, server.server_address[0])
    print(f"Pipeline2Agent web UI running at http://{host}:{server.server_port}")
    print(f"Access mode: {auth_mode()}", flush=True)
    from isolation import isolated_execution, start_worker_reaper
    reaper = start_worker_reaper(execution_access().metadata_root) if isolated_execution() else None
    from tools.infrastructure.pipeline_engine.broker import start_reconciler
    reconciler = start_reconciler(execution_access().metadata_root) if isolated_execution() else None
    try:
        server.serve_forever()
    finally:
        if reaper:
            reaper.set()
        if reconciler:
            reconciler.set()
        server.server_close()


def _structure_viewer_pdb_text(data: bytes, path: Path) -> str:
    if path.suffix.lower() == ".pdb":
        return data.decode("utf-8", errors="replace")
    parser = MMCIFParser(QUIET=True)
    structure = parser.get_structure(path.stem or "structure", StringIO(data.decode("utf-8", errors="replace")))
    writer = PDBIO()
    writer.set_structure(structure)
    output = StringIO()
    writer.save(output)
    return output.getvalue()


def _multipart_boundary(content_type: str) -> bytes:
    match = re.search(r'boundary=(?:"([^"]+)"|([^;]+))', content_type or "", re.IGNORECASE)
    if not match:
        raise ValueError("multipart boundary is missing")
    boundary = (match.group(1) or match.group(2) or "").strip()
    if not boundary:
        raise ValueError("multipart boundary is empty")
    return boundary.encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Pipeline2Agent HTTP web UI.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    run_server(host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
