"""BioAgent orchestration layer."""

from __future__ import annotations

import json
from typing import Any, Callable

from models.config import DEFAULT_AGENT_MODEL_KEY, DEFAULT_MAX_SKILL_STEPS
from models.llm_client import LLMClient
from registries.skill_registry import SKILL_SPECS, list_skill_prompt_hints

from .artifacts import COMPACT_RESULT_KEYS, SessionArtifactStore
from .evidence import EvidenceCollector
from .memory import InMemoryStateStore
from .planner import Planner, TaskPlan
from .prompts import build_direct_response_prompt, build_skill_loop_prompt
from .router import IntentRouter
from execution.skill_executor import (
    SkillExecutor,
    llm_skill_calls_from_message,
    message_to_dict,
    skill_call_parts,
)
from .trace import InMemoryTraceStore
from .verifier import Verifier


def _plan_to_dict(plan: TaskPlan) -> dict[str, Any]:
    return {
        "mode": plan.mode,
        "rationale": plan.rationale,
        "steps": [
            {
                "kind": step.kind,
                "name": step.name,
                "arguments": step.arguments,
            }
            for step in plan.steps
        ],
    }


def _record_has_error(record: dict[str, Any]) -> bool:
    result = record.get("result")
    return isinstance(result, dict) and bool(result.get("error"))


def _record_needs_user_input(record: dict[str, Any]) -> bool:
    result = record.get("result")
    return isinstance(result, dict) and bool(result.get("needs_input"))


def _ask_user_answer(record: dict[str, Any]) -> str:
    result = record.get("result")
    if not isinstance(result, dict):
        return "More information is needed before BioAgent can continue."
    question = str(result.get("question") or "").strip()
    return question or "More information is needed before BioAgent can continue."


def _exception_summary(exc: Exception) -> str:
    """Return a compact error suitable for trace events and client logs."""
    detail = " ".join(str(exc).split())
    return f"{type(exc).__name__}: {detail[:300]}" if detail else type(exc).__name__


ASK_USER_SKILL_SPECS = [
    skill_spec
    for skill_spec in SKILL_SPECS
    if skill_spec.get("function", {}).get("name") == "ask_user"
]


def _format_skill_record_summary(record: dict[str, Any]) -> str:
    result = record.get("result")
    if not isinstance(result, dict):
        return "non-dict result"
    if result.get("error"):
        return f"error={result['error']}"

    parts: list[str] = []
    for key in COMPACT_RESULT_KEYS:
        if key in result and result[key] not in (None, "", []):
            parts.append(f"{key}={result[key]}")

    files = result.get("files")
    if isinstance(files, list):
        parts.append(f"files={len(files)}")
    tool_calls = record.get("tool_calls")
    if isinstance(tool_calls, list):
        parts.append(f"tools={len(tool_calls)}")
    return ", ".join(str(part) for part in parts[:8]) or "ok"


def _format_evidence_summary(evidence: dict[str, Any]) -> str:
    return (
        f"citations={len(evidence.get('citations', []))}, "
        f"records={len(evidence.get('record_ids', []))}, "
        f"files={len(evidence.get('files', []))}, "
        f"tools={len(evidence.get('tools', []))}"
    )


def _format_verification_summary(verification: dict[str, Any]) -> str:
    return (
        f"status={verification.get('status', 'unknown')}, "
        f"warnings={len(verification.get('warnings', []))}, "
        f"errors={len(verification.get('errors', []))}"
    )


