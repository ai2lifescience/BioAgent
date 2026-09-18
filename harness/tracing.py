"""SDK lifecycle hooks mapped to Pipeline2Agent's local progress events."""

from __future__ import annotations

from typing import Any
from threading import RLock

from agents import Agent, RunHooks
from agents.run_context import AgentHookContext, RunContextWrapper
from agents.tracing import TracingProcessor, set_trace_provider
from agents.tracing.provider import DefaultTraceProvider

from .context import AgentRunContext


class AgentHooks(RunHooks[AgentRunContext]):
    async def on_agent_start(self, context: AgentHookContext[AgentRunContext], agent: Agent[Any]) -> None:
        context.context.record("agent_started", agent=agent.name, message=f"Agent started: {agent.name}.")

    async def on_agent_end(self, context: AgentHookContext[AgentRunContext], agent: Agent[Any], output: Any) -> None:
        context.context.record("agent_finished", agent=agent.name, message=f"Agent finished: {agent.name}.")

    async def on_tool_start(self, context: RunContextWrapper[AgentRunContext], _agent: Agent[Any], tool: Any) -> None:
        context.context.record("sdk_tool_started", tool=getattr(tool, "name", str(tool)))

    async def on_tool_end(self, context: RunContextWrapper[AgentRunContext], _agent: Agent[Any], tool: Any, result: Any) -> None:
        context.context.record("sdk_tool_finished", tool=getattr(tool, "name", str(tool)))

    async def on_handoff(self, context: RunContextWrapper[AgentRunContext], from_agent: Agent[Any], to_agent: Agent[Any]) -> None:
        context.context.record("handoff", from_agent=from_agent.name, to_agent=to_agent.name)

    async def on_llm_start(self, context, agent, system_prompt, input_items) -> None:
        context.context.record("model_requested", agent=agent.name)

    async def on_llm_end(self, context, agent, response) -> None:
        usage = response.usage
        context.context.record("model_responded", agent=agent.name, input_tokens=usage.input_tokens, output_tokens=usage.output_tokens)


class LocalTraceProcessor(TracingProcessor):
    """Consume real SDK spans locally, without creating an OpenAI exporter."""

    def __init__(self) -> None:
        self.contexts: dict[str, AgentRunContext] = {}
        self.lock = RLock()

    def bind(self, trace_id: str, context: AgentRunContext) -> None:
        with self.lock:
            self.contexts[trace_id] = context

    def unbind(self, trace_id: str) -> None:
        with self.lock:
            self.contexts.pop(trace_id, None)

    def on_trace_start(self, trace) -> None:
        with self.lock:
            context = self.contexts.get(trace.trace_id)
        if context:
            context.record("sdk_trace_started", trace_id=trace.trace_id)

    def on_trace_end(self, trace) -> None:
        with self.lock:
            context = self.contexts.get(trace.trace_id)
        if context:
            context.record("sdk_trace_finished", trace_id=trace.trace_id)

    def on_span_start(self, span) -> None:
        pass

    def on_span_end(self, span) -> None:
        with self.lock:
            context = self.contexts.get(span.trace_id)
        if context:
            data = span.span_data
            context.record(
                "sdk_span_finished", trace_id=span.trace_id, span_id=span.span_id,
                parent_id=getattr(span, "parent_id", None), span_type=data.type,
                name=getattr(data, "name", None), model=getattr(data, "model", None),
                started_at=span.started_at, ended_at=span.ended_at,
                has_error=bool(getattr(span, "error", None)),
            )

    def shutdown(self) -> None:
        pass

    def force_flush(self) -> None:
        pass


LOCAL_TRACES = LocalTraceProcessor()
_configured = False


def configure_tracing() -> None:
    global _configured
    with LOCAL_TRACES.lock:
        if not _configured:
            provider = DefaultTraceProvider()
            provider.register_processor(LOCAL_TRACES)
            set_trace_provider(provider)
            _configured = True
