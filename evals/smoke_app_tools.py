"""Offline checks for atomic data, research, workspace, and coding tools."""
from __future__ import annotations

import asyncio
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import importlib

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Bio import SeqIO
from Bio.Seq import Seq
from Bio.SeqRecord import SeqRecord

from tools.function_tools.coding.code_edit import _operation as code_edit
from tools.function_tools.coding.code_inspection import _operation as code_inspection
from tools.function_tools.coding.code_test import _operation as code_test
from tools.function_tools.workspace.workspace_search import _operation as workspace_search
from tools.infrastructure.tool_support.context import OperationContext

table_profile = importlib.import_module("tools.function_tools.data_analysis.table_profile")
table_plot = importlib.import_module("tools.function_tools.data_analysis.table_plot")
sequence_stats = importlib.import_module("tools.function_tools.biology.sequence_stats")
sequence_translate = importlib.import_module("tools.function_tools.biology.sequence_translate")
web_search = importlib.import_module("tools.function_tools.sources.web_search")


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
        search_context = OperationContext("workspace_search", user_context={"session_dir": directory, "files": files})
        assert workspace_search(query="alpha", context=search_context)["data"]["matched_count"] == 1

        user_context = {"session_dir": directory, "workspace_dir": str(root / "outputs"), "files": files}
        profile = table_profile._calculate(path="uploads/table.csv", max_rows=1000, context=OperationContext("table_profile", user_context))
        assert profile["data"]["rows"] == 3
        plot = table_plot._calculate(path="uploads/table.csv", column="value", max_rows=1000, context=OperationContext("table_plot", user_context))
        assert (root / plot["data"]["plot_path"]).is_file()

        stats = sequence_stats._calculate(
            source={"path": "uploads/sample.fasta", "sequence": None, "sequence_type": "auto"},
            max_records=100,
            context=OperationContext("sequence_stats", user_context),
        )
        assert stats["data"]["records"][0]["gc_content_percent"] == 37.5
        translated = sequence_translate._calculate(
            source={"sequence": "ATGAAATAG", "path": None, "sequence_type": "dna"},
            frame=1,
            genetic_code=1,
            max_records=100,
            context=OperationContext("sequence_translate", user_context),
        )
        assert translated["data"]["records"][0]["protein"] == "MK*"

        code_context = OperationContext("code_inspection", user_context={"session_dir": directory, "files": files})
        assert code_inspection(operation="search", query="alpha", context=code_context)["data"]["matched_count"] == 1
        edit_context = OperationContext("code_edit", user_context={"session_dir": directory, "files": files})
        assert code_edit(path="src/new.py", content="print(1)\n", context=edit_context)["data"]["changed_files"] == ["src/new.py"]
        test_context = OperationContext("code_test", user_context={"session_dir": directory, "files": files})
        assert asyncio.run(code_test(command="python -m compileall .", context=test_context))["data"]["returncode"] == 0

        async def fake_request(_url, _params):
            return '<div class="result"><a class="result__a" href="https://example.org/p">Example</a><a class="result__snippet">Snippet</a></div>'

        original_request = web_search.request
        web_search.request = fake_request
        try:
            result = asyncio.run(web_search._operation(query="test topic", domains=[], max_sources=5, context=OperationContext("web_search", user_context)))
            assert result["data"]["returned"] == 1
        finally:
            web_search.request = original_request

    print("app tools smoke: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
