"""Independent per-sample batch orchestration."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

from .input import InputSet
from .pipeline import run_pipeline


def run_samples(
    samples: Sequence[InputSet],
    output: Path,
    *,
    config_path: Path | None = None,
    dry_run: bool = False,
    threads: int | None = None,
) -> list[dict[str, Any]]:
    """Run one or more samples without combining their biological inputs."""
    if not samples:
        raise ValueError("At least one validated sample is required.")
    root = Path(output).expanduser().resolve()
    multiple = len(samples) > 1
    if multiple:
        root.mkdir(parents=True, exist_ok=True)
    statuses: list[dict[str, Any]] = []
    for sample in samples:
        target = root / sample.sample_id if multiple else root
        statuses.append(
            run_pipeline(
                sample.files,
                target,
                sample_id=sample.sample_id,
                config_path=config_path,
                dry_run=dry_run,
                threads=threads,
                input_type=sample.input_type,
                analysis_mode=sample.analysis_mode,
            )
        )
    return statuses
