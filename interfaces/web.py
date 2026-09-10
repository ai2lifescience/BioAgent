"""Small stdlib HTTP web UI and API for BioAgent."""

from __future__ import annotations

import argparse
from io import StringIO
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
from time import perf_counter
from typing import Any
from urllib.parse import parse_qs, urlparse

from Bio.PDB import MMCIFParser, PDBIO

from agent_core.artifacts import (
    allowed_artifact_suffix_message,
    artifact_content_type,
    artifact_suffix_config,
    can_view_structure_artifact,
    can_serve_artifact,
)
from interfaces.api import (
    delete_session,
    delete_upload,
    handle_request,
    list_sessions,
    list_uploads,
    store_upload,
)
from models.config import DEFAULT_AGENT_MODEL_KEY, DEFAULT_MAX_SKILL_STEPS, DEFAULT_MODELS


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WEB_UI_DIR = PROJECT_ROOT / "web_ui"
MAX_UPLOAD_BYTES = int(os.getenv("BIOAGENT_MAX_UPLOAD_BYTES", str(256 * 1024 * 1024)))
STATIC_FILES = {
    "/static/app.css": (WEB_UI_DIR / "app.css", "text/css; charset=utf-8"),
    "/static/markdown.js": (WEB_UI_DIR / "markdown.js", "application/javascript; charset=utf-8"),
    "/static/app.js": (WEB_UI_DIR / "app.js", "application/javascript; charset=utf-8"),
}


