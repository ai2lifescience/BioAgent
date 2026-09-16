"""Regression checks for compact manifests and optional native workflow files."""
from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.runtime_tools.pipeline_runtime.engine.config import load_pipeline_config
from tools.runtime_tools.pipeline_runtime.engine.runner import prepare_pipeline_context
from tools.runtime_tools.pipeline_runtime.engine.wdl import write_wdl_inputs, write_wdl_options
from tools.runtime_tools.pipeline_runtime import service


class PipelineConfigChecks(unittest.TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory(prefix="bioagent-config-")
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
        bundle = PROJECT_ROOT / "tools/runtime_tools/pipelines/generic_wdl"
        before = {name: (bundle / name).read_bytes() for name in ("inputs.json", "options.json")}
        selected = self.root / "selected.fasta"
        selected.write_text(">synthetic\nACGT\n", encoding="utf-8")
        context = prepare_pipeline_context(
            pipeline_name="generic_wdl", artifact_dir=str(self.root),
            input_overrides={"sequence": str(selected)},
        )
        inputs = json.loads(write_wdl_inputs(context).read_text())
        expected = json.loads(before["inputs.json"])
        expected["GenericWdl.input_fasta"] = str(selected)
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
        manifest["defaults"] = {"GenericWdl.label": "compact"}
        config, source = load_pipeline_config(self.root, manifest)
        optional = replace(context, runner_config=manifest, raw_config=config, raw_config_path=source)
        self.assertIsNone(write_wdl_options(optional))
        self.assertEqual(json.loads(write_wdl_inputs(optional).read_text()), {
            "GenericWdl.label": "compact", "GenericWdl.input_fasta": str(selected),
        })
        missing = replace(context, runner_config={**manifest, "options_json": "missing.json"})
        with self.assertRaises(FileNotFoundError):
            write_wdl_options(missing)

    def test_catalog_defaults_and_explicit_inputs(self) -> None:
        catalog = {item["name"]: item for item in service.catalog()}
        self.assertTrue(all("error" not in item for item in catalog.values()), catalog)
        self.assertEqual(catalog["example_sequence_qc"]["parameters"]["min_length"], 6)
        for name in ("example_sequence_qc", "generic_wdl"):
            result = service.plan(self.root, name, {}, {})
            self.assertEqual(result["status"], "needs_input")


if __name__ == "__main__":
    unittest.main()
