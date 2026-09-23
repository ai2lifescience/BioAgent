"""WDL backend selection shared by planning and execution."""

from __future__ import annotations

import os
from typing import Any


_ENGINE_ALIASES = {
    "local": "miniwdl",
    "miniwdl": "miniwdl",
    "mini-wdl": "miniwdl",
    "remote": "cromwell",
    "cromwell": "cromwell",
}


def resolve_wdl_engine() -> str:
    """Use local miniwdl unless the operator configures a Cromwell endpoint."""
    return "cromwell" if os.environ.get("CROMWELL_URL", "").strip() else "miniwdl"


def normalize_wdl_engine(value: Any) -> str:
    """Normalize a previously resolved backend stored in a plan."""
    requested = str(value or "").strip().lower()
    selected = _ENGINE_ALIASES.get(requested)
    if selected is None:
        raise ValueError(f"Unsupported WDL engine '{requested}'.")
    return selected
