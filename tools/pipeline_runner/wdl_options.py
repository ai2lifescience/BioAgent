"""WDL engine options helpers.

BioAgent keeps `runner.yaml` as the output contract. This module only prepares
engine-specific options files, such as Cromwell `options.json`, for runtime use.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any


CROMWELL_OUTPUT_DIR_KEY = "final_workflow_outputs_dir"


def read_options_json(path: Path) -> dict[str, Any]:
    """Read a WDL engine options JSON file."""
    options = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(options, dict):
        raise ValueError(f"WDL options file must contain a JSON object: {path}")
    return options


def rewrite_cromwell_output_dir(
    options: dict[str, Any],
    run_dir: Path,
) -> dict[str, Any]:
    """Rewrite relative Cromwell output directories under the BioAgent run dir."""
    rewritten = copy.deepcopy(options)
    output_dir = rewritten.get(CROMWELL_OUTPUT_DIR_KEY)
    if not isinstance(output_dir, str) or not output_dir.strip():
        return rewritten

    output_path = Path(output_dir).expanduser()
    if output_path.is_absolute():
        rewritten[CROMWELL_OUTPUT_DIR_KEY] = str(output_path.resolve())
    else:
        rewritten[CROMWELL_OUTPUT_DIR_KEY] = str((run_dir / output_path).resolve())
    return rewritten


def write_options_runtime_json(
    source: Path,
    target: Path,
    run_dir: Path,
) -> Path:
    """Write runtime WDL options for provenance and future Cromwell use."""
    options = read_options_json(source)
    runtime_options = rewrite_cromwell_output_dir(options, run_dir)
    target.write_text(json.dumps(runtime_options, indent=2) + "\n", encoding="utf-8")
    return target
