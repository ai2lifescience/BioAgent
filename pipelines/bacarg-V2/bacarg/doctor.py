"""Read-only BacARG deployment diagnostics."""

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
from .database import validate_database


def _check(level: str, name: str, message: str) -> dict[str, str]:
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
            shell=False,
            timeout=10,
            check=False,
        )
        text = (completed.stdout or completed.stderr).strip().splitlines()
        version_text = text[0][:300] if text else "version output unavailable"
    except (OSError, subprocess.SubprocessError) as exc:
        version_text = f"located; version probe warning: {exc}"
    return True, f"{located} ({version_text})"


def run_doctor(config_path: Path | None = None, output: Path | None = None) -> dict[str, Any]:
    """Run checks without downloading or modifying databases."""
    checks: list[dict[str, str]] = []
    checks.append(
        _check(
            "ok" if sys.version_info >= (3, 9) else "error",
            "python",
            sys.version.split()[0],
        )
    )
    try:
        config = load_config(config_path)
        checks.append(_check("ok", "configuration", str(config.source)))
        for name in ("trimmomatic", "reads_mapper", "assembler", "prokka", "abricate"):
            section = config.value("tools", name)
            ok, message = _executable(
                str(section["executable"]),
                [str(item) for item in section.get("prefix_options", [])],
            )
            checks.append(_check("ok" if ok else "error", f"executable:{name}", message))
        try:
            info = validate_database(config)
            checks.append(_check("ok", "database", str(info["directory"])))
        except Exception as exc:
            checks.append(_check("error", "database", str(exc)))
    except Exception as exc:
        checks.append(_check("error", "configuration", str(exc)))
    target = (output or Path.cwd()).expanduser().resolve()
    try:
        target.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(prefix=".bacarg-doctor-", dir=target)
        os.close(descriptor)
        Path(name).unlink()
        checks.append(_check("ok", "output_write", str(target)))
    except OSError as exc:
        checks.append(_check("error", "output_write", str(exc)))
    errors = sum(item["level"] == "error" for item in checks)
    warnings = sum(item["level"] == "warning" for item in checks)
    return {
        "project": "bacarg",
        "version": __version__,
        "ok": errors == 0,
        "error_count": errors,
        "warning_count": warnings,
        "checks": checks,
    }
