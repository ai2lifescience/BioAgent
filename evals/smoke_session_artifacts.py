"""Offline smoke checks for SDK session and artifact ownership."""
from __future__ import annotations

from pathlib import Path
import sys
import asyncio
from tempfile import TemporaryDirectory

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agents import SQLiteSession
from harness.sessions import SessionMetadataStore
from harness.support.artifacts import SessionArtifactStore


def main() -> int:
    with TemporaryDirectory() as temporary_dir:
        root = Path(temporary_dir)
        metadata = SessionMetadataStore(root / "metadata")
        artifacts = SessionArtifactStore(metadata, runs_dir=root / "runs", sessions_dir=root / "sessions")
        session, created = metadata.get_or_create_session("session_smoke", "First request")
        assert created
        run = artifacts.prepare_run(session)
        assert run["run_id"]
        artifacts.register_result(session, {"skill": "smoke", "result": {"report_path": str(Path(run["artifact_dir"]) / "report.md")}})
        assert artifacts.for_run(session, run["run_id"])[0]["kind"] == "report"
        upload = artifacts.store_upload("session_smoke", "example.fasta", b">x\nACGT\n", "text/plain")
        assert Path(upload["path"]).exists()
        assert artifacts.delete_upload("session_smoke", upload["upload_id"])
        metadata.record_exchange(session, "First request", "Second response")
        sdk_session = SQLiteSession("session_smoke", db_path=root / "sessions.sqlite3")
        asyncio.run(sdk_session.add_items([{"role": "user", "content": "First request"}]))
        sdk_session.close()
        assert metadata.list_sessions()[0]["message_count"] == 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
