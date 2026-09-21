"""Verify FunctionTool outputs stay inside the active session workspace."""

from __future__ import annotations

from pathlib import Path
from shutil import rmtree
import sys
from tempfile import TemporaryDirectory, mkdtemp
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from tools.function_tools.ncbi_retrieval.workflow import ncbi_retrieval
from tools.function_tools.pdb_download.workflow import pdb_download
from tools.function_tools.species_report.workflow import species_report
from tools.infrastructure.tool_support.context import WorkflowContext
from tools.infrastructure.workspace import workspace_output_dir


def _context(name: str, root: str) -> WorkflowContext:
    return WorkflowContext(name, {"session_dir": root, "workspace_dir": root})


def _assert_rejected(callable_, *args, **kwargs) -> None:
    try:
        callable_(*args, **kwargs)
    except ValueError:
        return
    raise AssertionError("outside-session output path was accepted")


def main() -> None:
    with TemporaryDirectory() as root:
        session_root = Path(root).resolve()
        context = _context("boundary_check", root)
        default = workspace_output_dir(context, None, "outputs")
        assert default.is_relative_to(session_root)
        _assert_rejected(workspace_output_dir, context, "/tmp/outside-agent-output")
        _assert_rejected(workspace_output_dir, context, "../outside-agent-output")
        outside = Path(mkdtemp(prefix="outside-agent-output-"))
        try:
            link = session_root / "outside-link"
            link.symlink_to(outside, target_is_directory=True)
            _assert_rejected(workspace_output_dir, context, "outside-link/file")
        finally:
            rmtree(outside)
        strict_context = WorkflowContext(
            "boundary_check",
            {"session_dir": root, "workspace_dir": str(session_root / "outputs")},
        )
        relative_output = workspace_output_dir(strict_context, "custom/results")
        assert relative_output == session_root / "outputs" / "custom" / "results"
        _assert_rejected(workspace_output_dir, strict_context, str(session_root / "runs"))

        ncbi_context = _context("ncbi_retrieval", root)
        captured: dict[str, str] = {}

        def fake_fetch(**kwargs):
            captured.update({"output_dir": str(kwargs["output_dir"])})
            return {"fasta_paths": [], "metadata_paths": [], "results": [],
                    "downloaded_count": 0, "matched_count": 0, "output_dir": captured["output_dir"]}

        with patch("tools.function_tools.ncbi_retrieval.workflow._action_ncbi_fetch", fake_fetch):
            ncbi_retrieval(context=ncbi_context, accessions=["NC_001422"])
        assert Path(captured["output_dir"]).resolve().is_relative_to(session_root)
        _assert_rejected(
            ncbi_retrieval,
            context=ncbi_context,
            accessions=["NC_001422"],
            output_dir="/tmp/outside-agent-output",
        )

        pdb_context = _context("pdb_download", root)
        fake_pdb = {"pdb_id": "1ABC", "file_format": "cif", "structure_path": "placeholder"}
        with patch("tools.function_tools.pdb_download.workflow._action_pdb_download", return_value=fake_pdb):
            pdb_download("1ABC", context=pdb_context)
        _assert_rejected(
            pdb_download,
            "1ABC",
            output_dir="/tmp/outside-agent-output",
            context=pdb_context,
        )

        report_context = _context("species_report", root)
        _assert_rejected(
            species_report,
            species_name="Escherichia coli",
            output_dir="/tmp/outside-agent-output",
            context=report_context,
        )

    print("output boundaries: ok")


if __name__ == "__main__":
    main()
