"""Offline smoke checks for document, data, web, and coding assistant tools."""

from __future__ import annotations

from pathlib import Path
import sys
from tempfile import TemporaryDirectory

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.common.context import WorkflowContext
from tools.function_tools.biology_analysis.workflow import biology_analysis
from tools.function_tools.code_workspace.workflow import code_edit, code_inspection, code_test
from tools.function_tools.data_analysis.workflow import data_analysis
from tools.function_tools.sequence_analysis.workflow import sequence_analysis
from tools.function_tools.web_research import workflow as web_workflow
from tools.function_tools.workspace_search.workflow import workspace_search
from Bio import SeqIO
from Bio.Seq import Seq
from Bio.SeqRecord import SeqRecord


class _Response:
    status_code = 200
    headers = {"Content-Type": "text/html"}

    def __init__(self, text: str):
        self._content = text.encode()
        self.text = text

    def iter_content(self, chunk_size=65536):
        yield self._content

    def raise_for_status(self):
        return None

    def close(self):
        return None


def main() -> int:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        uploads = root / "uploads"
        uploads.mkdir()
        (uploads / "notes.md").write_text("alpha result\nBeta finding\n", encoding="utf-8")
        (uploads / "table.csv").write_text("group,value\na,1\na,3\nb,5\n", encoding="utf-8")
        SeqIO.write(SeqRecord(Seq("ATGCGTAA"), id="sequence-1", description="fixture"), uploads / "sample.fasta", "fasta")
        files = [
            {"path": str(uploads / "notes.md"), "workspace_path": "uploads/notes.md", "name": "notes.md", "modified_at": 1},
            {"path": str(uploads / "table.csv"), "workspace_path": "uploads/table.csv", "name": "table.csv", "modified_at": 2},
            {"path": str(uploads / "sample.fasta"), "workspace_path": "uploads/sample.fasta", "name": "sample.fasta", "modified_at": 3},
        ]
        search_context = WorkflowContext("workspace_search", user_context={"session_dir": directory, "files": files})
        assert workspace_search("alpha", context=search_context)["matched_count"] == 1

        analysis_context = WorkflowContext("data_analysis", user_context={"session_dir": directory, "workspace_dir": str(root / "outputs"), "files": files})
        assert data_analysis(path="uploads/table.csv", operation="profile", context=analysis_context)["rows"] == 3
        plot = data_analysis(path="uploads/table.csv", operation="plot", column="value", context=analysis_context)
        assert (root / plot["plot_path"]).is_file()

        sequence_context = WorkflowContext("sequence_analysis", user_context={"session_dir": directory, "files": files})
        stats = sequence_analysis(fasta_path="uploads/sample.fasta", context=sequence_context)
        assert stats["records"][0]["gc_content_percent"] == 37.5
        biology_context = WorkflowContext("biology_analysis", user_context={"session_dir": directory, "files": files})
        translated = biology_analysis(operation="translate", sequence="ATGAAATAG", context=biology_context)
        assert translated["records"][0]["protein"] == "MK*"
        try:
            biology_analysis(operation="sequence_stats", sequence="ACGT", context=biology_context)
        except ValueError as exc:
            assert "reverse_complement" in str(exc)
        else:
            raise AssertionError("biology_analysis accepted sequence metrics")

        code_context = WorkflowContext("code_inspection", user_context={"session_dir": directory, "files": files})
        assert code_inspection("search", query="alpha", context=code_context)["matched_count"] == 1
        edit_context = WorkflowContext("code_edit", user_context={"session_dir": directory, "files": files})
        assert code_edit("src/new.py", "print(1)\n", context=edit_context)["changed_files"] == ["src/new.py"]
        test_context = WorkflowContext("code_test", user_context={"session_dir": directory, "files": files})
        assert code_test("python -m compileall .", context=test_context)["returncode"] == 0

    original_get = web_workflow.requests.get

    def fake_get(url, **kwargs):
        if "duckduckgo" in url:
            return _Response('<div class="result"><a class="result__a" href="https://example.org/p">Example</a><a class="result__snippet">Snippet</a></div>')
        return _Response("<html><body>Page body</body></html>")

    web_workflow.requests.get = fake_get
    try:
        result = web_workflow.web_research("test topic", context=WorkflowContext("web_research"))
        assert result["source_count"] == 1
        try:
            web_workflow._validate_url("http://127.0.0.1/test")
        except ValueError:
            pass
        else:
            raise AssertionError("private web source was accepted")
    finally:
        web_workflow.requests.get = original_get

    print("app tools smoke: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
