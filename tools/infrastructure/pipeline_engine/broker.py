"""Owned, durable manifest-driven jobs for isolated accounts.

Only application-installed workflows allowed by policy are exposed. Plans, input snapshots,
remote IDs and credentials never enter the model-writable workspace. Local engines
run in disposable workers; remote WDL jobs retain their Cromwell execution IDs.
"""
from __future__ import annotations

from contextlib import contextmanager
import copy
import fcntl
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import time
from uuid import UUID, uuid4

import requests

from auth import ExecutionUnavailable, current_principal
from isolation.files import inventory, open_regular, copy_stream, import_staged, fingerprint
from isolation.limits import limits
from isolation.storage import storage_lock, check_quota
import tempfile
from isolation.policy import WorkspaceAccess
from . import service
from .commands import mapping, parse_command
from .store import JobStore, TERMINAL, atomic_json, confined, now

from . import contracts
from .engine import cromwell
ACTIVE = {'submitting', 'queued', 'running', 'cancelling'}


def catalog(*, compact=True):
    entries = []
    for entry in service.catalog(compact=compact):
        try: backend = contracts.backend(entry['name'])
        except (ExecutionUnavailable, ValueError, OSError): continue
        if backend == 'docker' or os.getenv('CROMWELL_URL'):
            entries.append(entry)
    return entries


def _owned(root, access: WorkspaceAccess):
    root = Path(root).resolve()
    identifier = root.name
    access.ownership.require(identifier)
    if root != access.workspace(identifier).resolve():
        raise ValueError('Pipeline workspace does not match the owned session.')
    private = access.metadata_root / '.pipelines' / identifier
    private.mkdir(parents=True, exist_ok=True, mode=0o700)
    return private


