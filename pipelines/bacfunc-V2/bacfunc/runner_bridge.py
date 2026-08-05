"""Small helpers for Agent runtime YAML inputs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .errors import ConfigurationError


def read_runtime(path: Path, mode: str = "auto") -> tuple[list[Path], Path, str | None]:
    """Translate an Agent runtime YAML into explicit CLI-equivalent values."""
    with path.open("r", encoding="utf-8") as handle:
        data: Any = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ConfigurationError("Runner runtime YAML must be a mapping.")
    base = path.resolve().parent
    inputs = data.get("inputs", {})
    outputs = data.get("outputs", {})
    if not isinstance(inputs, dict) or not isinstance(outputs, dict):
        raise ConfigurationError("Runner inputs and outputs must be mappings.")
    if mode == "fasta":
        raw_files = [inputs.get("assembly")]
    elif mode == "fastq":
        raw_files = [inputs.get("read1"), inputs.get("read2")]
    else:
        raw = inputs.get("sequences")
        raw_files = raw if isinstance(raw, list) else [raw]
    files = [
        (base / str(item)).resolve() if not Path(str(item)).is_absolute() else Path(str(item)).resolve()
        for item in raw_files
        if item
    ]
    raw_output = outputs.get("directory") or data.get("output")
    if not raw_output:
        raise ConfigurationError("Runner runtime YAML is missing outputs.directory.")
    output = Path(str(raw_output))
    if not output.is_absolute():
        output = base / output
    return files, output.resolve(), data.get("sample_id")
