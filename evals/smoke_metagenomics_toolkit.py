"""No-Nextflow-install smoke checks for the Metagenomics-Toolkit adapter."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.pipeline_runner.core import run_pipeline
from tools.pipeline_runner.nested import get_config_value, set_config_value


def _fake_nextflow_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
    assert kwargs.get("timeout") is None
    params_path = Path(command[command.index("-params-file") + 1])
    config = yaml.safe_load(params_path.read_text(encoding="utf-8")) or {}
    results_dir = Path(config["output"])
    logs_dir = Path(config["logDir"])
    results_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    (results_dir / "result.tsv").write_text("sample\tstatus\nS1\tok\n", encoding="utf-8")
    ignored_failure = Path(str(kwargs["cwd"])).name == "ignored-failure"
    trace_status = "FAILED" if ignored_failure else "COMPLETED"
    trace_exit = "126" if ignored_failure else "0"
    (logs_dir / "trace.tsv").write_text(
        "status\texit\tprocess\ttag\n"
        f"{trace_status}\t{trace_exit}\twTest:pFastpSplit\tS1\n",
        encoding="utf-8",
    )
    return subprocess.CompletedProcess(command, 0, stdout="toolkit completed\n", stderr="")


def _write_yaml(path: Path, value: dict[str, object]) -> None:
    path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")


def main() -> int:
    nested: dict[str, object] = {}
    set_config_value(nested, "input.paired.sheet", "/data/samples.tsv")
    assert get_config_value(nested, "input.paired.sheet") == "/data/samples.tsv"

    with TemporaryDirectory(prefix="bioagent-metagenomics-") as temporary_dir:
        temporary = Path(temporary_dir)
        source = temporary / "metagenomics-tk"
        source.mkdir()
        (source / "main.nf").write_text("nextflow.enable.dsl=2\nworkflow {}\n", encoding="utf-8")
        (source / "nextflow.config").write_text("profiles { standard {} }\n", encoding="utf-8")

        full_params = temporary / "full.yml"
        _write_yaml(
            full_params,
            {
                "input": {"paired": {"sheet": "/data/samples.tsv"}},
                "steps": {"qc": {"fastp": {"additionalParams": {}}}},
            },
        )
        annotation_params = temporary / "annotation.yml"
        _write_yaml(
            annotation_params,
            {
                "steps": {
                    "annotation": {
                        "input": "/data/bins.tsv",
                        "prokka": {"additionalParams": ""},
                    }
                }
            },
        )

        with patch.dict(os.environ, {"METAGENOMICS_TK_PATH": str(source)}), patch(
            "tools.pipeline_runner.nextflow._nextflow_command",
            return_value=["nextflow-test-double"],
        ), patch(
            "tools.pipeline_runner.nextflow.subprocess.run",
            side_effect=_fake_nextflow_run,
        ):
            full = run_pipeline(
                pipeline_name="metagenomics_toolkit",
                artifact_dir=temporary / "artifacts",
                run_id="full",
                input_overrides={"params_file": str(full_params)},
                config_overrides={"execution_mode": "full"},
            )
            standalone = run_pipeline(
                pipeline_name="metagenomics_toolkit",
                artifact_dir=temporary / "artifacts",
                run_id="annotation",
                input_overrides={"params_file": str(annotation_params)},
                config_overrides={
                    "execution_mode": "standalone",
                    "module": "annotation",
                },
            )

            try:
                run_pipeline(
                    pipeline_name="metagenomics_toolkit",
                    artifact_dir=temporary / "artifacts",
                    run_id="ignored-failure",
                    input_overrides={"params_file": str(annotation_params)},
                    config_overrides={
                        "execution_mode": "standalone",
                        "module": "annotation",
                    },
                )
            except RuntimeError as exc:
                assert "ignored by the upstream retry policy" in str(exc)
                assert "exit 126" in str(exc)
            else:
                raise AssertionError("An ignored Nextflow task failure was reported as success.")

            invalid_params = temporary / "invalid.yml"
            _write_yaml(
                invalid_params,
                {"steps": {"annotation": {}, "qc": {}}},
            )
            try:
                run_pipeline(
                    pipeline_name="metagenomics_toolkit",
                    artifact_dir=temporary / "artifacts",
                    run_id="invalid",
                    input_overrides={"params_file": str(invalid_params)},
                    config_overrides={
                        "execution_mode": "standalone",
                        "module": "annotation",
                    },
                )
            except ValueError as exc:
                assert "only 'annotation'" in str(exc)
            else:
                raise AssertionError("Standalone execution accepted multiple step modules.")

            try:
                run_pipeline(
                    pipeline_name="metagenomics_toolkit",
                    artifact_dir=temporary / "artifacts",
                    run_id="multiple-modules",
                    input_overrides={"params_file": str(annotation_params)},
                    config_overrides={
                        "execution_mode": "standalone",
                        "module": ["annotation", "qc"],
                    },
                )
            except ValueError as exc:
                assert "exactly one named module" in str(exc)
            else:
                raise AssertionError("Standalone execution accepted multiple module names.")

        assert full["entry"] == "wFullPipeline"
        assert standalone["entry"] == "wAnnotate"
        assert full["timeout"] is None
        assert standalone["timeout"] is None
        assert full["profile"] == "standard"
        assert full["nextflow_version"] == "25.10.4"
        assert "-resume" in full["command"]
        assert full["command"][-2:] == ["--publishDirMode", "copy"]
        assert full["metrics"]["execution_mode"] == "full"
        assert standalone["metrics"]["module"] == "annotation"
        assert Path(full["report_path"]).is_file()
        assert Path(standalone["metrics_path"]).is_file()
        assert json.loads(Path(standalone["metrics_path"]).read_text(encoding="utf-8"))[
            "entry"
        ] == "wAnnotate"
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
