"""Cromwell Server REST backend for Pipeline2Agent WDL pipelines."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from contextlib import ExitStack
from pathlib import Path
import time
from typing import Any, Callable
from urllib.parse import urlsplit

import requests

from tools.infrastructure.pipeline_engine.engine.config import write_runtime_config
from tools.infrastructure.pipeline_engine.engine.inputs import stringify_input_value
from tools.infrastructure.pipeline_engine.engine.input_storage import (
    S3InputUploader,
    S3OutputStorage,
    upload_local_file_values,
    write_upload_manifest,
)
from tools.infrastructure.pipeline_engine.engine.outputs import finalize_output_records
from tools.infrastructure.pipeline_engine.engine.paths import read_json, resolve_pipeline_file
from tools.infrastructure.pipeline_engine.engine.types import PipelineContext, RuntimeConfigWrite
from tools.infrastructure.pipeline_engine.engine.wdl import (
    copy_declared_outputs,
    output_path_by_name,
    write_wdl_inputs,
    write_wdl_options,
)


TERMINAL_STATUSES = {"Succeeded", "Failed", "Aborted"}


@dataclass(frozen=True)
class PreparedWorkflow:
    workflow_path: Path
    inputs_path: Path
    options_path: Path | None
    runtime_config: RuntimeConfigWrite
    uploaded_inputs: list[dict[str, Any]]


def prepare_workflow(
    context: PipelineContext,
    *,
    input_storage: S3InputUploader | None,
    output_storage: S3OutputStorage | None,
    run_id: str | None = None,
    input_keys: set[str] | None = None,
    options_overrides: dict[str, Any] | None = None,
) -> PreparedWorkflow:
    """Prepare the same manifest-defined submission for local and isolated callers.

    The caller supplies storage credentials and any boundary-specific restrictions.
    This layer owns workflow resolution, config generation and upload serialization.
    """
    workflow_path = resolve_pipeline_file(
        context.pipeline_dir,
        str(context.runner_config.get("workflow") or "workflow.wdl"),
        fallback="workflow.wdl",
        label="WDL workflow",
    )
    runtime_config = write_runtime_config(context)
    inputs_path = write_wdl_inputs(context, runtime_config)
    if output_storage is not None and output_storage.mount_prefix is None:
        raise ValueError(
            "CROMWELL_OUTPUT_STORAGE_URI is configured, but no Cromwell-visible output "
            "directory is configured. The current Local backend needs "
            "CROMWELL_OUTPUT_STORAGE_MOUNT_PREFIX. Set that to the remote S3-backed "
            "mount."
        )
    options_path = write_wdl_options(
        context,
        output_storage_mount_prefix=(
            output_storage.mount_prefix if output_storage is not None else None
        ),
    )
    if options_overrides:
        settings = read_json(options_path)
        settings.update(options_overrides)
        options_path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    uploaded_inputs: list[dict[str, Any]] = []
    if input_storage is not None:
        uploaded_inputs = upload_local_file_values(
            inputs_path,
            input_storage,
            pipeline_name=context.pipeline_name,
            run_id=run_id or context.run_dir.parent.name,
            input_keys=input_keys,
        )
        write_upload_manifest(
            context.run_dir / "cromwell.input_uploads.json", input_storage, uploaded_inputs,
        )
    return PreparedWorkflow(workflow_path, inputs_path, options_path, runtime_config, uploaded_inputs)


class CromwellClient:
    """Shared Cromwell protocol with an optional caller-owned HTTP boundary.

    ``request`` accepts (method, suffix, **kwargs) and returns a decoded object.
    It controls credentials, redirects, timeouts and response limits when supplied.
    """

    def __init__(self, base_url: str, api_version: str = "v1", *,
                 headers: dict[str, str] | None = None, request: Callable | None = None):
        if not api_version or not api_version.isalnum():
            raise ValueError("Invalid Cromwell API version.")
        self.base_url = base_url
        self.api_version = api_version
        self.headers = headers if headers is not None else cromwell_headers()
        self.request = request

    def submit(self, prepared: PreparedWorkflow) -> dict[str, Any]:
        return submit_workflow(self.base_url, self.api_version, prepared.workflow_path,
                               prepared.inputs_path, prepared.options_path, self.headers,
                               request=self.request)

    def read(self, workflow_id: str, resource: str) -> dict[str, Any] | None:
        if resource not in {"status", "outputs", "metadata"}:
            raise ValueError("Unsupported Cromwell resource.")
        suffix = f"/{workflow_id}/{resource}"
        if self.request is not None:
            return self.request("GET", suffix)
        url = f"{self.base_url}/api/workflows/{self.api_version}{suffix}"
        return (get_workflow_status if resource == "status" else get_json)(url, self.headers)

    def abort(self, workflow_id: str) -> dict[str, Any]:
        suffix = f"/{workflow_id}/abort"
        if self.request is not None:
            return self.request("POST", suffix)
        response = requests.post(f"{self.base_url}/api/workflows/{self.api_version}{suffix}",
                                 headers=self.headers, timeout=60)
        ensure_success(response, "abort workflow")
        return response_json(response, "abort workflow")


def workflow_outputs(payload: dict[str, Any]) -> dict[str, Any]:
    outputs = payload.get("outputs")
    return outputs if isinstance(outputs, dict) else payload


def run_cromwell_pipeline(
    context: PipelineContext,
    cromwell_url: str | None = None,
) -> dict[str, Any]:
    """Submit WDL to Cromwell Server, wait for completion, and collect outputs."""
    input_storage = S3InputUploader.from_environment()
    output_storage = S3OutputStorage.from_environment()
    prepared = prepare_workflow(context, input_storage=input_storage, output_storage=output_storage)
    workflow_path, inputs_path, options_path = prepared.workflow_path, prepared.inputs_path, prepared.options_path
    runtime_config, uploaded_inputs = prepared.runtime_config, prepared.uploaded_inputs
    outputs_json = context.run_dir / "wdl.outputs.json"
    metadata_json = context.run_dir / "wdl.metadata.json"

    base_url = cromwell_base_url(explicit_url=cromwell_url)
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
    client = CromwellClient(base_url, api_version, headers=headers)
    submission = client.submit(prepared)
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
    metadata = client.read(workflow_id, "metadata")
    metadata_json.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")

    if status != "Succeeded":
        details = cromwell_failure_details(metadata)
        raise RuntimeError(
            f"Cromwell workflow {workflow_id} finished with status {status}: {details}"
        )

    output_response = client.read(workflow_id, "outputs")
    outputs_json.write_text(json.dumps(output_response, indent=2) + "\n", encoding="utf-8")
    output_map = workflow_outputs(output_response)
    try:
        copy_declared_outputs(
            runtime_config.output_records,
            output_map,
            remote_downloader=output_storage,
        )

        files, output_records = finalize_output_records(
            runtime_config.output_records,
            require_outputs=True,
        )
    except Exception as exc:
        raise RuntimeError(
            f"Cromwell workflow {workflow_id} succeeded, but output collection failed: {exc}"
        ) from exc

    output_storage_summary = None
    if output_storage is not None:
        output_storage_summary = {
            "backend": output_storage.backend,
            "base_uri": output_storage.base_uri,
            "mount_prefix": output_storage.mount_prefix,
            "execution_prefixes": list(output_storage.execution_prefixes),
            "downloaded": output_storage.downloaded,
        }
        (context.run_dir / "cromwell.output_downloads.json").write_text(
            json.dumps(output_storage_summary, indent=2) + "\n", encoding="utf-8"
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
        "input_storage": {
            "backend": input_storage.backend,
            "base_uri": input_storage.base_uri,
            "uploaded": uploaded_inputs,
        } if input_storage is not None else None,
        "output_storage": output_storage_summary,
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


def cromwell_base_url(
    explicit_url: str | None = None,
) -> str:
    # A saved plan's endpoint takes precedence over the worker environment.
    value = explicit_url if explicit_url is not None else os.environ.get("CROMWELL_URL", "")
    url = str(value).strip()
    if not url:
        raise ValueError(
            "Cromwell URL is not configured. Set CROMWELL_URL to use Cromwell."
        )
    if "://" not in url:
        url = f"http://{url}"
    try:
        parsed = urlsplit(url)
        valid = (
            parsed.scheme in {"http", "https"}
            and bool(parsed.hostname)
            and (parsed.port is None or parsed.port > 0)
            and not any(char.isspace() for char in url)
        )
    except ValueError:
        valid = False
    if not valid:
        raise ValueError(
            "Cromwell URL must be a valid HTTP(S) endpoint, for example "
            "http://192.168.164.39:39000."
        )
    return url.rstrip("/")


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
    *,
    request: Callable | None = None,
) -> dict[str, Any]:
    url = f"{base_url}/api/workflows/{api_version}"
    try:
        with ExitStack() as stack:
            workflow_handle = stack.enter_context(workflow_path.open("rb"))
            inputs_handle = stack.enter_context(inputs_path.open("rb"))
            files: dict[str, Any] = {
                "workflowSource": (workflow_path.name, workflow_handle, "application/octet-stream"),
                "workflowInputs": (inputs_path.name, inputs_handle, "application/json"),
            }
            if options_path:
                options_handle = stack.enter_context(options_path.open("rb"))
                files["workflowOptions"] = (options_path.name, options_handle, "application/json")
            if request is not None:
                payload = request("POST", "", files=files)
            else:
                response = requests.post(url, files=files, headers=headers, timeout=60)
                ensure_success(response, "submit workflow")
                payload = response_json(response, "submit workflow")
    except requests.RequestException as exc:
        raise RuntimeError(f"Could not submit workflow to Cromwell at {base_url}: {exc}") from exc
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
    client = CromwellClient(base_url, api_version, headers=headers)
    started_at = time.monotonic()
    deadline = started_at + timeout
    visibility_deadline = min(deadline, started_at + visibility_timeout)
    if initial_status in TERMINAL_STATUSES:
        return initial_status
    # Cromwell has accepted the workflow. Give its workflow store one polling
    # interval to expose the ID before the first status request.
    time.sleep(min(poll_interval, max(0.0, deadline - time.monotonic())))
    while True:
        payload = client.read(workflow_id, "status")
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
