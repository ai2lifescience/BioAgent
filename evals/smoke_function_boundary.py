"""Offline SDK boundary regressions for the flat FunctionTool catalog."""
from __future__ import annotations

import asyncio
import importlib
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents import Agent, Runner
from agents.testing import ModelStep, ScriptedModel, assistant_message, function_call
from agents.tool_context import ToolContext
from pypdf import PdfWriter

from harness.context import AgentRunContext
from harness.sessions import SessionMetadata
from harness.tracing import configure_tracing
from tools.function_tools import FUNCTION_TOOLS
from tools.infrastructure.tool_support.context import OperationContext
from tools.infrastructure.tool_support.evidence import EvidenceCollector
from tools.infrastructure.tool_support.operations import calculate
from tools.infrastructure.workspace.paths import output_file_path, resolve_workspace_item

configure_tracing()
TOOLS = {tool.name: tool for tool in FUNCTION_TOOLS}


def _slow_calculation(*, context):
    Path(context.session_dir, "worker.pid").write_text(str(os.getpid()))
    time.sleep(60)
    return {}


async def _calculate_locally(handler, arguments, metadata, name):
    """Keep patched external provider clients in this process for fixture tests."""
    return handler(context=OperationContext(name, metadata), **arguments)


class FunctionBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.context = AgentRunContext(
            session=SessionMetadata(session_id="boundary", metadata={"run": {
                "session_dir": temporary.name, "workspace_dir": str(self.root / "outputs"),
            }}),
            model_key="fixture",
        )

    async def call(self, name, **arguments):
        encoded = json.dumps(arguments)
        tool_context = ToolContext(context=self.context, tool_name=name, tool_call_id=name, tool_arguments=encoded)
        result = await TOOLS[name].on_invoke_tool(tool_context, encoded)
        payload = json.loads(str(result))
        self.assertNotIn(str(self.root), json.dumps(payload))
        self.assertNotIn(str(self.root), json.dumps(self.context.tool_results))
        return payload

    async def test_runner_edits_then_reads_and_reports_failed_tests_without_approval(self):
        model = ScriptedModel([
            ModelStep(output=[function_call("code_edit", {"path": "broken.py", "content": "def broken(:\n"}, call_id="edit")]),
            ModelStep(output=[function_call("code_inspection", {"operation": "read", "path": "broken.py"}, call_id="read")]),
            ModelStep(output=[function_call("code_test", {"command": "python -m compileall ."}, call_id="test")]),
            ModelStep(output=[assistant_message("Compilation failed.")]),
        ])
        result = await Runner.run(Agent(name="coding", model=model, tools=[TOOLS[name] for name in
            ("code_edit", "code_inspection", "code_test")]), "Edit, read, and test", context=self.context)
        self.assertFalse(result.interruptions)
        self.assertEqual([record["status"] for record in self.context.tool_results], ["ok", "ok", "error"])
        self.assertEqual(self.context.tool_results[1]["result"]["content"], "def broken(:\n")
        self.assertEqual(self.context.tool_results[-1]["error_type"], "TEST_FAILED")
        self.assertIn("SyntaxError", self.context.tool_results[-1]["result"]["logs"])
        self.assertEqual(self.context.files[0]["path"], "broken.py")
        evidence = EvidenceCollector().collect(self.context.tool_results)
        self.assertEqual(evidence["tool_errors"][0]["error_type"], "TEST_FAILED")
        self.assertEqual(evidence["outputs"][-1]["status"], "error")

    async def test_edit_artifact_becomes_input_and_conflict_preserves_file(self):
        edited = await self.call("code_edit", path="notes.txt", content="alpha finding\n")
        self.assertEqual(edited["status"], "ok")
        self.assertEqual(edited["files"][0]["path"], "notes.txt")
        inspected = await self.call("file_inspection", path="notes.txt")
        self.assertEqual(inspected["data"]["line_count"], 1)
        searched = await self.call("workspace_search", query="alpha")
        self.assertEqual(searched["data"]["matches"][0]["path"], "notes.txt")
        conflict = await self.call("code_edit", path="notes.txt", content="replacement", expected_sha256="wrong")
        self.assertEqual(conflict["status"], "error")
        self.assertEqual((self.root / "notes.txt").read_text(), "alpha finding\n")
        invalid = await self.call("code_edit", path="notes.txt")
        self.assertEqual(invalid["status"], "error")

    async def test_pdf_ocr_state_is_preserved_in_typed_data(self):
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        writer.write(str(self.root / "scanned.pdf"))
        self.context.files = [{"path": "scanned.pdf", "workspace_path": "scanned.pdf"}]
        result = await self.call("document_read", path="scanned.pdf")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["data"]["state"], "ocr_required")
        self.assertEqual(result["data"]["text"], "")

    async def test_provider_contracts_and_download_artifacts(self):
        alpha = importlib.import_module("tools.function_tools.biology.alphafold_download")
        pdb = importlib.import_module("tools.function_tools.biology.pdb_download")
        ncbi = importlib.import_module("tools.function_tools.biology.ncbi_retrieval")
        database = importlib.import_module("tools.function_tools.biology.database_lookup")

        def alpha_response(accession, directory, file_format):
            path = Path(directory) / f"{accession}.{file_format}"
            path.write_text("data_fixture\n")
            return {"query": accession, "structure_path": str(path), "record_count": 1, "provenance": {}}

        def pdb_response(pdb_id, file_format, directory):
            path = Path(directory) / f"{pdb_id}.{file_format}"
            path.write_text("data_fixture\n")
            return {"status": "ok", "database": "pdb", "pdb_id": pdb_id, "identifier": pdb_id,
                    "file_format": file_format, "url": f"https://files.rcsb.org/download/{path.name}",
                    "structure_path": str(path), "output_dir": directory, "bytes": path.stat().st_size}

        def ncbi_response(**kwargs):
            path = Path(kwargs["output_dir"]) / "sequence.fasta"
            path.write_text(">fixture\nACGT\n")
            query = {"term": kwargs["term"], "db": "nucleotide", "sequence_format": "fasta", "metadata_format": "csv",
                     "matched_count": 1, "downloaded_count": 1, "output_dir": kwargs["output_dir"], "fasta_path": str(path)}
            return {**{key: query[key] for key in ("db", "sequence_format", "metadata_format", "matched_count", "downloaded_count", "output_dir")},
                    "query_count": 1, "results": [query], "fasta_paths": [str(path)], "metadata_paths": []}

        with patch("tools.infrastructure.tool_support.operations.calculate", _calculate_locally), \
             patch.object(alpha, "download_alphafold_structure", alpha_response), \
             patch.object(pdb, "download_pdb_structure", pdb_response), \
             patch.object(ncbi, "fetch_ncbi", ncbi_response), \
             patch.object(database, "search_bio_database_tool", return_value={
                 "database": "uniprot", "query": "P0A7V8", "record_count": 0, "records": []}):
            for name, arguments in (
                ("alphafold_download", {"accession": "P0A7V8"}),
                ("pdb_download", {"pdb_id": "1ABC"}),
                ("ncbi_retrieval", {"term": "fixture"}),
            ):
                with self.subTest(tool=name):
                    result = await self.call(name, **arguments)
                    self.assertEqual(result["status"], "ok", result)
                    self.assertEqual(len(result["files"]), 1)
                    self.assertTrue((self.root / result["files"][0]["path"]).is_file())
            lookup = await self.call("database_lookup", database="uniprot", query="P0A7V8")
            self.assertEqual(lookup["status"], "ok", lookup)
            self.assertEqual(lookup["files"], [])
        self.assertEqual(len(self.context.files), 3)

    async def test_blast_submission_pending_and_failure_states(self):
        module = importlib.import_module("tools.function_tools.biology.blast_search")
        with patch("tools.infrastructure.tool_support.operations.calculate", _calculate_locally):
            for state in ("SUBMITTED", "READY", "TIMEOUT", "FAILED", "UNKNOWN"):
                with self.subTest(state=state), patch.object(module, "run_blast_search", return_value={
                    "database": "ncbi-blast:nt", "program": "blastn", "rid": "FIXTURE", "status": state,
                }):
                    result = await self.call("blast_search", rid="FIXTURE")
                    self.assertEqual(result["data"]["state"], state)
                    self.assertEqual(result["status"], "error" if state in {"FAILED", "UNKNOWN"} else "ok")
            with patch.object(module, "run_blast_search", side_effect=RuntimeError("Failed at /private/server/config")):
                result = await self.call("blast_search", rid="FIXTURE")
                self.assertEqual(result["status"], "error")
                self.assertNotIn("/private/server/config", json.dumps(self.context.tool_results))

    async def test_paths_reject_absolute_traversal_and_symlink_escape(self):
        with TemporaryDirectory() as outside:
            secret = Path(outside) / "secret.txt"
            secret.write_text("private")
            (self.root / "link").symlink_to(outside, target_is_directory=True)
            with patch("tools.infrastructure.tool_support.operations.calculate", _calculate_locally):
                for path in (str(secret), "../secret.txt", "link/secret.txt"):
                    result = await self.call("code_edit", path=path, content="changed")
                    self.assertEqual(result["status"], "error")
                self.assertEqual(secret.read_text(), "private")
            context = self.context.operation_context("fixture")
            with self.assertRaises(ValueError):
                resolve_workspace_item(context, {"path": str(secret)})
            with self.assertRaises(ValueError):
                output_file_path(self.root / "link", "../secret.txt")
            (self.root / "output.txt").symlink_to(secret)
            with self.assertRaises(ValueError):
                output_file_path(self.root, "output.txt")

    @unittest.skipUnless(os.name == "posix", "POSIX worker lifecycle")
    async def test_cancel_stops_calculation_worker(self):
        task = asyncio.create_task(calculate(_slow_calculation, {}, self.context.run, "slow"))
        try:
            async with asyncio.timeout(15):
                while not (self.root / "worker.pid").exists():
                    await asyncio.sleep(0.02)
            pid = int((self.root / "worker.pid").read_text())
        finally:
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)

    @unittest.skipUnless(os.name == "posix", "POSIX process groups")
    async def test_cancel_stops_test_command_and_descendants(self):
        (self.root / "test_slow.py").write_text(
            "import pathlib, subprocess, sys, time, unittest\n"
            "class Slow(unittest.TestCase):\n"
            "    def test_wait(self):\n"
            "        child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
            "        pathlib.Path('child.pid').write_text(str(child.pid))\n"
            "        child.wait()\n"
        )
        task = asyncio.create_task(self.call("code_test", command="python -m unittest"))
        try:
            async with asyncio.timeout(15):
                while not (self.root / "child.pid").exists():
                    await asyncio.sleep(0.02)
            pid = int((self.root / "child.pid").read_text())
        finally:
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        # A killed orphan may briefly remain as a zombie before PID 1 reaps it.
        proc_stat = Path(f"/proc/{pid}/stat")
        self.assertTrue(not proc_stat.exists() or proc_stat.read_text().split()[2] == "Z")
        self.assertEqual(self.context.events[-1]["event"], "tool_cancelled")


if __name__ == "__main__":
    unittest.main()
