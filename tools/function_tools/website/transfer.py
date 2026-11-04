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

class TransferResult(FunctionContract):
    value: dict[str, Any]

async def submit(ctx, site, operation, payload):
    service=Transfers()
    value=await asyncio.to_thread(service.create,ctx.context.session_id,site,operation,payload)
    deadline=time.monotonic()+25
    while value['state'] in {'queued','running'} and time.monotonic()<deadline:
        await asyncio.sleep(.5)
        value=await asyncio.to_thread(service.status,value['transfer_id'])
    return FunctionResult[TransferResult](status='ok',data=TransferResult(value=value))

@bio_function_tool(timeout=60)
async def website_connections(ctx: RunContextWrapper[AgentRunContext]) -> FunctionResult[TransferResult]:
    """List websites linked to the current user, their backend capabilities, destination fields and last contact. No browser required; credentials are never exposed."""
    return FunctionResult[TransferResult](status='ok',data=TransferResult(value={'connections':Transfers().connections()}))

@bio_function_tool(timeout=60)
async def website_search(ctx: RunContextWrapper[AgentRunContext], site_id: str, query: str = '', offset: int = 0) -> FunctionResult[TransferResult]:
    """Search owned projects, samples and file resources at a linked website. Use exact returned resource IDs for pulling. Results are paginated."""
    return await submit(ctx,site_id,'search',{'query':query,'offset':max(0,offset)})

@bio_function_tool(timeout=60)
async def website_pull(ctx: RunContextWrapper[AgentRunContext], site_id: str, resource_id: str) -> FunctionResult[TransferResult]:
    """Download a website resource into this session for analysis. Use a resource ID returned by website_search. Check transfer status before using a pending download."""
    return await submit(ctx,site_id,'pull',{'resource_id':resource_id})

@bio_function_tool(timeout=60)
async def website_push(ctx: RunContextWrapper[AgentRunContext], site_id: str, paths: list[str], destination_json: str, create_missing: bool = True) -> FunctionResult[TransferResult]:
    """Push selected session files/results, including owned remote pipeline-artifacts and pipeline-bundles/.../results.zip, to a linked website using its destination fields. Bundle pushes include their individual outputs automatically. Check native_imports for each job: only imported means native analysis is populated. Unsupported, incomplete and incompatible_sample_type results are delivered files, not successful native imports. Use website_connections to inspect available native_result_importers. Report native QC import only when native_qc_applied is true. For MSCAN use destination_json containing a JSON object {project: exact ID or name, sample: exact ID or name, data_type: meta/shortReads/genomic/synthetic}; optionally source_slots={R1: workspace path, R2: workspace path} or {genome: workspace path} inside destination for source data. Missing named destinations are created when create_missing is true. Existing sources are never overwritten. Ask the user to resolve ambiguous names. No browser or buttons required."""
    destination=json.loads(destination_json)
    if not isinstance(destination,dict): raise ValueError("Destination must be a JSON object.")
    if not destination: raise ValueError('Specify a destination.')
    return await submit(ctx,site_id,'push',{'paths':paths,'destination':destination,'create_missing':create_missing})

@bio_function_tool(timeout=60)
async def website_transfer_status(ctx: RunContextWrapper[AgentRunContext], transfer_id: str) -> FunctionResult[TransferResult]:
    """Check a queued push/pull/search. Succeeded pull results contain the actual downloaded workspace path; failures contain the backend error."""
    return FunctionResult[TransferResult](status='ok',data=TransferResult(value=await asyncio.to_thread(Transfers().status,transfer_id)))

@bio_function_tool(timeout=60)
async def website_transfer_retry(ctx: RunContextWrapper[AgentRunContext], transfer_id: str) -> FunctionResult[TransferResult]:
    """Resume a failed transfer after its reported problem is resolved. Reuses the command ID and destination to avoid duplicate records."""
    return FunctionResult[TransferResult](status='ok',data=TransferResult(value=await asyncio.to_thread(Transfers().retry,transfer_id)))

TRANSFER_TOOLS=[website_transfer_retry,website_connections,website_search,website_pull,website_push,website_transfer_status]
