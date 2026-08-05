"""Safe external command execution with auditable argument boundaries."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional, Sequence

from .errors import ExternalToolError


@dataclass
class CommandRunner:
    """Execute or plan subprocess calls without a shell."""

    dry_run: bool = False
    commands: list[list[str]] = field(default_factory=list)

    def run(
        self,
        command: Sequence[object],
        *,
        tool: str,
        log_path: Path,
        stdout_path: Optional[Path] = None,
    ) -> int:
        """Run one command and stream output directly to files."""
        args = [str(part) for part in command]
        if not args:
            raise ExternalToolError(f"{tool} command is empty.")
        self.commands.append(args)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8", newline="\n") as log:
            log.write(f"START {tool}\n")
            log.write("COMMAND " + json.dumps(args, ensure_ascii=False) + "\n")
            if self.dry_run:
                log.write(f"END {tool} dry-run\n")
                return 0
            output_handle = None
            try:
                if stdout_path is not None:
                    stdout_path.parent.mkdir(parents=True, exist_ok=True)
                    output_handle = stdout_path.open("w", encoding="utf-8", newline="\n")
                completed = subprocess.run(
                    args,
                    stdin=subprocess.DEVNULL,
                    stdout=output_handle if output_handle is not None else log,
                    stderr=log,
                    check=False,
                    shell=False,
                    text=True,
                )
            except OSError as exc:
                log.write(f"ERROR {exc}\n")
                raise ExternalToolError(
                    f"{tool} could not be started; see log: {log_path}"
                ) from exc
            finally:
                if output_handle is not None:
                    output_handle.close()
            log.write(f"EXIT_CODE {completed.returncode}\n")
            log.write(f"END {tool}\n")
        if completed.returncode != 0:
            raise ExternalToolError(
                f"{tool} failed with exit code {completed.returncode}; see log: {log_path}"
            )
        return completed.returncode


def render_commands(commands: Iterable[Sequence[str]]) -> list[list[str]]:
    """Return JSON-safe command argument lists."""
    return [[str(part) for part in command] for command in commands]
