"""Small, bounded external-tool version probes for provenance."""

from __future__ import annotations

import subprocess
from typing import Sequence


def probe_version(executable: object, prefix_options: Sequence[object] = ()) -> str:
    """Return the first version line, or an explicit unavailable marker."""
    try:
        completed = subprocess.run(
            [str(executable), *[str(item) for item in prefix_options], "--version"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            shell=False,
            check=False,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return "unavailable"
    if completed.returncode != 0:
        return "unavailable"
    lines = [
        line.strip()
        for line in (completed.stdout + "\n" + completed.stderr).splitlines()
        if line.strip()
    ]
    return lines[0][:500] if lines else "unavailable"
