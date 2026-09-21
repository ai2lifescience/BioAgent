"""Agents SDK local ShellTool for the Pipeline2Agent pipeline command protocol."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from agents import ShellTool
from agents.tool import ShellCommandRequest, ShellCommandOutput, ShellResult, ShellCallOutcome

from tools.infrastructure.pipeline_runtime.commands import dispatch, parse_command
from tools.infrastructure.pipeline_runtime.store import JobStore

PIPELINE_INSTRUCTIONS = """
Use pipeline_shell (the SDK local shell tool) for pipeline operations. Its only
command is agent-pipeline; Bash expressions, arbitrary commands, and redirects
are not supported. Issue ONE command per call. Shell action timeout_ms is in
milliseconds; --timeout is the pipeline deadline in seconds.
Pipeline catalog entries declare a container boundary and own their workflow
dependencies. Do not suggest installing pipeline dependencies into the agent
environment.

Commands:
- agent-pipeline catalog : discover intent-focused pipeline names, descriptions,
  use cases, limitations, inputs, parameters, and outputs.
- agent-pipeline files : discover session workspace-relative input paths.
- agent-pipeline example --pipeline template_shell : stage bundled internal
  demonstration data, only when the user requested a demonstration/example.
- agent-pipeline plan --pipeline NAME --input SLOT=WORKSPACE_PATH
  [--input OTHER_SLOT=PATH] [--param NAME=JSON_OR_TEXT] [--cores N]
  [--timeout SECONDS] [--dry-run]. Quote tokens containing spaces. For array inputs,
  pass a JSON array, e.g. --input 'reads=["uploads/a.fa","uploads/b.fa"]'.
- agent-pipeline run --plan-id ID : start the exact saved plan (SDK approval).
- agent-pipeline jobs : list previous jobs in this session.
- agent-pipeline status --job-id ID : status and log paths.
- agent-pipeline wait --job-id ID --seconds 5 : bounded wait, at most 30 seconds.
- agent-pipeline results --job-id ID [--max-table-rows 10] : verified outputs,
  metrics, table previews, and a ZIP bundle, without rerunning.
- agent-pipeline cancel --job-id ID : stop the local process group (SDK approval).

Inspect catalog and session files, reuse known paths, then plan. Choose a
pipeline by its display name, description, use_when, avoid_when, inputs, and
limitations. Treat entries marked visibility=internal as demonstrations and
select them only when the user asks for a demo or runtime test. Resolve missing
inputs or parameters before run. Use the returned plan ID; never invent an ID.
Do not modify job state or pipeline definitions through filesystem tools.
Use existing data retrieval tools to obtain requested public data before planning;
use example files only when the user requested examples. The agent selects data
and parameters; deterministic code validates them.
A queued/running job is not a successful pipeline. When the user's task includes
analysis, wait briefly and collect results automatically if it succeeds. For long
jobs return the job ID and status; do not promise unsolicited background messages.
On later requests inspect existing jobs. Never rerun to review outputs. Do not
automatically retry failed/interrupted jobs. Preserve logs and explain failures.

Usage examples:
1. "List the available pipelines" -> catalog.
2. "Run the shell metadata template and summarize it" -> example, plan,
   approval, run, wait, and results.
3. "Run the shell metadata template with my uploaded reads.fastq and metadata.tsv" ->
   files, explicit slot inputs, plan, approval, run, wait, and results.
"""


def workspace(context) -> Path:
    """Return the active SDK sandbox root for this pipeline invocation.

    The session identity is application-owned; the model cannot supply a
    workspace override.  The fallback keeps direct operator tests usable, while
    normal Runner calls must agree with the SDK sandbox manifest.
    """
    from harness.sandbox import session_root
    expected = session_root(context.session_id).resolve()
    sandbox_session = getattr(context, "sandbox_session", None)
    if sandbox_session is None:
        return expected
    manifest_root = Path(sandbox_session.state.manifest.root).resolve()
    if manifest_root != expected:
        raise ValueError("Pipeline workspace does not match the active SDK sandbox.")
    return manifest_root


async def needs_approval(ctx, action, call_id) -> bool:
    if len(action.commands) != 1:
        return False  # Executor rejects invalid calls without asking for approval.
    try:
        args = parse_command(action.commands[0])
    except ValueError:
        return False
    if args.operation == "run":
        # Ensure there is a concrete plan for the approval UI to display.
        try:
            plan = JobStore(workspace(ctx.context)).get(args.plan_id)
            if plan.get("plan", {}).get("dry_run"):
                return False
        except ValueError:
            return False
    return args.operation in {"run", "cancel"}


async def execute_local_pipeline_command(request: ShellCommandRequest) -> ShellResult:
    context = request.ctx_wrapper.context
    commands = request.data.action.commands
    command = commands[0] if len(commands) == 1 else ""
    try:
        if len(commands) != 1:
            raise ValueError("Send exactly one agent-pipeline command per shell call.")
        args = parse_command(command)
        # Bounded wait is capped by the shell action budget as well as its own flag.
        timeout = request.data.action.timeout_ms
        if args.operation == "wait" and timeout and args.seconds * 1000 > timeout:
            raise ValueError("--seconds exceeds the shell action timeout_ms budget.")
        value = await asyncio.to_thread(dispatch, workspace(context), command)
        value.setdefault("status", "ok")
        code = 1 if value["status"] == "error" else 0
    except Exception as exc:
        value = {"status": "error", "error": str(exc), "error_type": type(exc).__name__}
        code = 1
    record = {"tool": "pipeline_shell", "arguments": {"command": command}, "result": value,
              "tool_calls": [{"tool": "pipeline_shell", "arguments": {"command": command}, "result": value,
                              "status": "error" if code else "ok", "error": value.get("error")}]}
    context.tool_results.append(record)
    context.record("pipeline_command_finished", command=command, status=value["status"])
    if context.sandbox_session is not None:
        from harness.sandbox import list_files
        context.files = await list_files(context.sandbox_session)
    return ShellResult(output=[ShellCommandOutput(command=command, stdout=json.dumps(value),
        outcome=ShellCallOutcome(type="exit", exit_code=code))], max_output_length=32000)


pipeline_shell = ShellTool(name="pipeline_shell", executor=execute_local_pipeline_command,
                           needs_approval=needs_approval, environment={"type": "local"})
