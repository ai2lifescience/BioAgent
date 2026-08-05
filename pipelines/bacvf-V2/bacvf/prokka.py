"""Metagenome-aware Prokka orchestration."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from .command import CommandRunner
from .config import PipelineConfig
from .errors import ExternalToolError


@dataclass(frozen=True)
class ProkkaResult:
    """Required Prokka outputs."""

    faa: Path
    ffn: Path
    gff: Path
    tsv: Path
    txt: Path


def prokka_command(
    assembly: Path, output_dir: Path, prefix: str, config: PipelineConfig
) -> list[str]:
    """Build a configured Prokka command and enforce metagenome mode."""
    tool = config.value("tools", "prokka")
    options = [str(item) for item in tool.get("options", [])]
    if "--metagenome" not in options:
        raise ValueError("Prokka options must include --metagenome.")
    return [
        str(tool["executable"]), *[str(item) for item in tool.get("prefix_options", [])],
        *options, "--cpus", str(config.threads), "--outdir", str(output_dir),
        "--prefix", prefix, str(assembly),
    ]


def run_prokka(
    assembly: Path,
    work_dir: Path,
    raw_dir: Path,
    sample_id: str,
    config: PipelineConfig,
    runner: CommandRunner,
) -> ProkkaResult:
    """Run Prokka, validate outputs, and retain them under raw/prokka."""
    output_dir = work_dir / "prokka"
    runner.run(
        prokka_command(assembly, output_dir, sample_id, config),
        tool="Prokka",
        log_path=work_dir.parent / "logs" / "prokka.log",
    )
    result = ProkkaResult(
        faa=output_dir / f"{sample_id}.faa",
        ffn=output_dir / f"{sample_id}.ffn",
        gff=output_dir / f"{sample_id}.gff",
        tsv=output_dir / f"{sample_id}.tsv",
        txt=output_dir / f"{sample_id}.txt",
    )
    if not runner.dry_run:
        for path in result.__dict__.values():
            if not path.is_file() or path.stat().st_size == 0:
                raise ExternalToolError(f"Prokka required output is missing or empty: {path}")
        retained = raw_dir / "prokka"
        retained.mkdir(parents=True, exist_ok=True)
        for path in result.__dict__.values():
            shutil.copy2(path, retained / path.name)
    return result
