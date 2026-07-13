"""No-network smoke checks for session and artifact ownership."""

from __future__ import annotations

from pathlib import Path
import sys
from tempfile import TemporaryDirectory

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent_core.artifacts import SessionArtifactStore
from agent_core.memory import InMemoryStateStore
from interfaces.api import ARTIFACT_STORE, ORCHESTRATOR, STATE_STORE, TRACE_STORE


def main() -> int:
    assert ORCHESTRATOR.memory is STATE_STORE
    assert ORCHESTRATOR.trace_store is TRACE_STORE
    assert ORCHESTRATOR.artifact_store is ARTIFACT_STORE
    assert ARTIFACT_STORE.state_store is STATE_STORE

    with TemporaryDirectory() as temporary_dir:
        root = Path(temporary_dir)
        state_store = InMemoryStateStore()
        artifact_store = SessionArtifactStore(
            state_store,
            runs_dir=root / "runs",
            sessions_dir=root / "sessions",
        )
        session = state_store.create_session(session_id="session-smoke")

        run = artifact_store.prepare_run(session)
        assert run["run_id"]
        assert not Path(run["runtime_dir"]).exists()
        assert not Path(run["artifact_dir"]).exists()

        report_path = Path(run["artifact_dir"]) / "reports" / "report.md"
        artifact_store.register_result(
            session,
            {
                "skill": "smoke_skill",
                "result": {"report_path": str(report_path)},
                "tool_calls": [],
            },
        )
        artifacts = artifact_store.for_run(session, run["run_id"])
        assert len(artifacts) == 1
        assert artifacts[0]["path"] == str(report_path)
        assert artifacts[0]["source_skill"] == "smoke_skill"

        upload = artifact_store.store_upload(
            session_id=session.session_id,
            filename="example.fasta",
            data=b">example\nACGT\n",
            content_type="text/plain",
        )
        upload_path = Path(upload["path"])
        assert upload_path.exists()
        assert artifact_store.list_uploads(session.session_id)["uploads"][0]["upload_id"] == upload["upload_id"]
        assert artifact_store.delete_upload(session.session_id, upload["upload_id"])
        assert not upload_path.exists()

        state_store.append_message(session.session_id, "user", "First")
        state_store.append_message(session.session_id, "assistant", "Second")
        assert state_store.recent_messages(session) == [
            {"role": "user", "content": "First"},
            {"role": "assistant", "content": "Second"},
        ]

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
