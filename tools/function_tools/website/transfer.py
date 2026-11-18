"""Natural-language tool surface for any configured backend connector."""
import json
import asyncio
import time
from typing import Any
from agents import RunContextWrapper
from harness.context import AgentRunContext
from tools.infrastructure.tool_support.decorators import bio_function_tool
from tools.infrastructure.tool_support.results import FunctionContract, FunctionResult
from web_bridge.transfer.service import Transfers
from tools.infrastructure.pipeline_engine.broker import get_plan

class TransferResult(FunctionContract):
    value: dict[str, Any]

def _result_sync_job(context: AgentRunContext, job_id: str) -> dict[str, Any]:
    """Load an owned broker job from the session's protected pipeline store."""
    workspace=context.execution_access.workspace(context.session_id)
    return get_plan(workspace,job_id,access=context.execution_access)

def record_transfer(ctx, tool_name, arguments, value):
    """Record durable transfer handles so the runtime can monitor them without model turns."""
    context=ctx.context
    public_value=context.public(value)
    record={
        'tool':tool_name, 'arguments':context.public(arguments),
        'result':{'value':public_value}, 'status':'ok', 'error':None,
        'error_type':None, 'tool_calls':[],
    }
    context.tool_results.append(record)
    context.record('website_transfer_status',transfer_id=public_value.get('transfer_id'),
                   operation=public_value.get('operation'),state=public_value.get('state'))
    return record

async def submit(ctx, tool_name, site, operation, payload):
    service=Transfers()
    value=await asyncio.to_thread(service.create,ctx.context.session_id,site,operation,payload)
    record=record_transfer(ctx,tool_name,{'site_id':site,'operation':operation},value)
    deadline=time.monotonic()+25
    while value['state'] in {'queued','running'} and time.monotonic()<deadline:
        await asyncio.sleep(.5)
        value=await asyncio.to_thread(service.status,value['transfer_id'])
    public_value=ctx.context.public(value)
    record['result']={'value':public_value}
    return FunctionResult[TransferResult](status='ok',data=TransferResult(value=public_value))

@bio_function_tool(timeout=60)
async def website_connections(ctx: RunContextWrapper[AgentRunContext]) -> FunctionResult[TransferResult]:
    """List websites linked to the current user, their backend capabilities, destination fields and last contact. No browser required; credentials are never exposed."""
    return FunctionResult[TransferResult](status='ok',data=TransferResult(value={'connections':Transfers().connections()}))

@bio_function_tool(timeout=60)
async def website_search(ctx: RunContextWrapper[AgentRunContext], site_id: str, query: str = '', offset: int = 0) -> FunctionResult[TransferResult]:
    """Search owned projects, samples and file resources at a linked website. Use exact returned resource IDs for pulling. Results are paginated."""
    return await submit(ctx,'website_search',site_id,'search',{'query':query,'offset':max(0,offset)})

@bio_function_tool(timeout=60)
async def website_pull(ctx: RunContextWrapper[AgentRunContext], site_id: str, resource_id: str) -> FunctionResult[TransferResult]:
    """Download a website resource into this session for analysis. Use a resource ID returned by website_search. Check transfer status before using a pending download."""
    return await submit(ctx,'website_pull',site_id,'pull',{'resource_id':resource_id})

@bio_function_tool(timeout=60)
async def website_push(ctx: RunContextWrapper[AgentRunContext], site_id: str, paths: list[str], destination_json: str, create_missing: bool = True) -> FunctionResult[TransferResult]:
    """Push selected ordinary workspace files to a linked website. For MSCAN pipeline results, use website_result_sync so MSCAN retrieves and parses the Cromwell workflow itself. For MSCAN source data use destination_json {project, sample, data_type}; optionally source_slots maps R1/R2 or genome to selected paths. Missing named destinations are created when create_missing is true. Existing sources are never overwritten."""
    destination=json.loads(destination_json)
    if not isinstance(destination,dict): raise ValueError("Destination must be a JSON object.")
    if not destination: raise ValueError('Specify a destination.')
    return await submit(ctx,'website_push',site_id,'push',{'paths':paths,'destination':destination,'create_missing':create_missing})

@bio_function_tool(timeout=60)
async def website_result_sync(ctx: RunContextWrapper[AgentRunContext], site_id: str, job_id: str,
                              destination_json: str, create_missing: bool = True) -> FunctionResult[TransferResult]:
    """Explicitly synchronize one succeeded remote Cromwell pipeline result to MSCAN without transferring BioAgent files. BioAgent uses job_id only to verify ownership, then sends MSCAN the Cromwell task ID, pipeline name and destination. MSCAN uses its own Cromwell access and native parser. Use this only after the user asks to synchronize that result. destination_json is {project, sample, data_type: meta/shortReads/genomic/synthetic}."""
    destination=json.loads(destination_json)
    if not isinstance(destination,dict) or not destination:
        raise ValueError('Specify a destination JSON object.')
    record=await asyncio.to_thread(_result_sync_job,ctx.context,job_id)
    if record.get('status') != 'succeeded':
        raise ValueError('Result synchronization requires a succeeded pipeline job.')
    remote_id=record.get('remote_id')
    if not remote_id:
        raise ValueError('Result synchronization requires a remote Cromwell pipeline job.')
    pipeline_name=str((record.get('plan') or {}).get('pipeline_name') or '')
    if not pipeline_name:
        raise ValueError('Pipeline job has no pipeline name.')
    return await submit(ctx,'website_result_sync',site_id,'result_sync',{
        'cromwell_task_id':remote_id, 'pipeline_name':pipeline_name,
        'result_sync_protocol_version':1, 'pipeline_contract_version':1,
        'execution_engine':'cromwell',
        'destination':destination, 'create_missing':create_missing,
    })

@bio_function_tool(timeout=60)
async def website_transfer_status(ctx: RunContextWrapper[AgentRunContext], transfer_id: str) -> FunctionResult[TransferResult]:
    """Check a queued push, pull, search or result synchronization. A completed result synchronization reports MSCAN's native import outcome; failures contain the backend error."""
    value=await asyncio.to_thread(Transfers().status,transfer_id)
    record_transfer(ctx,'website_transfer_status',{'transfer_id':transfer_id},value)
    return FunctionResult[TransferResult](status='ok',data=TransferResult(value=value))

@bio_function_tool(timeout=60)
async def website_transfer_retry(ctx: RunContextWrapper[AgentRunContext], transfer_id: str) -> FunctionResult[TransferResult]:
    """Resume a failed transfer after its reported problem is resolved. Reuses the command ID and destination to avoid duplicate records."""
    value=await asyncio.to_thread(Transfers().retry,transfer_id)
    record_transfer(ctx,'website_transfer_retry',{'transfer_id':transfer_id},value)
    return FunctionResult[TransferResult](status='ok',data=TransferResult(value=value))

TRANSFER_TOOLS=[website_transfer_retry,website_connections,website_search,website_pull,website_push,website_result_sync,website_transfer_status]
