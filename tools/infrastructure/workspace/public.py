"""Project host-side results into the public workspace-relative path contract.

Apply at model/API boundaries, never to arguments used by deterministic writers.
Internal paths outside the active workspace are redacted, not made addressable.
"""
from __future__ import annotations

from pathlib import Path
import re
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
INTERNAL_PATH = "[internal path]"
INTERNAL_RELATIVE_PATH = re.compile(
    r"(?<![\w/])(?:runtime|tools/runtime_tools|harness|interfaces)/"
    r"(?:[\w.~-]+/)*[\w.~-]+"
)
# Match URLs first so paths within citations are preserved. Also cover paths in
# exception messages, quoted commands, and logs, not just fields named *_path.
PATH_TOKEN = re.compile(
    r"https?://[^\s<>\"'`]+|"
    r"(?<![\w:/])(?:/[\w.~-]+){2,}(?:[\w./~+@%=-]*)|"
    r"[A-Za-z]:\\(?:[^\s<>\"'`]+)"
)


def public_payload(value: Any, workspace_root: Path | str | None = None) -> Any:
    """Return a JSON-compatible copy without exposing host filesystem locations."""
    root = Path(workspace_root).resolve() if workspace_root else None
    aliases = [str(root)] if root else []
    if root and root.is_relative_to(PROJECT_ROOT):
        aliases.append(root.relative_to(PROJECT_ROOT).as_posix())

    def text(raw: str) -> str:
        # Preserve token-boundary whitespace so streamed deltas can be joined
        # without changing the user's text when an internal path is redacted.
        leading_count = len(raw) - len(raw.lstrip())
        trailing_count = len(raw) - len(raw.rstrip())
        if leading_count + trailing_count >= len(raw):
            return raw
        leading = raw[:leading_count]
        trailing = raw[len(raw) - trailing_count:] if trailing_count else ""
        raw = raw[leading_count: len(raw) - trailing_count if trailing_count else None]
        for prefix in sorted(aliases, key=len, reverse=True):
            if raw == prefix:
                return leading + "." + trailing
            # A path produced by an internal writer is safe to expose as a
            # workspace-relative path. Do this before generic absolute-path
            # redaction, which would otherwise turn ``<root>/outputs/x``
            # into ``[internal path]`` after the prefix is removed.
            if raw.startswith(prefix + "/"):
                return leading + raw[len(prefix) + 1:] + trailing
            # Repository-relative paths and absolute workspace paths can also
            # occur inside a short status message.
            raw = re.sub(r"(?<![\w/])" + re.escape(prefix) + r"/", "", raw)
        if raw.startswith("/") and not raw.startswith("//") and "\n" not in raw:
            return leading + INTERNAL_PATH + trailing
        raw = INTERNAL_RELATIVE_PATH.sub(INTERNAL_PATH, raw)
        transformed = PATH_TOKEN.sub(
            lambda match: match.group() if match.group().startswith(("https://", "http://")) else INTERNAL_PATH,
            raw,
        )
        return leading + transformed + trailing

    def visit(item: Any) -> Any:
        if isinstance(item, dict):
            return {text(str(key)): visit(child) for key, child in item.items()}
        if isinstance(item, (list, tuple)):
            return [visit(child) for child in item]
        if isinstance(item, Path):
            return text(str(item))
        if isinstance(item, str):
            return text(item)
        return item

    return visit(value)
