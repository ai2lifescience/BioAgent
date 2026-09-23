"""Regression checks for compact manifests and optional native workflow files."""
from __future__ import annotations

from dataclasses import replace
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.infrastructure.pipeline_engine.engine.config import load_pipeline_config
from tools.infrastructure.pipeline_engine.engine.runner import prepare_pipeline_context
from tools.infrastructure.pipeline_engine.engine.wdl import write_wdl_inputs, write_wdl_options
from tools.infrastructure.pipeline_engine import service


class PipelineConfigChecks(unittest.TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory(prefix="agent-config-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def manifest(self, values: dict) -> None:
        (self.root / "runner.yaml").write_text(yaml.safe_dump(values), encoding="utf-8")

    def test_manifest_only(self) -> None:
        self.manifest({"params": {"min_length": 12}, "defaults": {"label": "demo"}})
        config, source = load_pipeline_config(self.root)
        self.assertEqual(config, {"params": {"min_length": 12}, "label": "demo"})
        self.assertEqual(source, self.root / "runner.yaml")

    def test_native_config_merge_precedence(self) -> None:
        native = self.root / "config.yaml"
        native.write_text(yaml.safe_dump({
            "params": {"min_length": 4, "native_only": True},
            "nested": {"retained": 1, "choice": "native"},
        }), encoding="utf-8")
        before = native.read_bytes()
        manifest = {
            "defaults": {"params": {"min_length": 8}, "nested": {"choice": "manifest"}},
            "params": {"min_length": 12},
        }
        self.manifest(manifest)
        config, source = load_pipeline_config(self.root)
        self.assertEqual(source, native)
        self.assertEqual(config["params"], {"min_length": 12, "native_only": True})
        self.assertEqual(config["nested"], {"retained": 1, "choice": "manifest"})
        self.assertEqual(native.read_bytes(), before)
        # Callers can mutate runtime values without changing the loaded manifest.
        config, _ = load_pipeline_config(self.root, manifest)
        config["nested"]["choice"] = "runtime"
        self.assertEqual(manifest["defaults"]["nested"]["choice"], "manifest")

    def test_explicit_native_files(self) -> None:
        native = self.root / "inputs.json"
        native.write_text('{"Workflow.label": "native"}', encoding="utf-8")
        for key in ("config", "config_file", "config_path", "inputs_json", "inputs_file"):
            with self.subTest(key=key):
                self.manifest({key: "inputs.json", "defaults": {"Workflow.label": "override"}})
                config, source = load_pipeline_config(self.root)
                self.assertEqual(config, {"Workflow.label": "override"})
                self.assertEqual(source, native)
        self.assertEqual(json.loads(native.read_text()), {"Workflow.label": "native"})

    def test_invalid_config_rejected(self) -> None:
        for field in ("defaults", "params"):
            for value in (None, [], "invalid"):
                with self.subTest(field=field, value=value):
                    self.manifest({field: value})
                    with self.assertRaisesRegex(ValueError, "must be a mapping"):
                        load_pipeline_config(self.root)
        for key in ("config", "inputs_json"):
            self.manifest({key: "missing.json"})
            with self.assertRaises(FileNotFoundError):
                load_pipeline_config(self.root)
            self.manifest({key: "../outside.json"})
            with self.assertRaisesRegex(ValueError, "must stay inside"):
                load_pipeline_config(self.root)

    def test_wdl_native_files_preserved_during_runtime_generation(self) -> None:
        bundle = PROJECT_ROOT / "tools/runtime_tools/pipelines/template_wdl"
        before = {name: (bundle / name).read_bytes() for name in ("inputs.json", "options.json")}
        selected = self.root / "selected.fasta"
        selected.write_text(">synthetic\nACGT\n", encoding="utf-8")
        context = prepare_pipeline_context(
            pipeline_name="template_wdl", artifact_dir=str(self.root),
            input_overrides={"sequence": str(selected)},
        )
        inputs = json.loads(write_wdl_inputs(context).read_text())
        expected = json.loads(before["inputs.json"])
        expected["TemplateWdl.input_fasta"] = str(selected)
        self.assertEqual(inputs, expected)
        options_path = write_wdl_options(context)
        self.assertIsNotNone(options_path)
        options = json.loads(options_path.read_text())
        expected_options = json.loads(before["options.json"])
        expected_options["final_workflow_outputs_dir"] = str(context.run_dir / "output")
        self.assertEqual(options, expected_options)
        self.assertEqual(before, {name: (bundle / name).read_bytes() for name in before})

        # Neither native file is mandatory: WDL defaults can live in the manifest.
        manifest = {key: value for key, value in context.runner_config.items()
                    if key not in {"inputs_json", "options_json"}}
        manifest["defaults"] = {"TemplateWdl.label": "compact"}
        config, source = load_pipeline_config(self.root, manifest)
        optional = replace(context, runner_config=manifest, raw_config=config, raw_config_path=source)
        self.assertIsNone(write_wdl_options(optional))
        self.assertEqual(json.loads(write_wdl_inputs(optional).read_text()), {
            "TemplateWdl.label": "compact", "TemplateWdl.input_fasta": str(selected),
        })
        missing = replace(context, runner_config={**manifest, "options_json": "missing.json"})
        with self.assertRaises(FileNotFoundError):
            write_wdl_options(missing)

    def test_catalog_defaults_and_explicit_inputs(self) -> None:
        catalog = {item["name"]: item for item in service.catalog()}
        self.assertTrue(all("error" not in item for item in catalog.values()), catalog)
        self.assertEqual(catalog["template_shell"]["parameters"]["normalize_mode"], "whitespace")
        for name in ("template_shell", "template_wdl"):
            result = service.plan(self.root, name, {}, {})
            self.assertEqual(result["status"], "needs_input")

    def test_wdl_backend_is_selected_at_plan_time(self) -> None:
        (self.root / "sequence.fasta").write_text(">synthetic\nACGT\n", encoding="utf-8")
        (self.root / "reads.fastq").write_text("@synthetic\nACGT\n+\nIIII\n", encoding="utf-8")
        for name, inputs in (
            ("template_wdl", {"sequence": "sequence.fasta"}),
            ("metagenomic_de_novo_assembly", {"read1": "reads.fastq"}),
        ):
            for url in (None, "", "  ", " http://192.168.164.39:39000/ "):
                with self.subTest(pipeline=name, url=url), patch.dict(os.environ, {}, clear=True):
                    remote = bool(url and url.strip())
                    # Obsolete selectors must not override the URL-based choice.
                    os.environ["AGENT_WDL_ENGINE"] = "local" if remote else "remote"
                    os.environ["WDL_ENGINE"] = "miniwdl" if remote else "cromwell"
                    if url is not None:
                        os.environ["CROMWELL_URL"] = url
                    plan = service.plan(self.root, name, inputs, {})["plan"]
                    self.assertEqual(plan["wdl_engine"], "cromwell" if remote else "miniwdl")
                    if remote:
                        self.assertEqual(plan["cromwell_url"], "http://192.168.164.39:39000")
                    else:
                        self.assertNotIn("cromwell_url", plan)

    def test_invalid_cromwell_url_is_rejected_before_saving_plan(self) -> None:
        (self.root / "sequence.fasta").write_text(">synthetic\nACGT\n", encoding="utf-8")
        for url in ("ftp://host", "http://", "http://host:invalid", "http://host:99999", "http://bad host"):
            with self.subTest(url=url), patch.dict(os.environ, {"CROMWELL_URL": url}, clear=True):
                with self.assertRaisesRegex(ValueError, "Cromwell URL"):
                    service.plan(self.root, "template_wdl", {"sequence": "sequence.fasta"}, {})
        self.assertEqual(service.JobStore(self.root).list(), [])

    def wdl_output_fixture(self) -> dict[str, str]:
        outputs = {}
        directory = self.root / "engine-results"
        directory.mkdir(exist_ok=True)
        for key, filename, contents in (
            ("report", "report.md", "# WDL fixture\n"),
            ("metrics", "metrics.json", '{"sequence_length": 4}'),
            ("normalized_fasta", "normalized.fasta", ">synthetic\nACGT\n"),
        ):
            path = directory / filename
            path.write_text(contents, encoding="utf-8")
            outputs[f"TemplateWdl.{key}"] = str(path)
        return outputs

    def test_saved_local_plan_stays_local_when_url_is_added(self) -> None:
        inputs = {"sequence": "sequence.fasta"}
        (self.root / inputs["sequence"]).write_text(">synthetic\nACGT\n", encoding="utf-8")
        output_map = self.wdl_output_fixture()

        def miniwdl_run(command, **kwargs):
            self.assertEqual(command[:2], ["miniwdl", "run"])
            Path(command[command.index("-o") + 1]).write_text(json.dumps({"outputs": output_map}))
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

        with patch.dict(os.environ, {}, clear=True):
            plan = service.plan(self.root, "template_wdl", inputs, {})
            record = service.JobStore(self.root).get(plan["plan_id"])
            os.environ["CROMWELL_URL"] = "http://changed.invalid:39000"
            with (
                patch("tools.infrastructure.pipeline_engine.engine.wdl.miniwdl_executable", return_value="miniwdl"),
                patch("tools.infrastructure.pipeline_engine.engine.wdl.subprocess.run", side_effect=miniwdl_run),
                patch("requests.post", side_effect=AssertionError("Local execution must not submit to Cromwell")),
            ):
                result = service.execute_engine(self.root, record)
        self.assertEqual(result["wdl_engine"], "miniwdl")
        self.assertEqual(result["metrics"]["sequence_length"], 4)
        self.assertTrue(all(item.get("sha256") for item in result["output_records"]))

    def test_saved_remote_plan_keeps_endpoint_when_environment_changes(self) -> None:
        inputs = {"sequence": "sequence.fasta"}
        (self.root / inputs["sequence"]).write_text(">synthetic\nACGT\n", encoding="utf-8")
        output_map = self.wdl_output_fixture()
        endpoint = "http://planned.invalid:39000"
        for later_url in (None, "http://changed.invalid:39000"):
            with self.subTest(later_url=later_url), patch.dict(os.environ, {"CROMWELL_URL": endpoint}, clear=True):
                plan = service.plan(self.root, "template_wdl", inputs, {})
                record = service.JobStore(self.root).get(plan["plan_id"])
                os.environ.pop("CROMWELL_URL")
                if later_url:
                    os.environ["CROMWELL_URL"] = later_url
                with (
                    patch("requests.post", return_value=Mock(ok=True, json=lambda: {"id": "workflow-id", "status": "Succeeded"})) as post,
                    patch("requests.get", side_effect=[
                        Mock(ok=True, json=lambda: {"status": "Succeeded"}),
                        Mock(ok=True, json=lambda: {"outputs": output_map}),
                    ]) as get,
                    patch("tools.infrastructure.pipeline_engine.engine.wdl.miniwdl_executable", side_effect=AssertionError("Remote execution must not start miniwdl")),
                ):
                    result = service.execute_engine(self.root, record)
                self.assertEqual(post.call_args.args[0], f"{endpoint}/api/workflows/v1")
                self.assertEqual([call.args[0] for call in get.call_args_list], [
                    f"{endpoint}/api/workflows/v1/workflow-id/metadata",
                    f"{endpoint}/api/workflows/v1/workflow-id/outputs",
                ])
                self.assertEqual(result["wdl_engine"], "cromwell")
                self.assertEqual(result["cromwell_url"], endpoint)
                self.assertEqual(result["metrics"]["sequence_length"], 4)
                self.assertTrue(all(item.get("sha256") for item in result["output_records"]))


if __name__ == "__main__":
    unittest.main()
