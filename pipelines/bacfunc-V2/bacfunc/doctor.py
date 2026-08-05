"""Read-only BacFunc deployment diagnostics."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from . import __version__
from .config import load_config
from .eggnog import validate_database_path


def _item(level: str, name: str, message: str) -> dict[str, str]:
    return {"level": level, "name": name, "message": message}


def _executable(executable: str, prefix_options: list[str]) -> tuple[bool, str]:
    located = shutil.which(executable)
    if located is None and Path(executable).is_file():
        located = str(Path(executable).resolve())
    if located is None:
        return False, f"not found: {executable}"
    try:
        completed = subprocess.run(
            [located, *prefix_options, "--version"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
            shell=False,
            timeout=10,
        )
        lines = (completed.stdout or completed.stderr).strip().splitlines()
        detail = lines[0][:300] if lines else "version output unavailable"
    except (OSError, subprocess.SubprocessError) as exc:
        detail = f"located; version probe warning: {exc}"
    return True, f"{located} ({detail})"


def run_doctor(config_path: Path | None = None, output: Path | None = None) -> dict[str, Any]:
    """Check Python, configuration, tools, four eggNOG files, and output writes."""
    checks = [
        _item(
            "ok" if sys.version_info >= (3, 9) else "error",
            "python",
            sys.version.split()[0],
        )
    ]
    try:
        config = load_config(config_path)
        checks.append(_item("ok", "configuration", str(config.source)))
        for name in ("trimmomatic", "reads_search", "assembler", "prokka", "eggnog"):
            section = config.value("tools", name)
            ok, message = _executable(
                str(section["executable"]),
                [str(value) for value in section.get("prefix_options", [])],
            )
            checks.append(_item("ok" if ok else "error", f"executable:{name}", message))
        try:
            info = validate_database_path(config.eggnog_path("data_dir"))
            checks.append(
                _item(
                    "ok",
                    "database",
                    f"eggNOG detected version: {info['detected_version']}",
                )
            )
        except Exception as exc:
            checks.append(_item("error", "database", str(exc)))
    except Exception as exc:
        checks.append(_item("error", "configuration", str(exc)))
    target = (output or Path.cwd()).expanduser().resolve()
    try:
        target.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(prefix=".bacfunc-doctor-", dir=target)
        os.close(descriptor)
        Path(name).unlink()
        checks.append(_item("ok", "output_write", str(target)))
    except OSError as exc:
        checks.append(_item("error", "output_write", str(exc)))
    errors = sum(check["level"] == "error" for check in checks)
    warnings = sum(check["level"] == "warning" for check in checks)
    return {
        "project": "bacfunc",
        "version": __version__,
        "ok": errors == 0,
        "error_count": errors,
        "warning_count": warnings,
        "checks": checks,
    }
