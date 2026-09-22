"""Verify active tools keep outputs inside the current workspace."""
from __future__ import annotations

from pathlib import Path
from shutil import rmtree
import sys
from tempfile import TemporaryDirectory, mkdtemp
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from tools.function_tools.biology.ncbi_retrieval import _operation as ncbi_retrieval
from tools.function_tools.biology.pdb_download import _operation as pdb_download
from tools.infrastructure.tool_support.context import OperationContext
from tools.infrastructure.workspace import workspace_output_dir


def _context(name: str, root: str) -> OperationContext:
    return OperationContext(name, {"session_dir": root, "workspace_dir": root})


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
        strict_context = OperationContext("boundary_check", {"session_dir": root, "workspace_dir": str(session_root / "outputs")})
        assert workspace_output_dir(strict_context, "custom/results") == session_root / "outputs" / "custom" / "results"
        _assert_rejected(workspace_output_dir, strict_context, str(session_root / "runs"))

        ncbi_context = _context("ncbi_retrieval", root)
        captured: dict[str, str] = {}

        def fake_fetch(**kwargs):
            captured["output_dir"] = str(kwargs["output_dir"])
            return {"fasta_paths": [], "metadata_paths": [], "results": [], "downloaded_count": 0, "matched_count": 0, "output_dir": captured["output_dir"]}

        with patch("tools.function_tools.biology.ncbi_retrieval.fetch_ncbi", fake_fetch):
            ncbi_retrieval(context=ncbi_context, accessions=["NC_001422"])
        assert Path(captured["output_dir"]).resolve().is_relative_to(session_root)
        _assert_rejected(ncbi_retrieval, context=ncbi_context, accessions=["NC_001422"], output_dir="/tmp/outside-agent-output")

        pdb_context = _context("pdb_download", root)
        def fake_download(pdb_id, file_format, output_dir):
            path = Path(output_dir) / f"{pdb_id}.{file_format}"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"data_fixture")
            return {"status": "ok", "database": "pdb", "pdb_id": pdb_id,
                    "identifier": pdb_id, "file_format": file_format, "url": "https://example.org/1ABC.cif",
                    "structure_path": str(path), "output_dir": output_dir, "bytes": path.stat().st_size}
        with patch("tools.function_tools.biology.pdb_download.download_pdb_structure", fake_download):
            pdb_download(pdb_id="1ABC", context=pdb_context)
        _assert_rejected(pdb_download, pdb_id="1ABC", output_dir="/tmp/outside-agent-output", context=pdb_context)

    print("output boundaries: ok")


if __name__ == "__main__":
    main()