class BioAgentOrchestrator:
    """Coordinate routing, planning, execution, verification, and responses."""

    def __init__(
        self,
        router: IntentRouter | None = None,
        planner: Planner | None = None,
        skill_executor: SkillExecutor | None = None,
        memory: InMemoryStateStore | None = None,
        trace_store: InMemoryTraceStore | None = None,
        artifact_store: SessionArtifactStore | None = None,
        evidence_collector: EvidenceCollector | None = None,
        verifier: Verifier | None = None,
        llm_client_factory: Callable[[str], Any] | None = None,
    ) -> None:
        self.router = router or IntentRouter()
        self.planner = planner or Planner()
        self.skill_executor = skill_executor or SkillExecutor()
        self.memory = memory or InMemoryStateStore()
        self.trace_store = trace_store or InMemoryTraceStore()
        self.artifact_store = artifact_store or SessionArtifactStore(self.memory)
        self.evidence_collector = evidence_collector or EvidenceCollector()
        self.verifier = verifier or Verifier()
        self.llm_client_factory = llm_client_factory or LLMClient

    def _new_llm_client(self, model_key: str) -> Any:
        return self.llm_client_factory(model_key=model_key)

    def run(
        self,
        user_request: str,
        session_id: str | None = None,
        model_key: str = DEFAULT_AGENT_MODEL_KEY,
        max_skill_steps: int = DEFAULT_MAX_SKILL_STEPS,
        log_fn: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        with self.memory.locked_session(
            session_id=session_id,
            user_request=user_request,
        ) as (session, session_created):
            return self._run_for_session(
                session=session,
                user_request=user_request,
                session_created=session_created,
                model_key=model_key,
                max_skill_steps=max_skill_steps,
                log_fn=log_fn,
            )

    def _run_for_session(
        self,
        session,
        user_request: str,
        session_created: bool,
        model_key: str,
        max_skill_steps: int,
        log_fn: Callable[[str], None] | None,
    ) -> dict[str, Any]:
        session.user_request = user_request
        session.skill_results = []
        trace_start_index = len(self.trace_store.list_events(session.session_id))
        self.artifact_store.prepare_run(session)
        session.metadata["run"]["trace_start_index"] = trace_start_index
        public_run = {
            key: value
            for key, value in session.metadata["run"].items()
            if key != "trace_start_index"
        }
        self.trace_store.record(
            session.session_id,
            "session_started",
            request=user_request,
            session_created=session_created,
            run=public_run,
        )
        route = self.router.route(user_request)
        self.trace_store.record(session.session_id, "intent_routed", route=route.as_dict())
        plan = self.planner.plan(user_request=user_request, route=route, model_key=model_key)
        self.trace_store.record(session.session_id, "plan_created", plan=_plan_to_dict(plan))

        if log_fn:
            log_fn(f"[orchestrator] Run: {public_run.get('run_id')}.")
            log_fn(f"[orchestrator] Route: {route.mode}.")
            log_fn(f"[orchestrator] Plan: {plan.mode}.")

        return self._run_plan(
            session=session,
            route=route.as_dict(),
            plan=plan,
            model_key=model_key,
            max_skill_steps=max_skill_steps,
            log_fn=log_fn,
        )

    def _run_plan(
        self,
        session,
        route: dict[str, Any],
        plan: TaskPlan,
        model_key: str,
        max_skill_steps: int,
        log_fn: Callable[[str], None] | None,
    ) -> dict[str, Any]:
        answer: str | None = None
        messages: list[dict[str, Any]] = [{"role": "user", "content": session.user_request}]
        evidence: dict[str, Any] | None = None
        verification: dict[str, Any] | None = None

        for step in plan.steps:
            if step.kind == "skill":
                if log_fn:
                    log_fn(f"[orchestrator] Skill started: {step.name}.")
                self.trace_store.record(
                    session.session_id,
                    "skill_started",
                    skill=step.name,
                    arguments=step.arguments,
                )
                record = self.skill_executor.execute_skill(
                    name=step.name,
                    arguments=step.arguments,
                    log_fn=log_fn,
                    user_context=self.artifact_store.user_context(session),
                )
                session.skill_results.append(record)
                self.artifact_store.register_result(session, record)
                self.trace_store.record(
                    session.session_id,
                    "skill_finished",
                    skill=record.get("skill"),
                    category=record.get("category"),
                    has_error=_record_has_error(record),
                )
                if log_fn:
                    log_fn(
                        f"[orchestrator] Skill finished: {record.get('skill')} | "
                        f"{_format_skill_record_summary(record)}."
                    )
                continue

            if step.kind == "llm_skill_loop":
                if log_fn:
                    log_fn(f"[orchestrator] Starting model-guided skill loop | max_steps={max_skill_steps}.")
                loop_result = self._run_llm_skill_loop_step(
                    session=session,
                    model_key=model_key,
                    max_skill_steps=max_skill_steps,
                    log_fn=log_fn,
                )
                messages = loop_result["messages"]
                answer = loop_result.get("answer")
                self.trace_store.record(
                    session.session_id,
                    "llm_skill_loop_completed",
                    has_answer=bool(answer),
                    message_count=len(messages),
                )
                if log_fn:
                    log_fn(f"[orchestrator] Model-guided skill loop completed | messages={len(messages)}.")
                continue

            if step.kind == "llm_response":
                response_result = self._run_llm_response_step(
                    session=session,
                    model_key=model_key,
                    log_fn=log_fn,
                )
                messages = response_result["messages"]
                answer = response_result["answer"]
                self.trace_store.record(
                    session.session_id,
                    "llm_response_completed",
                    message_count=len(messages),
                )
                if log_fn:
                    log_fn(f"[orchestrator] Direct model response completed | messages={len(messages)}.")
                continue

            if step.kind == "evidence":
                evidence = self._collect_evidence(session)
                self.trace_store.record(
                    session.session_id,
                    "evidence_collected",
                    citation_count=len(evidence.get("citations", [])),
                    record_id_count=len(evidence.get("record_ids", [])),
                    file_count=len(evidence.get("files", [])),
                )
                if log_fn:
                    log_fn(f"[orchestrator] Evidence collected | {_format_evidence_summary(evidence)}.")
                continue

            if step.kind == "verification":
                if evidence is None:
                    evidence = self._collect_evidence(session)
                verification = self.verifier.verify(
                    user_request=session.user_request,
                    skill_results=session.skill_results,
                    evidence=evidence,
                    allow_model_knowledge=plan.mode == "llm_response",
                )
                self.trace_store.record(
                    session.session_id,
                    "verification_completed",
                    verification_status=verification.get("status"),
                )
                if log_fn:
                    log_fn(
                        f"[orchestrator] Verification completed | "
                        f"{_format_verification_summary(verification)}."
                    )
                continue

            if step.kind == "respond":
                if step.name == "control_response":
                    answer = str(step.arguments.get("answer", ""))
                    evidence = evidence or self._collect_evidence(session)
                    verification = verification or {"status": "ok", "warnings": [], "errors": []}
                    self.trace_store.record(session.session_id, "control_response_generated")
                elif answer is None:
                    answer = self._default_answer_from_skill_results(session)
                self.trace_store.record(session.session_id, "response_generated", response_step=step.name)
                if log_fn:
                    log_fn(f"[orchestrator] Response generated: {step.name}.")
                continue

            raise RuntimeError(f"Unsupported plan step kind: {step.kind}")

        if answer is None:
            answer = self._default_answer_from_skill_results(session)
        return self._finalize_model_answer(
            answer=answer,
            messages=messages,
            route=route,
            plan=plan,
            session=session,
            evidence=evidence,
            verification=verification,
        )

    def _complete_with_tool_fallback(
        self,
        llm_client: Any,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        temperature: float,
        session,
        model_key: str,
        mode: str,
        log_fn: Callable[[str], None] | None,
    ) -> tuple[Any, bool]:
        """Complete with tools, then retry once without them if needed."""
        fallback_reason: str | None = None
        tool_calling_disabled = not bool(getattr(llm_client, "supports_tool_calling", True))
        if tool_calling_disabled:
            fallback_reason = "tool calling is disabled for this model"
        else:
            try:
                response = llm_client.complete(
                    messages=messages,
                    tools=tools,
                    tool_choice="auto",
                    temperature=temperature,
                )
                return response, False
            except Exception as exc:
                fallback_reason = _exception_summary(exc)

        self.trace_store.record(
            session.session_id,
            "model_tool_fallback_started",
            model_key=model_key,
            model_label=llm_client.model_label,
            mode=mode,
            reason=fallback_reason,
        )
        if log_fn:
            if tool_calling_disabled:
                log_fn("[orchestrator] Tool calling is disabled; requesting a normal model response.")
            else:
                log_fn(
                    "[orchestrator] Tool calling failed; retrying once "
                    f"without tools ({fallback_reason})."
                )
        try:
            response = llm_client.complete_without_tools(
                messages=messages,
                temperature=temperature,
            )
        except Exception as exc:
            fallback_error = _exception_summary(exc)
            self.trace_store.record(
                session.session_id,
                "model_tool_fallback_failed",
                model_key=model_key,
                model_label=llm_client.model_label,
                mode=mode,
                reason=fallback_reason,
                error=fallback_error,
            )
            if log_fn:
                log_fn(f"[orchestrator] Tool-free retry failed: {fallback_error}.")
            raise RuntimeError(
                f"{llm_client.model_label} did not respond. Tool-call attempt: "
                f"{fallback_reason}; tool-free retry: {fallback_error}."
            ) from exc

        self.trace_store.record(
            session.session_id,
            "model_tool_fallback_completed",
            model_key=model_key,
            model_label=llm_client.model_label,
            mode=mode,
            reason=fallback_reason,
        )
        if log_fn:
            log_fn("[orchestrator] Tool-free retry completed; returning a normal model response.")
        return response, True

    def _run_llm_response_step(
        self,
        session,
        model_key: str,
        log_fn: Callable[[str], None] | None,
    ) -> dict[str, Any]:
        llm_client = self._new_llm_client(model_key)
        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": build_direct_response_prompt(llm_client.model_label),
            },
            *self.memory.recent_messages(session),
            {"role": "user", "content": session.user_request},
        ]
        if log_fn:
            log_fn(f"[orchestrator] Asking {llm_client.model_label} for a direct answer.")
        self.trace_store.record(
            session.session_id,
            "model_requested",
            model_key=model_key,
            model_label=llm_client.model_label,
            mode="llm_response",
        )
        response, used_tool_fallback = self._complete_with_tool_fallback(
            llm_client=llm_client,
            messages=messages,
            tools=ASK_USER_SKILL_SPECS,
            temperature=0.2,
            session=session,
            model_key=model_key,
            mode="llm_response",
            log_fn=log_fn,
        )
        message = response.choices[0].message
        messages.append(message_to_dict(message))
        skill_calls = llm_skill_calls_from_message(message)
        self.trace_store.record(
            session.session_id,
            "model_responded",
            mode="llm_response",
            skill_call_count=len(skill_calls),
            tool_fallback=used_tool_fallback,
        )
        if skill_calls:
            call_id, record = self.skill_executor.execute_llm_skill_call(
                skill_calls[0],
                log_fn=log_fn,
                user_context=self.artifact_store.user_context(session),
            )
            session.skill_results.append(record)
            self.artifact_store.register_result(session, record)
            self.trace_store.record(
                session.session_id,
                "llm_skill_call_executed",
                call_id=call_id,
                skill=record.get("skill"),
                category=record.get("category"),
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call_id,
                    "name": record["skill"],
                    "content": json.dumps(record["result"], ensure_ascii=False),
                }
            )
            if _record_needs_user_input(record):
                if log_fn:
                    log_fn("[orchestrator] Waiting for the user to answer a clarification question.")
                return {"answer": _ask_user_answer(record), "messages": messages}
        return {"answer": message.content or "", "messages": messages}

    def _run_llm_skill_loop_step(
        self,
        session,
        model_key: str,
        max_skill_steps: int,
        log_fn: Callable[[str], None] | None,
    ) -> dict[str, Any]:
        llm_client = self._new_llm_client(model_key)
        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": build_skill_loop_prompt(
                    llm_client.model_label,
                    skill_hints=list_skill_prompt_hints(),
                ),
            },
            *self.memory.recent_messages(session),
            {"role": "user", "content": session.user_request},
        ]

        for step_index in range(max_skill_steps):
            if log_fn:
                log_fn(
                    f"[orchestrator] Asking {llm_client.model_label} to choose "
                    f"the next action ({step_index + 1}/{max_skill_steps})."
                )
            self.trace_store.record(
                session.session_id,
                "model_requested",
                model_key=model_key,
                model_label=llm_client.model_label,
            )

            response, used_tool_fallback = self._complete_with_tool_fallback(
                llm_client=llm_client,
                messages=messages,
                tools=SKILL_SPECS,
                temperature=0.1,
                session=session,
                model_key=model_key,
                mode="llm_skill_loop",
                log_fn=log_fn,
            )
            message = response.choices[0].message
            messages.append(message_to_dict(message))
            self.trace_store.record(
                session.session_id,
                "model_responded",
                skill_call_count=len(llm_skill_calls_from_message(message)),
                tool_fallback=used_tool_fallback,
            )

            skill_calls = llm_skill_calls_from_message(message)
            if not skill_calls:
                if log_fn:
                    log_fn("[orchestrator] Model returned a final answer.")
                return {"answer": message.content or "", "messages": messages}

            if log_fn:
                names = [skill_call_parts(skill_call)[1] or "unknown" for skill_call in skill_calls]
                log_fn(f"[orchestrator] Model selected skill call(s): {', '.join(names)}.")
            ask_user_calls = [
                skill_call
                for skill_call in skill_calls
                if skill_call_parts(skill_call)[1] == "ask_user"
            ]
            if ask_user_calls:
                skill_calls = ask_user_calls[:1]

            for skill_call in skill_calls:
                call_id, record = self.skill_executor.execute_llm_skill_call(
                    skill_call,
                    log_fn=log_fn,
                    user_context=self.artifact_store.user_context(session),
                )
                session.skill_results.append(record)
                self.artifact_store.register_result(session, record)
                self.trace_store.record(
                    session.session_id,
                    "llm_skill_call_executed",
                    call_id=call_id,
                    skill=record.get("skill"),
                    category=record.get("category"),
                )
                if log_fn:
                    log_fn(
                        f"[orchestrator] LLM skill call completed: {record.get('skill')} | "
                        f"{_format_skill_record_summary(record)}."
                    )

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "name": record["skill"],
                        "content": json.dumps(record["result"], ensure_ascii=False),
                    }
                )
                if _record_needs_user_input(record):
                    if log_fn:
                        log_fn("[orchestrator] Waiting for the user to answer a clarification question.")
                    return {"answer": _ask_user_answer(record), "messages": messages}

        return {
            "answer": "Stopped because the maximum number of skill-calling steps was reached.",
            "messages": messages,
        }

    def _finalize_model_answer(
        self,
        answer: str,
        messages: list[dict[str, Any]],
        session,
        route: dict[str, Any],
        plan: TaskPlan,
        evidence: dict[str, Any] | None = None,
        verification: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if evidence is None:
            evidence = self._collect_evidence(session)
        if verification is None:
            verification = self.verifier.verify(
                user_request=session.user_request,
                skill_results=session.skill_results,
                evidence=evidence,
            )
        self.trace_store.record(
            session.session_id,
            "run_finalized",
            verification_status=verification.get("status"),
            skill_count=len(session.skill_results),
        )
        run = dict(session.metadata.get("run") or {})
        trace_start = int(run.get("trace_start_index", 0) or 0)
        public_run = {
            key: value
            for key, value in run.items()
            if key != "trace_start_index"
        }
        self.memory.append_message(
            session.session_id,
            "user",
            session.user_request,
            metadata={"run_id": public_run.get("run_id")},
        )
        self.memory.append_message(
            session.session_id,
            "assistant",
            answer,
            metadata={"run_id": public_run.get("run_id")},
        )
        return self._build_result(
            answer=answer,
            messages=messages,
            evidence=evidence,
            verification=verification,
            route=route,
            plan=_plan_to_dict(plan),
            trace=self.trace_store.list_events(session.session_id, start=trace_start),
            session_id=session.session_id,
            run=public_run,
            artifacts=self.artifact_store.for_run(session, public_run.get("run_id")),
        )

    def _collect_evidence(self, session) -> dict[str, Any]:
        return self.evidence_collector.collect(session.skill_results)

    def _default_answer_from_skill_results(self, session) -> str:
        if session.skill_results:
            return self._answer_for_skill_record(session.skill_results[-1])
        return "No executable skill steps were found in the plan."

    @staticmethod
    def _answer_for_skill_record(record: dict[str, Any]) -> str:
        skill = record.get("skill", "")
        result = record.get("result") or {}

        if isinstance(result, dict) and result.get("error"):
            return f"Skill {skill} failed: {result['error']}"

        if isinstance(result, dict) and result.get("answer"):
            answer = str(result["answer"])
            report_path = result.get("report_path")
            if (
                report_path
                and result.get("presentation") != "downloads_only"
                and str(report_path) not in answer
            ):
                return f"{answer}\n\nReport saved to: {report_path}"
            return answer
        if isinstance(result, dict) and result.get("summary"):
            return str(result["summary"])
        return f"Skill {skill} completed: {result}"

    @staticmethod
    def _build_result(
        answer: str,
        messages: list[dict[str, Any]],
        evidence: dict[str, Any],
        verification: dict[str, Any],
        route: dict[str, Any],
        plan: dict[str, Any],
        trace: list[dict[str, Any]] | None = None,
        session_id: str | None = None,
        run: dict[str, Any] | None = None,
        artifacts: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        return {
            "answer": answer,
            "session_id": session_id,
            "run": run or {},
            "artifacts": artifacts or [],
            "messages": messages,
            "evidence": evidence,
            "verification": verification,
            "route": route,
            "plan": plan,
            "trace": trace or [],
        }
