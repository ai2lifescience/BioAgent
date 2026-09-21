"""Search public web pages and return bounded source excerpts."""

from __future__ import annotations

from typing import Annotated

from agents import RunContextWrapper
from pydantic import Field

from harness.context import AgentRunContext
from tools.infrastructure.tooling.results import run_workflow
from tools.infrastructure.tooling.tooling import bio_function_tool

from .workflow import web_research as _workflow


@bio_function_tool()
async def web_research(
    ctx: RunContextWrapper[AgentRunContext],
    query: Annotated[str, Field(min_length=3, max_length=500, description="Current topic or question to research on public web pages.")],
    domains: Annotated[list[str] | None, Field(description="Optional domains to restrict results, such as ncbi.nlm.nih.gov.")] = None,
    max_sources: Annotated[int, Field(ge=1, le=10, description="Maximum sources to collect.")] = 5,
    fetch_content: Annotated[bool, Field(description="Fetch bounded page excerpts in addition to search snippets.")] = True,
) -> str:
    """Research a current topic using public web sources and preserve URLs.

    Use this for current facts or a multi-source web question. For curated
    biological records use the NCBI/database tools, which provide stronger
    domain-specific identifiers.
    """
    return await run_workflow(
        ctx.context,
        "web_research",
        _workflow,
        {"query": query, "domains": domains, "max_sources": max_sources, "fetch_content": fetch_content},
        category="web_research",
        with_progress=False,
    )


__all__ = ["web_research"]
