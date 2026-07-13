"""Runtime context passed into skill workflows."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from execution.tool_executor import ToolExecutor


@dataclass
class SkillContext:
    """Give a skill controlled access to tool execution."""

    skill_name: str
    allowed_tools: tuple[str, ...]
    tool_executor: ToolExecutor
    user_context: dict[str, Any] | None = None
    log_fn: Callable[[str], None] | None = None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)

    @property
    def run_id(self) -> str | None:
        return str((self.user_context or {}).get("run_id") or "") or None

    @property
    def runtime_dir(self) -> str | None:
        return str((self.user_context or {}).get("runtime_dir") or "") or None

    @property
    def session_dir(self) -> str | None:
        return str((self.user_context or {}).get("session_dir") or "") or None

    @property
    def artifact_dir(self) -> str | None:
        return str((self.user_context or {}).get("artifact_dir") or "") or None

    @property
    def artifacts(self) -> list[dict[str, Any]]:
        artifacts = (self.user_context or {}).get("artifacts") or []
        return [dict(item) for item in artifacts if isinstance(item, dict)]

    def runtime_path(self, *parts: str) -> str:
        base = Path(self.runtime_dir or "runtime")
        return str(base.joinpath(*parts))

    def artifact_path(self, *parts: str) -> str:
        base = Path(self.artifact_dir or self.runtime_path("artifacts"))
        return str(base.joinpath(*parts))

    def latest_artifact(
        self,
        kinds: tuple[str, ...] = (),
        suffixes: tuple[str, ...] = (),
    ) -> dict[str, Any] | None:
        clean_suffixes = tuple(suffix.lower() for suffix in suffixes)
        for artifact in reversed(self.artifacts):
            path = str(artifact.get("path") or "")
            if kinds and artifact.get("kind") not in kinds:
                continue
            if clean_suffixes and not path.lower().endswith(clean_suffixes):
                continue
            return artifact
        return None

    def run_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = dict(arguments or {})
        self._log(f"[tool] Started {tool_name}{_format_arguments(payload)}.")
        record = self.tool_executor.execute_tool(
            skill_name=self.skill_name,
            tool_name=tool_name,
            arguments=payload,
            allowed_tools=self.allowed_tools,
            user_context=self.user_context,
        )
        self.tool_calls.append(record)
        if record.get("status") == "error":
            self._log(f"[tool] Failed {tool_name}: {record.get('error')}")
            raise RuntimeError(str(record.get("error") or f"Tool {tool_name} failed."))
        self._log(f"[tool] Finished {tool_name}{_format_tool_summary(record)}.")
        return record

    def _log(self, message: str) -> None:
        if self.log_fn:
            self.log_fn(message)


def ensure_skill_context(
    context: SkillContext | None,
    skill_name: str,
) -> SkillContext:
    if context is None:
        raise RuntimeError(
            f"Skill {skill_name} requires a SkillContext. "
            "Run the skill through SkillExecutor or pass a context explicitly."
        )
    if context.skill_name != skill_name:
        raise RuntimeError(
            f"SkillContext for {context.skill_name} cannot run skill {skill_name}."
        )
    return context


def _format_arguments(arguments: dict[str, Any]) -> str:
    shown_keys = (
        "pipeline_name",
        "input_path",
        "output_dir",
        "label",
        "db",
        "term",
        "terms",
        "genes",
        "accessions",
        "pdb_id",
        "file_format",
        "structure_path",
        "max_records",
        "collection_name",
        "top_k",
        "dry_run",
        "cores",
    )
    parts = [
        f"{key}={_compact_value(arguments[key])}"
        for key in shown_keys
        if key in arguments and arguments[key] not in (None, "", [])
    ]
    if not parts:
        return ""
    return " | " + ", ".join(parts[:6])


def _format_tool_summary(record: dict[str, Any]) -> str:
    result = record.get("result")
    if not isinstance(result, dict):
        return ""

    parts: list[str] = []
    for key in (
        "status",
        "matched_count",
        "downloaded_count",
        "record_count",
        "source_count",
        "chunk_count",
        "citation_count",
        "hit_count",
        "atom_count",
        "chain_count",
        "residue_count",
        "ligand_count",
        "model_count",
        "genome_length",
        "feature_count",
        "gene_count",
        "cds_count",
        "orf_count",
        "bytes",
        "returncode",
        "collection_name",
        "rid",
    ):
        if key in result and result[key] not in (None, "", []):
            parts.append(f"{key}={_compact_value(result[key])}")

    files = result.get("files")
    if isinstance(files, list):
        parts.append(f"files={len(files)}")
    for key in ("structure_path", "image_path", "genome_map_path", "report_path", "output_dir", "config_path"):
        if key in result and result[key]:
            parts.append(f"{key}={_compact_value(result[key])}")

    if not parts:
        return ""
    return " | " + ", ".join(parts[:8])


def _compact_value(value: Any, limit: int = 80) -> str:
    if isinstance(value, list):
        if len(value) <= 3:
            text = ", ".join(str(item) for item in value)
        else:
            text = f"{len(value)} items"
    else:
        text = str(value)
    text = " ".join(text.split())
    if len(text) > limit:
        return f"{text[:limit - 3]}..."
    return text
