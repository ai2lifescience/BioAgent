"""Offline regression checks for Cromwell S3 output collection."""
from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.infrastructure.pipeline_engine import service
from tools.infrastructure.pipeline_engine.engine.input_storage import S3OutputStorage
from tools.infrastructure.pipeline_engine.engine.runner import prepare_pipeline_context
from tools.infrastructure.pipeline_engine.engine.wdl import copy_declared_outputs, write_wdl_options


class FakeS3:
    def __init__(self, objects: dict[tuple[str, str], bytes] | None = None) -> None:
        self.objects = objects or {}
        self.downloads: list[tuple[str, str]] = []

    def download_file(self, bucket: str, key: str, filename: str) -> None:
        self.downloads.append((bucket, key))
        if (bucket, key) not in self.objects:
            Path(filename).write_bytes(b"partial transfer")
            raise OSError("object unavailable")
        Path(filename).write_bytes(self.objects[bucket, key])


class CromwellOutputChecks(unittest.TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory(prefix="agent-cromwell-outputs-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        environment = patch.dict(os.environ, {}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)
        self.client = FakeS3()
        self.storage = S3OutputStorage(
            bucket="test-bucket", prefix="cromwell/outputs", client=self.client,
            mount_prefix="/remote/s3/test-bucket/cromwell/outputs/",
            execution_prefixes=("/remote", "/remote/cromwell-executions/"),
        )
        self.env = {
            "CROMWELL_URL": "http://cromwell.test",
            "CROMWELL_OUTPUT_STORAGE_URI": self.storage.base_uri,
            "CROMWELL_OUTPUT_STORAGE_MOUNT_PREFIX": self.storage.mount_prefix,
            "CROMWELL_OUTPUT_STORAGE_EXECUTION_PATH_PREFIXES": "/remote/cromwell-executions",
            "CROMWELL_INPUT_STORAGE_ENDPOINT": "http://object-store.test",
            "CROMWELL_INPUT_STORAGE_ACCESS_KEY": "test-access",
            "CROMWELL_INPUT_STORAGE_SECRET_KEY": "test-secret",
            "CROMWELL_INPUT_STORAGE_REGION": "us-east-1",
        }

    def test_mscan_mapping_and_path_boundaries(self) -> None:
        suffix = "Workflow/id/call-task/execution/output.tsv"
        expected = f"s3://test-bucket/cromwell/outputs/{suffix}"
        for source in (
            f"/remote/cromwell-executions/{suffix}",
            f"{self.storage.mount_prefix}/{suffix}",
            f"file:///remote/cromwell-executions/{suffix}",
            expected,
        ):
            with self.subTest(source=source):
                self.assertEqual(self.storage.uri_for_path(source), expected)
        for source in (
            "/remote-other/file", "/unrelated/file", "https://host/file", "",
            "s3://other-bucket/cromwell/outputs/file",
        ):
            self.assertIsNone(self.storage.uri_for_path(source))
        self.assertEqual(
            self.storage.uri_for_path("/remote/cromwell-executions-other/file"),
            "s3://test-bucket/cromwell/outputs/cromwell-executions-other/file",
        )

    def test_successful_and_failed_downloads_are_atomic(self) -> None:
        key = ("test-bucket", "cromwell/outputs/output.bin")
        self.client.objects[key] = b"\x00\xffbinary\n"
        target = self.root / "outputs" / "output.bin"
        self.assertTrue(self.storage.download("/remote/cromwell-executions/output.bin", target))
        self.assertEqual(target.read_bytes(), self.client.objects[key])
        self.assertEqual(self.storage.downloaded[0]["size"], len(self.client.objects[key]))
        with self.assertRaisesRegex(RuntimeError, "Could not download Cromwell output"):
            self.storage.download("/remote/cromwell-executions/missing", target)
        self.assertEqual(target.read_bytes(), self.client.objects[key])
        self.assertEqual(list(target.parent.iterdir()), [target])
        self.assertFalse(self.storage.download("/unrelated/output", self.root / "unused"))

    def test_output_settings_reuse_input_connection_and_credentials(self) -> None:
        with (
            patch.dict(os.environ, self.env),
            patch("boto3.client", return_value=self.client) as factory,
        ):
            storage = S3OutputStorage.from_environment()
        self.assertEqual(storage.mount_prefix, self.storage.mount_prefix)
        self.assertEqual(factory.call_args.kwargs["endpoint_url"], "http://object-store.test")
        self.assertEqual(factory.call_args.kwargs["region_name"], "us-east-1")
        self.assertEqual(factory.call_args.kwargs["aws_access_key_id"], "test-access")
        self.assertEqual(factory.call_args.kwargs["aws_secret_access_key"], "test-secret")

    def test_explicit_credentials_do_not_mix_with_input_credentials(self) -> None:
        with patch.dict(os.environ, {**self.env, "CROMWELL_OUTPUT_STORAGE_ACCESS_KEY": "other"}):
            with patch("boto3.client") as factory:
                with self.assertRaisesRegex(ValueError, "must be supplied together"):
                    S3OutputStorage.from_environment()
                factory.assert_not_called()
        overrides = {
            "CROMWELL_OUTPUT_STORAGE_ENDPOINT": "http://outputs.test",
            "CROMWELL_OUTPUT_STORAGE_ACCESS_KEY": "output-access",
            "CROMWELL_OUTPUT_STORAGE_SECRET_KEY": "output-secret",
            "CROMWELL_OUTPUT_STORAGE_SESSION_TOKEN": "output-token",
        }
        with patch.dict(os.environ, {**self.env, **overrides}), patch("boto3.client") as factory:
            S3OutputStorage.from_environment()
        self.assertEqual(factory.call_args.kwargs["endpoint_url"], "http://outputs.test")
        self.assertEqual(factory.call_args.kwargs["aws_access_key_id"], "output-access")
        self.assertEqual(factory.call_args.kwargs["aws_secret_access_key"], "output-secret")
        self.assertEqual(factory.call_args.kwargs["aws_session_token"], "output-token")

    def test_unconfigured_and_invalid_output_storage(self) -> None:
        self.assertIsNone(S3OutputStorage.from_environment())
        with patch.dict(os.environ, {"CROMWELL_OUTPUT_STORAGE_URI": "https://host/bucket"}):
            with self.assertRaisesRegex(ValueError, "s3://bucket/prefix"):
                S3OutputStorage.from_environment()
        for field in ("mount_prefix", "execution_prefixes"):
            kwargs = {field: "relative/path" if field == "mount_prefix" else ("relative/path",)}
            with self.assertRaisesRegex(ValueError, "absolute"):
                S3OutputStorage(bucket="test", prefix="outputs", client=self.client, **kwargs)

    def test_storage_options_override_client_path_and_work_without_options_file(self) -> None:
        selected = self.root / "sequence.fasta"
        selected.write_text(">synthetic\nACGT\n")
        context = prepare_pipeline_context(
            pipeline_name="template_wdl", artifact_dir=str(self.root),
            input_overrides={"sequence": str(selected)},
        )
        original = (context.pipeline_dir / "options.json").read_bytes()
        for with_options in (True, False):
            manifest = dict(context.runner_config)
            if not with_options:
                manifest.pop("options_json")
            path = write_wdl_options(
                replace(context, runner_config=manifest),
                output_storage_mount_prefix=self.storage.mount_prefix,
            )
            options = json.loads(path.read_text())
            self.assertEqual(options["final_workflow_outputs_dir"], self.storage.mount_prefix)
            self.assertFalse(options["use_relative_output_paths"])
        self.assertEqual((context.pipeline_dir / "options.json").read_bytes(), original)

    def test_optional_null_outputs_and_local_fallback(self) -> None:
        local = self.root / "source.txt"
        local.write_text("local")
        target = self.root / "copied.txt"
        optional = self.root / "optional.txt"
        copy_declared_outputs(
            [{"wdl_output": "Workflow.file", "path": str(target)},
             {"wdl_output": "Workflow.optional", "path": str(optional)}],
            {
                "Other.file": "/incorrect",
                "Workflow.file": {"path": str(local)},
                "Workflow.optional": None,
            },
            remote_downloader=self.storage,
        )
        self.assertEqual(target.read_text(), "local")
        self.assertFalse(optional.exists())
        self.assertEqual(self.client.downloads, [])

    def execute_remote_fixture(self, *, missing: bool = False) -> dict:
        (self.root / "sequence.fasta").write_text(">synthetic\nACGT\n")
        output_map = {}
        paths = (
            "/remote/cromwell-executions/Workflow/id/report.md",
            f"{self.storage.mount_prefix}/Workflow/id/metrics.json",
            "s3://test-bucket/cromwell/outputs/Workflow/id/normalized.fasta",
        )
        for name, source, data in zip(
            ("report", "metrics", "normalized_fasta"), paths,
            (b"# report\n", b'{"sequence_length": 4}', b">synthetic\nACGT\n"),
        ):
            output_map[f"TemplateWdl.{name}"] = source
            key = self.storage.uri_for_path(source).removeprefix("s3://test-bucket/")
            if not missing:
                self.client.objects["test-bucket", key] = data
        with (
            patch.dict(os.environ, self.env),
            patch("boto3.client", return_value=self.client),
            patch(
                "requests.post",
                return_value=Mock(
                    ok=True,
                    json=lambda: {"id": "workflow-id", "status": "Succeeded"},
                ),
            ) as post,
            patch("requests.get", side_effect=[
                Mock(ok=True, json=lambda: {"status": "Succeeded"}),
                Mock(ok=True, json=lambda: {"outputs": output_map}),
            ]),
        ):
            plan = service.plan(self.root, "template_wdl", {"sequence": "sequence.fasta"}, {})
            result = service.execute_engine(
                self.root,
                service.JobStore(self.root).get(plan["plan_id"]),
            )
        post.assert_called_once()
        return result

    def test_remote_outputs_are_downloaded_validated_and_hashed(self) -> None:
        result = self.execute_remote_fixture()
        self.assertEqual(result["cromwell_status"], "Succeeded")
        self.assertEqual(result["metrics"]["sequence_length"], 4)
        self.assertEqual(len(result["output_storage"]["downloaded"]), 3)
        for item in result["output_records"]:
            path = Path(item["path"])
            self.assertTrue(path.is_relative_to(Path(result["output_dir"])))
            self.assertEqual(item["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
        options = json.loads(Path(result["options_path"]).read_text())
        self.assertEqual(options["final_workflow_outputs_dir"], self.storage.mount_prefix)
        self.assertFalse(options["use_relative_output_paths"])
        manifest = json.loads(
            (Path(result["run_dir"]) / "cromwell.output_downloads.json").read_text()
        )
        self.assertEqual(manifest, result["output_storage"])
        self.assertNotIn("test-secret", json.dumps(result))

    def test_collection_failure_preserves_workflow_success_in_error(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "workflow-id succeeded, but output collection failed"):
            self.execute_remote_fixture(missing=True)

    def test_local_cromwell_requires_remote_output_mount(self) -> None:
        (self.root / "sequence.fasta").write_text(">synthetic\nACGT\n")
        environment = dict(self.env)
        environment.pop("CROMWELL_OUTPUT_STORAGE_MOUNT_PREFIX")
        with (
            patch.dict(os.environ, environment),
            patch("boto3.client", return_value=self.client),
            patch("requests.post") as post,
        ):
            plan = service.plan(self.root, "template_wdl", {"sequence": "sequence.fasta"}, {})
            with self.assertRaisesRegex(ValueError, "CROMWELL_OUTPUT_STORAGE_MOUNT_PREFIX"):
                service.execute_engine(
                    self.root,
                    service.JobStore(self.root).get(plan["plan_id"]),
                )
        post.assert_not_called()

    def test_detached_worker_receives_output_transport_configuration(self) -> None:
        (self.root / "sequence.fasta").write_text(">synthetic\nACGT\n")
        with patch.dict(os.environ, {**self.env, "OPENROUTER_API_KEY": "model-secret"}):
            plan = service.plan(self.root, "template_wdl", {"sequence": "sequence.fasta"}, {})
            with (
                patch.object(service.subprocess, "Popen", return_value=Mock(pid=123)) as popen,
                patch.object(service, "identity", return_value="test-identity"),
                patch.object(service.threading, "Thread"),
            ):
                service.start(self.root, plan["plan_id"])
        worker_env = popen.call_args.kwargs["env"]
        for name, value in self.env.items():
            self.assertEqual(worker_env[name], value)
        self.assertNotIn("OPENROUTER_API_KEY", worker_env)


if __name__ == "__main__":
    unittest.main()