@contextmanager
def _lock(path):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.open('a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        yield


def get_plan(root, identifier, *, access: WorkspaceAccess):
    return JobStore(_owned(root, access)).get(identifier)


def public_plan(plan):
    value = copy.deepcopy(plan)
    for slot, items in value['inputs'].items():
        for index, item in enumerate(items):
            original = value['public_inputs'][slot]
            item['path'] = original[index] if isinstance(original, list) else original
    value['immutable_input_snapshot'] = True
    for key in ('owner_user_id', 'session_id', 'cromwell_url', 'public_inputs'):
        value.pop(key, None)
    return value


def _plan(root, private, args):
    _, manifest, config = contracts.definition(args.pipeline)
    local = manifest['engine'] in contracts.LOCAL_ENGINES
    if args.dry_run:
        raise ValueError('Use plan to validate inputs; remote dry-run execution is not supported.')
    if not local:
        _configured()
    store = JobStore(private)
    if sum(row['status'] == 'planned' for row in store.list()) >= 32:
        raise ValueError('This session already has 32 pending plans; cancel unused plans first.')
    params, inputs = mapping(args.param, decode=True), mapping(args.input, decode=True)
    contracts.validate_parameters(params, manifest, config)
    from .engine.inputs import pipeline_input_specs
    specs = pipeline_input_specs(manifest)
    if set(inputs) - set(specs):
        raise ValueError('Unknown pipeline input slot.')
    missing = [slot for slot, spec in specs.items() if spec['required'] and not inputs.get(slot)]
    if missing:
        return {'status': 'needs_input', 'needs_input': True, 'pipeline_name': args.pipeline,
                'requested_inputs': [{**specs[slot], 'slot': slot} for slot in missing]}
    snapshot, public_inputs = {}, {}
    files = inventory(root)
    for slot, value in inputs.items():
        values = value if isinstance(value, list) else [value]
        if not values or any(not isinstance(item, str) for item in values):
            raise ValueError('Inputs must be workspace-relative file paths.')
        copied = []
        for item in values:
            path = confined(root, item)
            relative = path.relative_to(root).as_posix()
            if relative not in files:
                raise ValueError('Input must be a regular file in this session.')
            target = private / 'uploads' / uuid4().hex / path.name
            target.parent.mkdir(parents=True)
            with open_regular(root, relative) as source, target.open('wb') as output:
                copy_stream(source, output, limits().file_bytes)
            copied.append(target.relative_to(private).as_posix())
        snapshot[slot] = copied if isinstance(value, list) else copied[0]
        public_inputs[slot] = values if isinstance(value, list) else values[0]
    if local:
        from isolation.policy import WORKER_TIMEOUT
        args.timeout = min(args.timeout or int(manifest.get('timeout', 300)), WORKER_TIMEOUT)
    result = service.plan(private, args.pipeline, snapshot, params, args.cores, args.timeout, False)
    if 'plan_id' in result:
        record = store.get(result['plan_id'])
        plan = record['plan']
        plan.update(owner_user_id=current_principal().user_id, session_id=root.name, public_inputs=public_inputs)
        if not local:
            plan['wdl_engine'] = 'cromwell'
        store.update(record['job_id'], plan=plan)
        result['plan'] = public_plan(plan)
    return result


def _configured():
    from tools.infrastructure.pipeline_engine.engine.cromwell import cromwell_base_url
    from tools.infrastructure.pipeline_engine.engine.input_storage import S3InputUploader, S3OutputStorage
    base = cromwell_base_url()
    uploads, outputs = S3InputUploader.from_environment(), S3OutputStorage.from_environment()
    if uploads is None or outputs is None or not outputs.mount_prefix:
        raise ExecutionUnavailable('Remote jobs require Cromwell input/output S3 configuration and an output mount prefix.')
    return base, uploads, outputs


def _http(base, method, suffix, *, api_version='v1', **kwargs):
    from tools.infrastructure.pipeline_engine.engine.cromwell import cromwell_headers
    with requests.Session() as client:
        client.trust_env = False
        with client.request(method, base + '/api/workflows/' + api_version + suffix, headers=cromwell_headers(),
                            timeout=(5, 30), allow_redirects=False, stream=True, **kwargs) as response:
            if not 200 <= response.status_code < 300:
                raise RuntimeError(f'Cromwell returned HTTP {response.status_code}.')
            body = bytearray()
            for chunk in response.iter_content(65536):
                body.extend(chunk)
                if len(body) > 1024 * 1024:
                    raise ValueError('Cromwell response exceeds 1 MiB.')
            result = json.loads(body)
            if not isinstance(result, dict):
                raise ValueError('Invalid Cromwell response.')
            return result


def _remote_client(record):
    version = record.get('remote_api_version', 'v1')
    return cromwell.CromwellClient(record['remote_base'], version, headers={},
        request=lambda method, suffix, **kwargs: _http(record['remote_base'], method, suffix,
                                                       api_version=version, **kwargs))


def _start(private, identifier, access: WorkspaceAccess):
    store = JobStore(private)
    record = store.get(identifier)
    if record['status'] != 'planned':
        return _summary(record)
    backend = contracts.backend(record['plan']['pipeline_name'])
    if backend == 'docker':
        from .isolated_controller import start
        return _summary(start(private, identifier, access))
    plan = record['plan']
    service.verify(private, plan)
    base, uploads, outputs = _configured()
    # Serialize quota checks and the durable claim across all sessions/processes.
    with _lock(private.parent / '.launch.lock'):
        active = [job for folder in private.parent.iterdir() if folder.is_dir()
                  for job in JobStore(folder).list() if job['status'] in ACTIVE or job.get('submission_unknown')]
        if len(active) >= 16 or sum(job['plan']['owner_user_id'] == plan['owner_user_id'] for job in active) >= 2:
            raise ValueError('Remote job limit reached (2 per account, 16 server-wide).')
        store.update(identifier, status='submitting', started_at=now(),
                     deadline=time.time() + plan['timeout_seconds'], remote_base=base)
    submitted = False
    try:
        from tools.infrastructure.pipeline_engine.engine.inputs import pipeline_input_specs
        context = service.prepare_execution(private, record, snapshot_inputs=False)
        specs = pipeline_input_specs(context.runner_config)
        # Cache sharing could disclose another account's data. Always execute independently.
        prepared = cromwell.prepare_workflow(context, input_storage=uploads, output_storage=outputs,
            run_id=identifier, input_keys={spec['config_key'] for spec in specs.values()},
            options_overrides={'read_from_cache': False, 'write_to_cache': False})
        version = str(context.runner_config.get('cromwell_api_version') or 'v1').strip()
        record = store.update(identifier, output_records=prepared.runtime_config.output_records,
                              remote_api_version=version)
        client = _remote_client(record)
        transport = client.request
        def submit_request(method, suffix, **kwargs):
            nonlocal submitted
            # Any transport failure after this point is ambiguous; never auto-resubmit.
            submitted = True
            return transport(method, suffix, **kwargs)
        client.request = submit_request
        access.ownership.require(plan['session_id'])
        reply = client.submit(prepared)
        remote_id = str(UUID(str(reply.get('id', ''))))
        record = store.update(identifier, remote_id=remote_id, status='queued')
    except Exception:
        record = store.update(identifier, status='interrupted' if submitted else 'failed', finished_at=now(),
            submission_unknown=submitted,
            error=('Submission outcome is unknown; ask the operator to reconcile Cromwell before creating another plan.'
                   if submitted else 'Job preparation failed; check server configuration and storage connectivity.'))
    return _summary(record)


def _summary(record):
    allowed = ('job_id', 'plan_id', 'status', 'created_at', 'started_at', 'finished_at', 'updated_at', 'error', 'remote_id')
    return {**{key: record[key] for key in allowed if key in record}, 'pipeline_name': record['plan']['pipeline_name']}


def _output_key(storage, source, remote_id):
    from urllib.parse import urlsplit
    uri = storage.uri_for_path(source)
    if not uri:
        raise ValueError('Output is outside configured storage.')
    parsed = urlsplit(uri)
    parts = PurePosixPath(parsed.path).parts
    if '..' in parts or remote_id not in parts or parsed.query or parsed.fragment:
        raise ValueError('Output is outside this workflow.')
    return parsed.netloc, parsed.path.lstrip('/')


def _collect(private, record):
    from tools.infrastructure.pipeline_engine.engine.input_storage import S3OutputStorage
    from tools.infrastructure.pipeline_engine.engine.wdl import output_value, output_value_as_string
    store = JobStore(private)
    storage = S3OutputStorage.from_environment()
    if storage is None:
        raise ValueError('Output storage is unavailable.')
    payload = _remote_client(record).read(record['remote_id'], 'outputs')
    output_map = cromwell.workflow_outputs(payload)
    collected = []
    for item in record['output_records']:
        target = Path(item['path'])
        if not target.resolve().is_relative_to(store.directory(record['job_id']) / 'outputs'):
            raise ValueError('Invalid private output destination.')
        raw = output_value(item, output_map)
        def flatten(value):
            if isinstance(value, list):
                for child in value: yield from flatten(child)
            else:
                yield value
        for index, value in enumerate(flatten(raw)):
            source = output_value_as_string(value)
            if not source:
                if value is None and not item.get('required', True): continue
                raise ValueError('Required file output is missing or invalid.')
            bucket, key = _output_key(storage, source, record['remote_id'])
            metadata = storage.client.head_object(Bucket=bucket, Key=key)
            size = int(metadata['ContentLength'])
            if size < 0: raise ValueError('Invalid remote artifact size.')
            if not metadata.get('ETag') and metadata.get('VersionId') in {None, '', 'null'}:
                raise ValueError('Output storage did not provide an immutable object reference.')
            artifact = dict(item)
            if isinstance(raw, list):
                artifact.update(name=f"{item.get('name', 'output')}[{index}]",
                                path=str(target.with_name(f'{target.stem}-{index}{target.suffix}')))
            collected.append({**artifact, 'exists': False, 'size': size,
                              'remote': {'bucket': bucket, 'key': key, 'etag': metadata.get('ETag'),
                                         'version_id': metadata.get('VersionId')}})
    atomic_json(store.directory(record['job_id']) / 'output-manifest.json', collected)
    return store.update(record['job_id'], status='succeeded', finished_at=now(), artifact_status='available', error=None, result={'output_records': collected})


def _status(private, identifier):
    store = JobStore(private)
    record = store.get(identifier)
    if record.get('execution_backend') == 'docker':
        from .isolated_controller import status
        return _summary(status(private, identifier))
    if record['status'] == 'submitting':
        # A server killed during submission must never submit a duplicate on restart.
        record = store.update(identifier, status='interrupted', finished_at=now(),
            submission_unknown=True,
            error='Submission was interrupted; reconcile Cromwell before submitting another plan.')
    if record['status'] not in ACTIVE or not record.get('remote_id'):
        return _summary(record)
    status = None
    try:
        client = _remote_client(record)
        payload = client.read(record['remote_id'], 'status')
        if payload is None:
            return _summary(record)
        status = payload.get('status')
        expired = time.time() > record['deadline']
        if status == 'Succeeded':
            record = _collect(private, record)
        elif status in {'Failed', 'Aborted'}:
            terminal = 'failed' if status == 'Failed' else ('timed_out' if record.get('timeout_abort') else 'cancelled')
            record = store.update(identifier, status=terminal, finished_at=now())
        elif record['status'] == 'cancelling' or expired:
            # Keep it active until the remote server confirms termination.
            client.abort(record['remote_id'])
            record = store.update(identifier, status='cancelling', timeout_abort=record.get('timeout_abort', expired))
        else:
            record = store.update(identifier, status='running')
    except Exception as exc:
        # Polling/download failures are recoverable; preserve the remote ID and
        # never turn a failed fetch into another submission or a false success.
        if status == 'Succeeded' and time.time() > record['deadline'] + 600:
            record = store.update(identifier, status='succeeded', finished_at=now(), artifact_status='unavailable',
                error='Remote workflow succeeded; artifact registration is unavailable. Retry results to register outputs.')
        return {**_summary(record), 'warning': 'Remote status or output collection is temporarily unavailable; retry status.',
                'error_type': type(exc).__name__}
    return _summary(record)


def _remote_file(record, index):
    item = record['result']['output_records'][index]
    name = Path(item.get('path') or item.get('name') or 'artifact').name
    path = f"pipeline-artifacts/{record['job_id']}/{index}/{name}"
    return {'name': name, 'path': path, 'workspace_path': path, 'size': item['size'],
            'remote': True, 'artifact_id': f"{record['job_id']}:{index}"}


@contextmanager
def remote_stream(root, path, *, access, byte_range=None):
    """Resolve owned immutable remote references; storage credentials stay server-side."""
    from tools.infrastructure.pipeline_engine.engine.input_storage import S3OutputStorage
    parts = PurePosixPath(path).parts
    if len(parts) != 4 or parts[0] != 'pipeline-artifacts':
        raise ValueError('Invalid pipeline artifact path.')
    record = JobStore(_owned(root, access)).get(parts[1])
    index = int(parts[2])
    if index < 0 or index >= len(record.get('result', {}).get('output_records', [])) or record['status'] != 'succeeded': raise ValueError('Artifact is unavailable.')
    item = record['result']['output_records'][index]
    if _remote_file(record, index)['path'] != path or 'remote' not in item:
        raise ValueError('Artifact is unavailable.')
    storage = S3OutputStorage.from_environment()
    if storage is None: raise ValueError('Output storage is unavailable.')
    remote = item['remote']
    _output_key(storage, f"s3://{remote['bucket']}/{remote['key']}", record['remote_id'])
    arguments = {'Bucket': remote['bucket'], 'Key': remote['key']}
    if remote.get('version_id') not in {None, '', 'null'}: arguments['VersionId'] = remote['version_id']
    elif remote.get('etag'): arguments['IfMatch'] = remote['etag']
    if byte_range:
        match = re.fullmatch(r'bytes=(\d*)-(\d*)', byte_range)
        if not match or not any(match.groups()) or not item['size']: raise ValueError('Unsatisfiable byte range.')
        left, right = match.groups()
        if left:
            start = int(left); end = min(int(right), item['size'] - 1) if right else item['size'] - 1
        else:
            if int(right) <= 0: raise ValueError('Unsatisfiable byte range.')
            start, end = max(0, item['size'] - int(right)), item['size'] - 1
        if start > end or start >= item['size']: raise ValueError('Unsatisfiable byte range.')
        arguments['Range'] = f'bytes={start}-{end}'
    response = storage.client.get_object(**arguments)
    try:
        yield response, item
    finally:
        response['Body'].close()


def materialize(root, path, *, access):
    """Explicitly stage one remote artifact as an ordinary owned workspace file."""
    from isolation.storage import publish
    from isolation.storage import reserve, release
    # Ownership and manifest lookup happen before allocating local storage.
    parts = PurePosixPath(path).parts
    if len(parts) != 4 or parts[0] != 'pipeline-artifacts': raise ValueError('Invalid pipeline artifact path.')
    record = JobStore(_owned(root, access)).get(parts[1])
    index = int(parts[2])
    if index < 0 or index >= len(record.get('result', {}).get('output_records', [])): raise ValueError('Artifact is unavailable.')
    item = record['result']['output_records'][index]
    if index < 0 or _remote_file(record, index)['path'] != path: raise ValueError('Invalid artifact.')
    if item['size'] > limits().file_bytes: raise ValueError('Artifact exceeds the configured local file limit; download it directly.')
    reservation = reserve(access, root.name, item['size'])
    try:
        with tempfile.TemporaryDirectory(dir=access.metadata_root) as temporary:
            source = Path(temporary) / 'data'
            with remote_stream(root, path, access=access) as (response, _), source.open('wb') as output:
                actual = copy_stream(response['Body'], output, item['size'])
            if actual['size'] != item['size']: raise ValueError('Incomplete remote artifact.')
            return publish(access, root.name, Path(path).name, source, item['size'], reservation=reservation)
    finally:
        release(access, reservation)


def remote_files(root, *, access):
    private = _owned(root, access)
    return [_remote_file(record, index) for record in JobStore(private).list()
            if record['status'] == 'succeeded'
            for index, item in enumerate(record.get('result', {}).get('output_records', [])) if item.get('remote')]


def _publish(root, private, identifier, max_rows, access: WorkspaceAccess):
    status = _status(private, identifier)
    if status['status'] != 'succeeded':
        return {**status, 'files': []}
    record = JobStore(private).get(identifier)
    if record.get('artifact_status') == 'unavailable':
        record = _collect(private, record)
    if any(item.get('remote') for item in record.get('result', {}).get('output_records', [])):
        files = [_remote_file(record, i) for i, item in enumerate(record['result']['output_records']) if item.get('remote')]
        previews, remaining = [], limits().preview_bytes
        for file in files:
            if file['size'] > remaining or Path(file['name']).suffix.lower() not in {'.txt', '.md', '.json', '.csv', '.tsv'}:
                continue
            try:
                with remote_stream(root, file['path'], access=access) as (response, _):
                    data = response['Body'].read(file['size'] + 1)
                if len(data) != file['size']: raise ValueError('Incomplete remote preview.')
                remaining -= len(data)
                previews.append({'path': file['path'], 'text': data.decode('utf-8', errors='replace')})
            except Exception:
                previews.append({'path': file['path'], 'error': 'Preview unavailable; the remote artifact can be retried.'})
        return {**status, 'files': files, 'previews': previews, 'bundle_path': f'pipeline-bundles/{identifier}/results.zip',
                'message': 'Outputs remain in remote storage. Small text previews are included; import selected files to use workspace tools.'}
    # Existing jobs with collected local outputs remain readable, without a duplicate ZIP.
    result = service.results(private, identifier, max_rows, include_bundle=False)
    public_directory = Path('outputs') / 'pipelines' / identifier
    with tempfile.TemporaryDirectory(dir=access.metadata_root) as temporary:
        stage = Path(temporary); before = {}
        for item in result['files']:
            source = confined(private, item['workspace_path'])
            target = (public_directory / source.relative_to(JobStore(private).directory(identifier))).as_posix()
            if (root / target).exists(): before[target] = fingerprint(root, target)
            (stage / target).parent.mkdir(parents=True, exist_ok=True)
            with open_regular(private, item['workspace_path']) as incoming, (stage / target).open('wb') as output:
                copy_stream(incoming, output, limits().file_bytes)
            item['workspace_path'] = item['path'] = target
        with storage_lock(access):
            check_quota(access, root.name, max(0, sum(inventory(stage).values()) - sum(v['size'] for v in before.values())))
            import_staged(root, before, stage)
    result['bundle_path'] = f'pipeline-bundles/{identifier}/results.zip'
    return result


def _stage_example(root, name, access):
    """Reserve example storage, then publish a complete directory atomically."""
    from isolation.storage import reserve, release
    directory, _, _ = service.definition(name)
    source = directory / 'data' / 'input'
    sizes = inventory(source)
    budget = limits()
    if any(size > budget.file_bytes for size in sizes.values()):
        raise ValueError(f'File exceeds the {budget.file_bytes} byte limit.')
    total = sum(sizes.values())
    reservation = reserve(access, root.name, total)
    try:
        with storage_lock(access):
            check_quota(access, root.name, total, exclude=reservation)
            for parent in (root / 'uploads', root / 'uploads' / 'examples'):
                if parent.is_symlink():
                    raise ValueError('Example directories cannot be symbolic links.')
            parent = confined(root, 'uploads/examples')
            parent.mkdir(parents=True, exist_ok=True)
            if shutil.disk_usage(parent).free - total < budget.free_disk_bytes:
                raise ValueError('Insufficient workspace disk space for pipeline examples.')
            destination = parent / f'{name}-{uuid4().hex}'
            # Same filesystem as the destination, so publication is one rename.
            with tempfile.TemporaryDirectory(dir=parent, prefix='.example-') as temporary:
                stage = Path(temporary)
                for relative, size in sorted(sizes.items()):
                    target = stage / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with open_regular(source, relative) as incoming, target.open('wb') as outgoing:
                        copied = copy_stream(incoming, outgoing, size)
                    if copied['size'] != size:
                        raise ValueError('Example input changed during copying; retry the request.')
                # Staged bytes already count in usage; exclude our reservation
                # rather than charging this operation twice. Recheck ownership.
                check_quota(access, root.name, 0, exclude=reservation)
                os.rename(stage, destination)
            return {'pipeline_name': name, 'example_data': True, 'files': [
                {'workspace_path': (destination / relative).relative_to(root).as_posix(), 'size': size}
                for relative, size in sorted(sizes.items())]}
    finally:
        release(access, reservation)


def dispatch(root, command, *, access: WorkspaceAccess):
    root = Path(root).resolve()
    private = _owned(root, access)
    args = parse_command(command)
    if args.operation == 'wait':
        if not math.isfinite(args.seconds) or not 0 <= args.seconds <= 30:
            raise ValueError('Wait must be between 0 and 30 seconds.')
        deadline = time.monotonic() + args.seconds
        while True:
            value = dispatch(root, f'agent-pipeline status --job-id {args.job_id}', access=access)
            if value['status'] in TERMINAL | {'planned'} or time.monotonic() >= deadline:
                return value
            time.sleep(min(1, max(0, deadline - time.monotonic())))
    # Same lock as disposable tools: result imports and input snapshots are serialized.
    with _lock(access.metadata_root / '.worker-locks' / root.name), _lock(private / '.broker.lock'):
        _owned(root, access)  # Recheck after waiting for another tool or controller.
        if args.operation == 'catalog':
            return {'pipelines': catalog()}
        if args.operation == 'files':
            return {'files': service.files(root)}
        if args.operation == 'example':
            contracts.definition(args.pipeline)
            return _stage_example(root, args.pipeline, access)
        if args.operation == 'plan':
            with storage_lock(access):
                values = mapping(args.input, decode=True)
                extra = sum(confined(root, item).stat().st_size for value in values.values() for item in (value if isinstance(value, list) else [value]) if isinstance(item, str))
                check_quota(access, root.name, extra)
                return _plan(root, private, args)
        if args.operation == 'run':
            return _start(private, args.plan_id, access)
        if args.operation == 'jobs':
            return {'jobs': [_status(private, row['job_id']) for row in JobStore(private).list()]}
        if args.operation == 'status':
            return _status(private, args.job_id)
        if args.operation == 'cancel':
            row = JobStore(private).get(args.job_id)
            if row['status'] == 'planned':
                return _summary(JobStore(private).update(args.job_id, status='cancelled', finished_at=now()))
            if row['status'] not in TERMINAL:
                JobStore(private).update(args.job_id, status='cancelling', timeout_abort=False)
            return _status(private, args.job_id)
        return _publish(root, private, args.job_id, args.max_table_rows, access)


def poll_pending(metadata_root: Path):
    """Trusted background reconciliation; remote jobs outlive browser/server processes."""
    parent = metadata_root / '.pipelines'
    if not parent.exists():
        return
    for private in parent.iterdir():
        if not private.is_dir():
            continue
        with _lock(private / '.broker.lock'):
            for record in JobStore(private).list():
                if record['status'] in ACTIVE:
                    _status(private, record['job_id'])


def start_reconciler(metadata_root: Path):
    """Start remote-job reconciliation independently of disposable Docker workers."""
    from threading import Event, Thread
    stopped = Event()

    def poll():
        while not stopped.is_set():
            try:
                poll_pending(metadata_root)
            except Exception:
                # Reconciliation is retryable; never resubmit a remote job.
                pass
            stopped.wait(5)

    Thread(target=poll, daemon=True, name='remote-pipeline-reconciliation').start()
    return stopped


@contextmanager
def bundle_stream(root, identifier, *, access):
    """Build a ZIP only on download, with a disk reservation and automatic cleanup."""
    import zipfile
    from isolation.storage import reserve, release
    private = _owned(root, access)
    record = JobStore(private).get(identifier)
    if record['status'] != 'succeeded': raise ValueError('Results require a succeeded job.')
    outputs = record.get('result', {}).get('output_records', [])
    budget = sum(int(item.get('size', 0)) + 65536 for item in outputs) + 65536
    reservation = reserve(access, root.name, budget)
    try:
        with tempfile.TemporaryDirectory(dir=access.metadata_root) as temporary:
            path = Path(temporary) / 'results.zip'
            with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
                for index, item in enumerate(outputs):
                    name = f"{index:03d}_" + Path(item.get('path') or item.get('name') or 'artifact').name
                    with archive.open(name, 'w', force_zip64=True) as output:
                        if item.get('remote'):
                            with remote_stream(root, _remote_file(record, index)['path'], access=access) as (response, _):
                                actual = copy_stream(response['Body'], output, int(item['size']))
                                if actual['size'] != item['size']: raise ValueError('Incomplete remote artifact.')
                        elif item.get('exists'):
                            if service.digest(confined(private, item['workspace_path'])) != item['sha256']:
                                raise ValueError('Stored output changed.')
                            with open_regular(private, item['workspace_path']) as source:
                                copy_stream(source, output, limits().file_bytes)
            if path.stat().st_size > budget: raise ValueError('ZIP exceeded its reserved storage.')
            with path.open('rb') as stream:
                yield stream
    finally:
        release(access, reservation)
