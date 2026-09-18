"""Scientific reporting agents executed by the Agents SDK."""

from __future__ import annotations

from typing import Any

from agents import Agent, ModelProvider, ModelSettings, Runner, RunConfig
from agents.tracing import gen_trace_id


async def run_reporting_agent(
    messages: list[dict[str, Any]],
    model_key: str,
    provider: ModelProvider,
    *,
    temperature: float,
    bio_context: Any = None,
) -> str:
    """Run one opinion or synthesis using the batch's shared provider."""
    from harness.tracing import LOCAL_TRACES, configure_tracing

    configure_tracing()
    trace_id = gen_trace_id()
    if bio_context is not None:
        LOCAL_TRACES.bind(trace_id, bio_context)
    try:
        agent = Agent(
            name=f"reporting_{model_key.replace('-', '_')}",
            instructions=(
                "You are a scientific reporting specialist. Answer only from the "
                "provided messages and preserve uncertainty and citations."
            ),
            model=model_key,
            model_settings=ModelSettings(temperature=temperature),
        )
        result = await Runner.run(
            agent, messages,
            run_config=RunConfig(
                model_provider=provider,
                workflow_name="BioAgent reporting", trace_id=trace_id,
                trace_include_sensitive_data=False,
            ),
        )
        content = str(result.final_output or "").strip()
        if not content:
            raise RuntimeError(f"Model '{model_key}' returned an empty response.")
        return content
    finally:
        if bio_context is not None:
            LOCAL_TRACES.unbind(trace_id)
