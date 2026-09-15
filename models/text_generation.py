"""Generic text generation helpers for LLM-backed tasks."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from agents import Agent, ModelSettings, OpenAIChatCompletionsModel, Runner, RunConfig, set_default_openai_api
from agents.tracing import gen_trace_id

from .config import DEFAULT_AGENT_MODEL_KEY, get_default_model_id
from .openrouter_client import create_async_client


async def _run_agent(messages: list[dict[str, Any]], model_key: str, temperature: float, bio_context: Any = None) -> str:
    """Run a reporting request through the Agents SDK model boundary."""
    set_default_openai_api("chat_completions")
    client = create_async_client()
    trace_id = gen_trace_id()
    if bio_context is not None:
        from harness.tracing import LOCAL_TRACES
        LOCAL_TRACES.bind(trace_id, bio_context)
    try:
        agent = Agent(
            name=f"reporting_{model_key.replace('-', '_')}",
            instructions=(
                "You are a scientific reporting specialist. Answer only from the "
                "provided messages and preserve uncertainty and citations."
            ),
            model=OpenAIChatCompletionsModel(
                model=get_default_model_id(model_key), openai_client=client,
            ),
            model_settings=ModelSettings(temperature=temperature),
        )
        result = await Runner.run(
            agent, messages,
            run_config=RunConfig(
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
            from harness.tracing import LOCAL_TRACES
            LOCAL_TRACES.unbind(trace_id)
        await client.close()


def _run_agent_sync(messages: list[dict[str, Any]], model_key: str, temperature: float, bio_context: Any = None) -> str:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_run_agent(messages, model_key, temperature, bio_context))
    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(asyncio.run, _run_agent(messages, model_key, temperature, bio_context)).result()


def generate_from_messages(
    messages: list[dict[str, Any]],
    model_key: str = DEFAULT_AGENT_MODEL_KEY,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str | None = None,
    temperature: float = 0.2,
    bio_context: Any = None,
    **kwargs: Any,
) -> str:
    """Generate text from chat messages using a configured model."""
    if tools is not None or tool_choice is not None:
        raise ValueError("Reporting agents do not accept nested provider tool schemas.")
    if kwargs:
        raise ValueError(f"Unsupported reporting-agent options: {', '.join(sorted(kwargs))}")
    return _run_agent_sync(messages, model_key, temperature, bio_context)


def generate_text(
    system_prompt: str,
    user_prompt: str,
    model_key: str = DEFAULT_AGENT_MODEL_KEY,
    temperature: float = 0.2,
    **kwargs: Any,
) -> str:
    """Generate text from a system/user prompt pair."""
    return generate_from_messages(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        model_key=model_key,
        temperature=temperature,
        **kwargs,
    )