def _model_options() -> list[dict[str, str]]:
    return [
        {
            "key": key,
            "label": str(config.get("label", key)),
            "model": str(config.get("model", key)),
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
) -> dict[str, Any]:
    evidence = result.get("evidence") or {}
    verification = result.get("verification") or {}
    trace = result.get("trace") or []
    run = result.get("run") or {}
    last_event = trace[-1] if trace else {}
    fallback_events = [
        event
        for event in trace
        if event.get("event", "").startswith("model_tool_fallback_")
    ]
    latest_fallback = fallback_events[-1] if fallback_events else {}
    latest_fallback_data = latest_fallback.get("data") or {}
    skills = evidence.get("skills") or []
    tools = evidence.get("tools") or []
    files = evidence.get("files") or []
    return {
        "status": status,
        "elapsed_seconds": round(elapsed_seconds, 2),
        "model_key": model_key,
        "session_id": result.get("session_id"),
        "run_id": run.get("run_id"),
        "runtime_dir": run.get("runtime_dir"),
        "route": (result.get("route") or {}).get("mode"),
        "plan": (result.get("plan") or {}).get("mode"),
        "verification": verification.get("status"),
        "skills": skills,
        "tools": tools,
        "files": files,
        "file_count": len(files),
        "last_event": last_event.get("event"),
        "model_tool_fallback": {
            "used": bool(fallback_events),
            "status": latest_fallback.get("event"),
            "reason": latest_fallback_data.get("reason"),
        },
        "logs": logs,
    }


class BioAgentRequestHandler(BaseHTTPRequestHandler):
    """Browser UI and JSON API handler."""

    server_version = "BioAgentHTTP/1.1"

    def log_message(self, format: str, *args: Any) -> None:
        return

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in {"/", "/index.html"}:
            self._send_file(WEB_UI_DIR / "index.html", "text/html; charset=utf-8")
            return
        if path in STATIC_FILES:
            file_path, content_type = STATIC_FILES[path]
            self._send_file(file_path, content_type)
            return
        if path == "/health":
            self._send_json({"status": "ok"})
            return
        if path == "/config":
            self._send_json(
                {
                    "default_model_key": DEFAULT_AGENT_MODEL_KEY,
                    "default_max_skill_steps": DEFAULT_MAX_SKILL_STEPS,
                    "models": _model_options(),
                    "artifacts": artifact_suffix_config(),
                }
            )
            return
        if path == "/sessions":
            self._send_json({"sessions": list_sessions()})
            return
        if path == "/uploads":
            self._handle_uploads()
            return
        if path == "/artifact":
            self._handle_artifact()
            return
        self._send_json({"error": "not found"}, status=404)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/upload":
            self._handle_upload()
            return
        if path == "/run_stream":
            self._handle_run_stream()
            return
        if path != "/run":
            self._send_json({"error": "not found"}, status=404)
            return

        self._handle_run()

    def do_DELETE(self) -> None:
        path = urlparse(self.path).path
        if path.startswith("/uploads/"):
            self._handle_delete_upload(path)
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
            logs: list[str] = []
            start = perf_counter()
            model_key = payload.get("model_key") or DEFAULT_AGENT_MODEL_KEY
            session_id = str(payload.get("session_id") or "").strip() or None

            def log_progress(message: str) -> None:
                logs.append(_progress_line(start, message))

            result = handle_request(
                request=request,
                session_id=session_id,
                model_key=model_key,
                max_skill_steps=int(payload.get("max_skill_steps", DEFAULT_MAX_SKILL_STEPS)),
                log_fn=log_progress,
            )
            result["runtime"] = _runtime_info(
                result=result,
                elapsed_seconds=perf_counter() - start,
                logs=logs,
                model_key=model_key,
            )
            self._send_json(result)
        except Exception as exc:
            runtime = {
                "status": "error",
                "elapsed_seconds": 0,
                "logs": [],
            }
            if "start" in locals():
                runtime["elapsed_seconds"] = round(perf_counter() - start, 2)
            if "logs" in locals():
                runtime["logs"] = logs[-30:]
            self._send_json(
                {
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "runtime": runtime,
                },
                status=500,
            )

    def _handle_run_stream(self) -> None:
        try:
            payload = self._read_json()
            request = str(payload.get("request", "")).strip()
            if not request:
                self._send_json({"error": "request is required"}, status=400)
                return

            self._send_stream_headers()
            logs: list[str] = []
            start = perf_counter()
            model_key = payload.get("model_key") or DEFAULT_AGENT_MODEL_KEY
            session_id = str(payload.get("session_id") or "").strip() or None

            def log_stream(message: str) -> None:
                line = _progress_line(start, message)
                logs.append(line)
                if not self._send_stream_event("log", {"message": line}):
                    raise ConnectionAbortedError("Client disconnected from runtime stream.")

            self._send_stream_event(
                "status",
                {
                    "message": "Agent request started.",
                    "model_key": model_key,
                    "session_id": session_id,
                    "max_skill_steps": int(payload.get("max_skill_steps", DEFAULT_MAX_SKILL_STEPS)),
                },
            )
            result = handle_request(
                request=request,
                session_id=session_id,
                model_key=model_key,
                max_skill_steps=int(payload.get("max_skill_steps", DEFAULT_MAX_SKILL_STEPS)),
                log_fn=log_stream,
            )
            result["runtime"] = _runtime_info(
                result=result,
                elapsed_seconds=perf_counter() - start,
                logs=logs,
                model_key=model_key,
            )
            self._send_stream_event("result", result)
        except ConnectionAbortedError:
            return
        except Exception as exc:
            runtime = {
                "status": "error",
                "elapsed_seconds": 0,
                "logs": [],
            }
            if "start" in locals():
                runtime["elapsed_seconds"] = round(perf_counter() - start, 2)
            if "logs" in locals():
                runtime["logs"] = logs
            if "model_key" in locals():
                runtime["model_key"] = model_key
            self._send_stream_event(
                "error",
                {
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "runtime": runtime,
                },
            )

    def _handle_uploads(self) -> None:
        parsed = urlparse(self.path)
        values = parse_qs(parsed.query)
        session_id = (values.get("session_id") or [""])[0].strip() or None
        self._send_json(list_uploads(session_id))

    def _handle_upload(self) -> None:
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

            raw = self.rfile.read(length)
            boundary = _multipart_boundary(self.headers.get("Content-Type", ""))
            parts = _parse_multipart(raw, boundary)
            session_id = ""
            uploads: list[dict[str, Any]] = []

            for part in parts:
                if part.get("name") == "session_id" and not part.get("filename"):
                    session_id = part["data"].decode("utf-8", errors="replace").strip()
                    break

            for part in parts:
                filename = str(part.get("filename") or "").strip()
                if not filename:
                    continue
                artifact = store_upload(
                    session_id=session_id or None,
                    filename=filename,
                    data=part["data"],
                    content_type=str(part.get("content_type") or ""),
                )
                session_id = str(artifact.get("session_id") or session_id)
                uploads.append(artifact)

            if not uploads:
                self._send_json({"error": "no files were uploaded"}, status=400)
                return
            self._send_json({"session_id": session_id, "uploads": uploads})
        except Exception as exc:
            self._send_json(
                {
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                },
                status=400,
            )

    def _handle_delete_upload(self, path: str) -> None:
        artifact_id = path[len("/uploads/"):].strip()
        if not artifact_id:
            self._send_json({"error": "upload artifact id is required"}, status=400)
            return
        values = parse_qs(urlparse(self.path).query)
        session_id = (values.get("session_id") or [""])[0].strip()
        if not session_id:
            self._send_json({"error": "session_id is required"}, status=400)
            return
        deleted = delete_upload(session_id, artifact_id)
        self._send_json({"session_id": session_id, "upload_id": artifact_id, "deleted": deleted})

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def _handle_artifact(self) -> None:
        parsed = urlparse(self.path)
        values = parse_qs(parsed.query)
        requested_path = (values.get("path") or [""])[0].strip()
        viewer_format = (values.get("viewer") or [""])[0].strip().lower()
        try:
            artifact_path = _resolve_artifact_path(requested_path)
        except ValueError as exc:
            self._send_json({"error": str(exc)}, status=400)
            return
        if not artifact_path.exists() or not artifact_path.is_file():
            self._send_json({"error": "artifact not found"}, status=404)
            return
        if viewer_format == "pdb":
            if not can_view_structure_artifact(artifact_path):
                self._send_json({"error": "viewer=pdb is only available for structure artifacts"}, status=400)
                return
            try:
                self._send_text(_structure_viewer_pdb_text(artifact_path), "chemical/x-pdb; charset=utf-8")
            except Exception as exc:
                self._send_json({"error": str(exc), "error_type": type(exc).__name__}, status=500)
            return
        self._send_file(
            artifact_path,
            artifact_content_type(artifact_path),
            sandbox_html=True,
        )

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
        data = path.read_bytes()
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
    server = ThreadingHTTPServer((host, port), BioAgentRequestHandler)
    print(f"BioAgent web UI running at http://{host}:{port}")
    server.serve_forever()


def _resolve_artifact_path(requested_path: str) -> Path:
    if not requested_path:
        raise ValueError("path is required")
    raw_path = Path(requested_path)
    candidate = raw_path if raw_path.is_absolute() else PROJECT_ROOT / raw_path
    resolved = candidate.resolve()
    try:
        resolved.relative_to(PROJECT_ROOT)
    except ValueError as exc:
        raise ValueError("artifact path must be inside the BioAgent project") from exc
    if not can_serve_artifact(resolved):
        raise ValueError(allowed_artifact_suffix_message())
    return resolved


def _structure_viewer_pdb_text(path: Path) -> str:
    if path.suffix.lower() == ".pdb":
        return path.read_text(encoding="utf-8", errors="replace")
    parser = MMCIFParser(QUIET=True)
    structure = parser.get_structure(path.stem or "structure", str(path))
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


def _parse_multipart(raw: bytes, boundary: bytes) -> list[dict[str, Any]]:
    delimiter = b"--" + boundary
    parts: list[dict[str, Any]] = []
    for section in raw.split(delimiter):
        if not section or section in {b"--", b"--\r\n", b"--\n"}:
            continue
        if section.startswith(b"\r\n"):
            section = section[2:]
        elif section.startswith(b"\n"):
            section = section[1:]
        if section.endswith(b"--"):
            section = section[:-2]
        if section.endswith(b"\r\n"):
            section = section[:-2]
        elif section.endswith(b"\n"):
            section = section[:-1]

        header_bytes, separator, body = section.partition(b"\r\n\r\n")
        if not separator:
            header_bytes, separator, body = section.partition(b"\n\n")
        if not separator:
            continue

        headers = _parse_multipart_headers(header_bytes)
        disposition = _parse_header_params(headers.get("content-disposition", ""))
        parts.append(
            {
                "name": disposition.get("name", ""),
                "filename": disposition.get("filename", ""),
                "content_type": headers.get("content-type", ""),
                "headers": headers,
                "data": body,
            }
        )
    return parts


def _parse_multipart_headers(raw: bytes) -> dict[str, str]:
    headers: dict[str, str] = {}
    for line in raw.decode("utf-8", errors="replace").splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        headers[key.strip().lower()] = value.strip()
    return headers


def _parse_header_params(value: str) -> dict[str, str]:
    params: dict[str, str] = {}
    parts = [part.strip() for part in value.split(";") if part.strip()]
    if parts:
        params[""] = parts[0].lower()
    for part in parts[1:]:
        if "=" not in part:
            continue
        key, raw_value = part.split("=", 1)
        clean = raw_value.strip()
        if len(clean) >= 2 and clean[0] == clean[-1] == '"':
            clean = clean[1:-1].replace(r"\"", '"')
        params[key.strip().lower()] = clean
    return params


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the BioAgent HTTP web UI.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    run_server(host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
