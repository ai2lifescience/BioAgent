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
from harness import sandbox
from harness.sandbox import clear_workspace, delete_file, list_files, open_workspace, prepare_run, read_file, upload_file
from harness.sessions import SessionMetadataStore


def main() -> int:
    with TemporaryDirectory() as temporary_dir:
        root = Path(temporary_dir)
        metadata = SessionMetadataStore(root / "metadata")
        sandbox.WORKSPACES_DIR = root / "sessions"
        session, created = metadata.get_or_create_session("session_smoke", "First request")
        assert created
        run = prepare_run(session)
        assert run["run_id"]
        async def workspace_check():
            async with open_workspace("session_smoke") as workspace:
                upload = await upload_file(workspace, "example.fasta", b">x\nACGT\n")
                assert await read_file(workspace, upload["workspace_path"]) == b">x\nACGT\n"
                files = await list_files(workspace)
                assert files[0]["kind"] == "upload"
                await delete_file(workspace, upload["workspace_path"])
                assert not await list_files(workspace)
        asyncio.run(workspace_check())
        (sandbox.WORKSPACES_DIR / "session_smoke" / "outputs").mkdir(parents=True)
        (sandbox.WORKSPACES_DIR / "session_smoke" / "outputs" / "result.txt").write_text("result")
        asyncio.run(clear_workspace("session_smoke"))
        assert not list((sandbox.WORKSPACES_DIR / "session_smoke").iterdir())
        metadata.record_exchange(session, "First request", "Second response")
        sdk_session = SQLiteSession("session_smoke", db_path=root / "sessions.sqlite3")
        asyncio.run(sdk_session.add_items([{"role": "user", "content": "First request"}]))
        sdk_session.close()
        assert metadata.list_sessions()[0]["message_count"] == 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
