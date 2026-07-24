"""Cromwell Server REST backend for BioAgent WDL pipelines."""

from __future__ import annotations

import json
import os
from pathlib import Path
import time
from typing import Any

import requests

from tools.pipeline_runner.config import write_runtime_config
from tools.pipeline_runner.inputs import stringify_input_value
from tools.pipeline_runner.outputs import finalize_output_records
from tools.pipeline_runner.paths import read_json, resolve_pipeline_file
from tools.pipeline_runner.types import PipelineContext
from tools.pipeline_runner.wdl import (
    copy_declared_outputs,
    output_path_by_name,
    write_wdl_inputs,
    write_wdl_options,
)


TERMINAL_STATUSES = {"Succeeded", "Failed", "Aborted"}


def run_cromwell_pipeline(context: PipelineContext) -> dict[str, Any]:
    """Submit WDL to Cromwell Server, wait for completion, and collect outputs."""
    workflow_path = resolve_pipeline_file(
        context.pipeline_dir,
        str(context.runner_config.get("workflow") or "workflow.wdl"),
        fallback="workflow.wdl",
        label="WDL workflow",
    )
    runtime_config = write_runtime_config(context)
    inputs_path = write_wdl_inputs(context)
    options_path = write_wdl_options(context)
    outputs_json = context.run_dir / "wdl.outputs.json"
    metadata_json = context.run_dir / "wdl.metadata.json"

    base_url = cromwell_base_url(context.runner_config)
    api_version = str(context.runner_config.get("cromwell_api_version") or "v1").strip()
    poll_interval = max(
        1.0,
        float(context.runner_config.get("cromwell_poll_interval") or 5),
    )
    visibility_timeout = max(
        poll_interval,
        float(context.runner_config.get("cromwell_visibility_timeout") or 300),
    )
    headers = cromwell_headers()
    submission = submit_workflow(
        base_url,
        api_version,
        workflow_path,
        inputs_path,
        options_path,
        headers,
    )
    workflow_id = str(submission["id"])
    submission_status = str(submission.get("status") or "Submitted")
    submission_json = context.run_dir / "cromwell.submission.json"
    submission_json.write_text(
        json.dumps(submission, indent=2) + "\n",
        encoding="utf-8",
    )

    status = wait_for_workflow(
        base_url,
        api_version,
        workflow_id,
        headers,
        timeout=context.timeout,
        poll_interval=poll_interval,
        visibility_timeout=visibility_timeout,
        initial_status=submission_status,
    )
    metadata = get_json(
        f"{base_url}/api/workflows/{api_version}/{workflow_id}/metadata",
        headers,
    )
    metadata_json.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")

    if status != "Succeeded":
        details = cromwell_failure_details(metadata)
        raise RuntimeError(
            f"Cromwell workflow {workflow_id} finished with status {status}: {details}"
        )

    output_response = get_json(
        f"{base_url}/api/workflows/{api_version}/{workflow_id}/outputs",
        headers,
    )
    outputs_json.write_text(json.dumps(output_response, indent=2) + "\n", encoding="utf-8")
    output_map = output_response.get("outputs")
    if not isinstance(output_map, dict):
        output_map = output_response
    copy_declared_outputs(runtime_config.output_records, output_map)

    files, output_records = finalize_output_records(
        runtime_config.output_records,
        require_outputs=True,
    )
    metrics_path = output_path_by_name(output_records, "metrics")
    report_path = output_path_by_name(output_records, "report")
    return {
        "status": "ok",
        "pipeline": str(context.runner_config.get("name", context.pipeline_name)),
        "pipeline_name": context.pipeline_name,
        "engine": "wdl",
        "wdl_engine": "cromwell",
        "cromwell_url": base_url,
        "cromwell_workflow_id": workflow_id,
        "cromwell_status": status,
        "dry_run": False,
        "config_path": str(runtime_config.path),
        "inputs_path": str(inputs_path),
        "options_path": str(options_path) if options_path else "",
        "runner_config_path": str(context.runner_config_path),
        "raw_config_path": str(context.raw_config_path),
        "workflow_path": str(workflow_path),
        "input_path": str(context.input_path),
        "original_input_path": str(context.original_input_path),
        "session_input_path": str(context.session_input_path or ""),
        "input_staged": context.input_staged,
        "input_overrides": {
            key: stringify_input_value(path)
            for key, path in context.resolved_input_overrides.items()
        },
        "run_dir": str(context.run_dir),
        "output_dir": str(context.output_dir),
        "metadata_path": str(metadata_json),
        "returncode": 0,
        "command": ["POST", f"{base_url}/api/workflows/{api_version}"],
        "stdout": f"Cromwell workflow {workflow_id} succeeded.",
        "stderr": "",
        "metrics_path": str(metrics_path) if metrics_path else "",
        "report_path": str(report_path) if report_path else "",
        "output_records": output_records,
        "files": files,
        "metrics": {} if not metrics_path else read_json(metrics_path),
    }


def cromwell_base_url(runner_config: dict[str, Any]) -> str:
    value = os.environ.get("CROMWELL_URL") or runner_config.get("cromwell_url")
    if not value:
        raise ValueError(
            "Cromwell URL is not configured. Set CROMWELL_URL or runner.yaml cromwell_url."
        )
    url = str(value).strip().rstrip("/")
    if "://" not in url:
        url = f"http://{url}"
    if not url.startswith(("http://", "https://")):
        raise ValueError(
            "Cromwell URL must use http:// or https://, for example "
            "http://192.168.164.39:39000."
        )
    return url


