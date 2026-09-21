"""Offline smoke checks for workspace PDF extraction."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from tools.infrastructure.tool_support.context import WorkflowContext
from tools.function_tools.document_read.workflow import document_read


def _pdf_bytes() -> bytes:
    writer = PdfWriter()
    font = writer._add_object(
        DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
    )
    for message in ("Pipeline2Agent PDF page one", "Pipeline2Agent PDF page two"):
        page = writer.add_blank_page(width=612, height=792)
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
        )
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 12 Tf 72 720 Td ({message}) Tj ET".encode())
        page[NameObject("/Contents")] = writer._add_object(stream)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def main() -> int:
    with TemporaryDirectory() as directory:
        pdf = Path(directory) / "paper.pdf"
        pdf.write_bytes(_pdf_bytes())
        context = WorkflowContext(
            "document_read",
            user_context={
                "files": [
                    {
                        "path": str(pdf),
                        "workspace_path": "uploads/paper.pdf",
                    }
                ]
            },
        )
        result = document_read("uploads/paper.pdf", context=context)
        assert result["status"] == "ok"
        assert result["page_count"] == 2
        assert "[Page 1]" in result["text"]
        assert "Pipeline2Agent PDF page two" in result["text"]
        latest = document_read(None, context=context)
        assert latest["source_path"] == "uploads/paper.pdf"
        try:
            document_read("/etc/passwd", context=context)
        except ValueError as exc:
            assert "active workspace" in str(exc)
        else:
            raise AssertionError("outside-workspace paths must be rejected")
    print("document_read smoke: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
