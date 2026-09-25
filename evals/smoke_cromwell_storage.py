"""Offline checks for optional Cromwell object-storage input staging."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.infrastructure.pipeline_engine.engine.input_storage import upload_local_file_values
from tools.infrastructure.pipeline_engine.engine.input_storage import S3InputUploader
from tools.infrastructure.pipeline_engine import service


class FakeUploader:
    backend = "fake-s3"
    base_uri = "s3://test-bucket/prefix"

    def __init__(self) -> None:
        self.calls: list[tuple[Path, str]] = []

    def upload(self, source: Path, object_key: str) -> str:
        self.calls.append((source, object_key))
        return f"s3://test-bucket/{object_key}"

    def cromwell_path(self, uri: str, object_key: str) -> str:
        return f"/data/versitygw/data/s3/test-bucket/{object_key}"


def adapter_integration_check() -> None:
    """Exercise the remote adapter path without contacting Cromwell or S3."""
    with TemporaryDirectory(prefix="agent-cromwell-adapter-") as directory:
        root = Path(directory)
        sequence = root / "sequence.fasta"
        sequence.write_text(">synthetic\nACGT\n", encoding="utf-8")
        fixture = root / "fixture"
        fixture.mkdir()
        outputs = {}
        for key, filename, contents in (
            ("report", "report.md", "# report\n"),
            ("metrics", "metrics.json", '{"sequence_length": 4}'),
            ("normalized_fasta", "normalized.fasta", ">synthetic\nACGT\n"),
        ):
            path = fixture / filename
            path.write_text(contents, encoding="utf-8")
            outputs[f"TemplateWdl.{key}"] = str(path)

        fake = FakeUploader()
        with patch.dict(
            os.environ,
            {"CROMWELL_URL": "http://cromwell.test", "CROMWELL_INPUT_STORAGE_URI": "s3://test-bucket/prefix"},
            clear=True,
        ):
            plan = service.plan(root, "template_wdl", {"sequence": "sequence.fasta"}, {})
            with (
                patch.object(S3InputUploader, "from_environment", classmethod(lambda cls: fake)),
                patch("requests.post", return_value=Mock(ok=True, json=lambda: {"id": "workflow-id", "status": "Succeeded"})),
                patch("requests.get", side_effect=[
                    Mock(ok=True, json=lambda: {"status": "Succeeded"}),
                    Mock(ok=True, json=lambda: {"outputs": outputs}),
                ]),
            ):
                result = service.execute_engine(root, service.JobStore(root).get(plan["plan_id"]))
        runtime_inputs = json.loads(Path(result["inputs_path"]).read_text(encoding="utf-8"))
        assert fake.calls
        assert runtime_inputs["TemplateWdl.input_fasta"].startswith("/data/versitygw/data/s3/test-bucket/")
        assert result["input_storage"]["uploaded"]


def main() -> int:
    with TemporaryDirectory(prefix="agent-cromwell-storage-") as directory:
        root = Path(directory)
        first = root / "reads.fastq.gz"
        second = root / "reference.fa"
        first.write_bytes(b"reads")
        second.write_bytes(b"reference")
        inputs = root / "inputs.json"
        inputs.write_text(json.dumps({
            "Workflow.reads": str(first),
            "Workflow.other_reads": [str(first), str(second)],
            "Workflow.mounted_db": "/remote/database/index.k2d",
        }))
        uploader = FakeUploader()
        records = upload_local_file_values(inputs, uploader, pipeline_name="demo", run_id="run-1")
        payload = json.loads(inputs.read_text())
        assert len(records) == 2
        assert len(uploader.calls) == 2
        assert payload["Workflow.reads"].startswith("/data/versitygw/data/s3/test-bucket/")
        assert payload["Workflow.other_reads"][0] == payload["Workflow.reads"]
        assert payload["Workflow.mounted_db"] == "/remote/database/index.k2d"
    adapter_integration_check()
    print("cromwell object-storage input staging: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