def cromwell_headers() -> dict[str, str]:
    token = str(os.environ.get("CROMWELL_TOKEN") or "").strip()
    return {"Authorization": f"Bearer {token}"} if token else {}


def submit_workflow(
    base_url: str,
    api_version: str,
    workflow_path: Path,
    inputs_path: Path,
    options_path: Path | None,
    headers: dict[str, str],
) -> dict[str, Any]:
    url = f"{base_url}/api/workflows/{api_version}"
    try:
        with workflow_path.open("rb") as workflow_handle, inputs_path.open("rb") as inputs_handle:
            files: dict[str, Any] = {
                "workflowSource": (workflow_path.name, workflow_handle, "application/octet-stream"),
                "workflowInputs": (inputs_path.name, inputs_handle, "application/json"),
            }
            if options_path:
                with options_path.open("rb") as options_handle:
                    files["workflowOptions"] = (
                        options_path.name,
                        options_handle,
                        "application/json",
                    )
                    response = requests.post(url, files=files, headers=headers, timeout=60)
            else:
                response = requests.post(url, files=files, headers=headers, timeout=60)
    except requests.RequestException as exc:
        raise RuntimeError(f"Could not submit workflow to Cromwell at {base_url}: {exc}") from exc
    ensure_success(response, "submit workflow")
    payload = response_json(response, "submit workflow")
    workflow_id = str(payload.get("id") or "").strip()
    if not workflow_id:
        raise RuntimeError(f"Cromwell submission response did not include a workflow id: {payload}")
    payload["id"] = workflow_id
    payload["status"] = str(payload.get("status") or "Submitted")
    return payload


def wait_for_workflow(
    base_url: str,
    api_version: str,
    workflow_id: str,
    headers: dict[str, str],
    timeout: int,
    poll_interval: float,
    visibility_timeout: float = 300,
    initial_status: str = "Submitted",
) -> str:
    url = f"{base_url}/api/workflows/{api_version}/{workflow_id}/status"
    started_at = time.monotonic()
    deadline = started_at + timeout
    visibility_deadline = min(deadline, started_at + visibility_timeout)
    if initial_status in TERMINAL_STATUSES:
        return initial_status
    # Cromwell has accepted the workflow. Give its workflow store one polling
    # interval to expose the ID before the first status request.
    time.sleep(min(poll_interval, max(0.0, deadline - time.monotonic())))
    while True:
        payload = get_workflow_status(url, headers)
        if payload is None:
            now = time.monotonic()
            if now >= visibility_deadline:
                raise RuntimeError(
                    f"Cromwell workflow {workflow_id} was accepted but remained unrecognized "
                    f"by the status API for {visibility_timeout:g} seconds. Check whether "
                    "Cromwell API instances share the same database and whether the reverse "
                    "proxy uses consistent routing."
                )
            time.sleep(min(poll_interval, max(0.0, visibility_deadline - now)))
            continue
        status = str(payload.get("status") or "Unknown")
        if status in TERMINAL_STATUSES:
            return status
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"Timed out waiting for Cromwell workflow {workflow_id}; last status: {status}. "
                "The workflow was not aborted and may still be running on Cromwell."
            )
        time.sleep(min(poll_interval, max(0.0, deadline - time.monotonic())))


def get_workflow_status(url: str, headers: dict[str, str]) -> dict[str, Any] | None:
    """Return status JSON, retrying Cromwell's transient unknown-ID response upstream."""
    try:
        response = requests.get(url, headers=headers, timeout=60)
    except requests.RequestException as exc:
        raise RuntimeError(f"Cromwell request failed for {url}: {exc}") from exc
    if response.status_code == 404 and "Unrecognized workflow ID" in response.text:
        return None
    ensure_success(response, f"GET {url}")
    return response_json(response, f"GET {url}")


def get_json(url: str, headers: dict[str, str]) -> dict[str, Any]:
    try:
        response = requests.get(url, headers=headers, timeout=60)
    except requests.RequestException as exc:
        raise RuntimeError(f"Cromwell request failed for {url}: {exc}") from exc
    ensure_success(response, f"GET {url}")
    return response_json(response, f"GET {url}")


def ensure_success(response: requests.Response, operation: str) -> None:
    if response.ok:
        return
    body = response.text.strip()
    if len(body) > 2000:
        body = body[-2000:]
    raise RuntimeError(
        f"Cromwell {operation} failed with HTTP {response.status_code}: {body or '<empty response>'}"
    )


def response_json(response: requests.Response, operation: str) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError(f"Cromwell {operation} returned invalid JSON: {response.text[:1000]}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"Cromwell {operation} returned unexpected JSON: {payload}")
    return payload


def cromwell_failure_details(metadata: dict[str, Any]) -> str:
    messages: list[str] = []

    def collect(value: Any) -> None:
        if isinstance(value, dict):
            message = value.get("message")
            if isinstance(message, str) and message.strip():
                messages.append(message.strip())
            for nested in value.values():
                collect(nested)
        elif isinstance(value, list):
            for nested in value:
                collect(nested)

    collect(metadata.get("failures") or metadata)
    unique = list(dict.fromkeys(messages))
    details = " | ".join(unique[-10:])
    return details[-4000:] if details else "see wdl.metadata.json for failure details"
