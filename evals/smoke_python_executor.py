"""Offline checks for the approved bounded Python executor."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from agents.testing import ModelStep, ScriptedModel, assistant_message, function_call

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.function_tools.coding.python_execute import _operation
from tools.infrastructure.tool_support.context import OperationContext


class PythonExecutorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.context = OperationContext(
            "python_execute",
            {"session_dir": str(self.root), "workspace_dir": str(self.root / "outputs")},
        )

    def run_code(self, code: str, **kwargs):
        return _operation(context=self.context, code=code, **kwargs)

    def test_success_persists_script_and_output(self):
        result = self.run_code(
            'from pathlib import Path\nPath("answer.txt").write_text(str(6 * 7))\nprint("computed", 6 * 7)',
            input_paths=[], output_paths=["answer.txt"], timeout_seconds=10,
        )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["data"]["returncode"], 0)
        self.assertEqual(result["data"]["stdout"].strip(), "computed 42")
        self.assertEqual(result["data"]["missing_outputs"], [])
        paths = {item["path"] for item in result["files"]}
        script = next(item for item in result["files"] if item["name"] == "script.py")
        self.assertEqual(script["kind"], "text")
        self.assertEqual(script["content_type"], "text/x-python; charset=utf-8")
        output = next(path for path in paths if path.endswith("/answer.txt"))
        self.assertEqual((self.root / output).read_text(), "42")

    def test_input_staging_is_explicit(self):
        source = self.root / "inputs" / "values.txt"
        source.parent.mkdir()
        source.write_text("alpha\n")
        code = (
            "import json, os\n"
            "from pathlib import Path\n"
            "staged = json.loads(os.environ['BIOAGENT_INPUTS_JSON'])['inputs/values.txt']\n"
            "Path('upper.txt').write_text(Path(staged).read_text().upper())\n"
        )
        result = self.run_code(code, input_paths=["inputs/values.txt"], output_paths=["upper.txt"], timeout_seconds=10)
        self.assertEqual(result["status"], "ok")
        output = next(item["path"] for item in result["files"] if item["name"] == "upper.txt")
        self.assertEqual((self.root / output).read_text(), "ALPHA\n")

    def test_nonzero_exit_is_reported(self):
        result = self.run_code("raise RuntimeError('fixture failure')", input_paths=[], output_paths=[], timeout_seconds=10)
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"]["code"], "PYTHON_EXECUTION_FAILED")
        self.assertIn("fixture failure", result["data"]["stderr"])

    def test_application_secrets_are_not_inherited(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "secret-value"}, clear=False):
            result = self.run_code(
                "import os\nfrom pathlib import Path\nPath('secret.txt').write_text(os.environ.get('OPENAI_API_KEY', 'missing'))",
                input_paths=[], output_paths=["secret.txt"], timeout_seconds=10,
            )
        self.assertEqual(result["status"], "ok")
        output = next(item["path"] for item in result["files"] if item["name"] == "secret.txt")
        self.assertEqual((self.root / output).read_text(), "missing")

    def test_timeout_kills_execution(self):
        result = self.run_code("while True: pass", input_paths=[], output_paths=[], timeout_seconds=1)
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"]["code"], "PYTHON_TIMEOUT")
        self.assertTrue(result["data"]["timed_out"])

    def test_path_and_expected_output_boundaries(self):
        with self.assertRaises(ValueError):
            self.run_code("print('x')", input_paths=["../secret"], output_paths=[], timeout_seconds=10)
        with self.assertRaises(ValueError):
            self.run_code("print('x')", input_paths=[], output_paths=["../secret"], timeout_seconds=10)
        with self.assertRaises(ValueError):
            self.run_code("print('x')", input_paths=[], output_paths=["inputs/copied"], timeout_seconds=10)
        result = self.run_code("print('x')", input_paths=[], output_paths=["missing.txt"], timeout_seconds=10)
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"]["code"], "PYTHON_OUTPUT_MISSING")
        self.assertIn("missing.txt", result["error"]["message"])

    def test_runtime_requires_approval_and_resumes_once(self):
        import asyncio
        from harness import runtime, sandbox
        from harness.sessions import SessionMetadataStore

        session_id = "python-executor-approval"
        with TemporaryDirectory() as td:
            root = Path(td)
            store = SessionMetadataStore(root / "metadata")
            initial_model = ScriptedModel([
                ModelStep(output=[function_call(
                    "python_execute",
                    {
                        "code": "from pathlib import Path\nPath('approved.txt').write_text('yes')",
                        "input_paths": [],
                        "output_paths": ["approved.txt"],
                        "timeout_seconds": 10,
                    },
                    call_id="python-approval",
                )]),
            ])
            with patch.object(runtime, "STATE_STORE", store), \
                 patch.object(runtime, "SESSION_DB", root / "conversation.sqlite3"), \
                 patch.object(sandbox, "WORKSPACES_DIR", root / "sessions"):
                pending = asyncio.run(runtime.async_run_agent(
                    "Generate the approved fixture", session_id=session_id, model=initial_model,
                ))
                self.assertEqual(pending["status"], "pending_approval")
                approval = pending["approvals"][0]
                self.assertEqual(approval["tool_name"], "python_execute")
                self.assertEqual(len(approval["code_sha256"]), 64)
                done = asyncio.run(runtime.async_resume_agent(
                    session_id,
                    approved=True,
                    approval_id=approval["approval_id"],
                    model=ScriptedModel([ModelStep(output=[assistant_message("Approved execution finished.")])]),
                ))
                self.assertEqual(done["status"], "ok")
                self.assertTrue(any(item["path"].endswith("/approved.txt") for item in done["files"]))


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(PythonExecutorTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print(json.dumps({"tests": result.testsRun, "failures": len(result.failures), "errors": len(result.errors)}))
    raise SystemExit(0 if result.wasSuccessful() else 1)
