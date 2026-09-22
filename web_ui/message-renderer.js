import { compactList, escapeHtml, fileNameFromPath, formatElapsed } from "/static/ui-utils.js";

export function createMessageRenderer({
  chat,
  agentIcon,
  artifactViewers,
  workspaceFileUrl,
  getConfig,
  formatModelLabel,
  getRunning,
  getSessionLoading,
  onApprovalBusy,
  onApprovalResult,
} = {}) {
  function statusClass(result) {
    const status = result?.status || "ok";
    if (status === "error") return "error";
    if (status === "warning") return "warning";
    return "ok";
  }

  function modelLabelForKey(modelKey) {
    const key = String(modelKey || "").trim();
    const model = (getConfig()?.models || []).find((item) => item.key === key);
    return model ? formatModelLabel(model) : (key || "Unknown model");
  }

  function debugStatus(result) {
    const status = String(result?.runtime?.status || result?.status || "ok");
    const labels = {
      ok: "Completed",
      pending_approval: "Waiting for approval",
      blocked: "Blocked by guardrail",
      error: "Failed",
      stopped: "Stopped",
    };
    const tone = status === "ok" ? "ok" : status === "pending_approval" || status === "stopped" ? "warning" : "error";
    return { status, label: labels[status] || status, tone };
  }

  function toolLabel(tool) {
    const labels = {
      database_lookup: "Database lookup",
      genome_read_features: "Read genome features",
      alphafold_download: "Download AlphaFold structure",
      document_read: "Read document",
      file_inspection: "Inspect file",
      genome_render_map: "Create genome map",
      ncbi_retrieval: "Retrieve NCBI records",
      pdb_download: "Download PDB structure",
      pipeline_shell: "Run pipeline command",
      pipeline_specialist: "Pipeline specialist",
      structure_inspect: "Inspect protein structure",
      sequence_stats: "Measure sequence",
      sequence_find_orfs: "Find sequence ORFs",
      report_review: "Review evidence",
      report_synthesize: "Draft cited report",
      report_write: "Save cited report",
      blast_search: "BLAST search",
    };
    return labels[String(tool || "")] || String(tool || "Agent operation").replaceAll("_", " ");
  }

  function evidenceOutputForTool(result, tool) {
    const evidence = result?.evidence || {};
    const records = [
      ...(Array.isArray(evidence.outputs) ? evidence.outputs : []),
      ...(Array.isArray(evidence.tool_outputs) ? evidence.tool_outputs : []),
    ];
    for (let index = records.length - 1; index >= 0; index -= 1) {
      if (records[index]?.tool === tool) return records[index];
    }
    return null;
  }

  function evidenceOutputSummary(result, tool) {
    const output = evidenceOutputForTool(result, tool);
    if (!output) return "No compact result summary was returned.";
    if (output.error) return String(output.error);
    if (output.summary) return String(output.summary);
    if (output.answer) return String(output.answer);
    if (output.status) return `Status: ${String(output.status)}`;
    return "Result returned.";
  }

  function traceEventDetail(event, result) {
    const data = event?.data || {};
    const tool = data.tool;
    if (tool) {
      const summary = evidenceOutputSummary(result, tool);
      return event.event === "tool_finished" || event.event === "sdk_tool_finished"
        ? summary
        : `Registered operation: ${tool}`;
    }
    if (event.event === "model_responded") {
      const input = Number(data.input_tokens || 0);
      const output = Number(data.output_tokens || 0);
      return input || output ? `Tokens: ${input.toLocaleString()} in · ${output.toLocaleString()} out` : "Decision received.";
    }
    if (event.event === "handoff") return `${data.from_agent || "Agent"} → ${data.to_agent || "specialist"}`;
    if (event.event === "run_blocked") return `Reason: ${data.reason || "request blocked"}.`;
    if (event.event === "run_paused") return "Approval is required before execution can continue.";
    if (event.event === "tool_failed") return String(data.error_type || "Tool execution failed.");
    if (event.event === "pipeline_command_finished") return `Status: ${data.status || "unknown"}.`;
    if (event.event === "guardrail_completed") {
      const warnings = Array.isArray(data.warnings) ? data.warnings : [];
      return warnings.length ? warnings.join(" ") : "No warnings.";
    }
    if (event.event === "run_finished") return `Tools used: ${data.tool_count || 0}.`;
    if (event.event === "run_failed") return String(data.error || "Run failed.");
    return String(data.message || "");
  }

  function traceEventTitle(event) {
    const data = event?.data || {};
    switch (event?.event) {
      case "run_started": return "Request accepted";
      case "agent_started": return `Agent started${data.agent ? ` · ${data.agent}` : ""}`;
      case "agent_finished": return `Agent finished${data.agent ? ` · ${data.agent}` : ""}`;
      case "model_requested": return "Agent selected the next step";
      case "model_responded": return "Agent decision received";
      case "handoff": return `Delegated to ${data.to_agent || "specialist"}`;
      case "tool_started":
      case "sdk_tool_started": return `Started · ${toolLabel(data.tool)}`;
      case "tool_finished":
      case "sdk_tool_finished": return `Finished · ${toolLabel(data.tool)}`;
      case "tool_failed": return `Tool failed · ${toolLabel(data.tool)}`;
      case "pipeline_command_finished": return "Pipeline command finished";
      case "guardrail_completed": return "Output safety check completed";
      case "guardrail_blocked": return "Safety guardrail blocked the request";
      case "run_blocked": return "Request blocked by a guardrail";
      case "approval_decision": return data.approved ? "Tool approval granted" : "Tool approval rejected";
      case "run_paused": return "Run paused for approval";
      case "run_finished": return "Run completed";
      case "run_failed": return "Run failed";
      default: return String(event?.event || "Activity").replaceAll("_", " ");
    }
  }

  function formatTraceTime(timestamp) {
    if (!timestamp) return "—";
    const value = new Date(timestamp);
    if (Number.isNaN(value.getTime())) return String(timestamp);
    return value.toLocaleTimeString([], { hour12: false });
  }

  function executionTimeline(result) {
    const trace = Array.isArray(result?.trace) ? result.trace : [];
    const explicitTools = new Set(trace.filter((event) => event?.event === "tool_started").map((event) => event?.data?.tool).filter(Boolean));
    const visible = trace.filter((event) => {
      const name = event?.event;
      if (["sdk_span_finished", "sdk_trace_started", "sdk_trace_finished"].includes(name)) return false;
      if (["sdk_tool_started", "sdk_tool_finished"].includes(name) && explicitTools.has(event?.data?.tool)) return false;
      return true;
    });
    if (!visible.length) return `<div class="run-empty">No execution events were returned by the runtime.</div>`;
    return `<ol class="run-timeline">${visible.map((event, index) => {
      const detail = traceEventDetail(event, result);
      const tone = event.event === "run_failed" || event.event === "guardrail_blocked"
        ? "error"
        : event.event === "tool_finished" && evidenceOutputForTool(result, event.data?.tool)?.status === "error"
          ? "error"
          : event.event === "run_finished" || event.event === "agent_finished" ? "done" : "";
      return `<li class="run-step ${tone}"><span class="run-step-index">${index + 1}</span><div class="run-step-body"><strong>${escapeHtml(traceEventTitle(event))}</strong>${detail ? `<span>${escapeHtml(detail)}</span>` : ""}</div></li>`;
    }).join("")}</ol>`;
  }

  function technicalTrace(result) {
    const trace = Array.isArray(result?.trace) ? result.trace : [];
    if (!trace.length) return `<div class="run-empty">No trace events were returned.</div>`;
    return `<div class="trace-log">${trace.map((event) => {
      const data = event?.data || {};
      const details = Object.entries(data)
        .filter(([key, value]) => value !== null && value !== "" && key !== "timestamp")
        .slice(0, 6)
        .map(([key, value]) => `${key}=${typeof value === "object" ? JSON.stringify(value) : String(value)}`)
        .join(" · ");
      return `<div class="trace-row"><time>${escapeHtml(formatTraceTime(event?.timestamp))}</time><code>${escapeHtml(event?.event || "event")}</code><span>${escapeHtml(details || "No event details")}</span></div>`;
    }).join("")}</div>`;
  }

  function runOutline(result) {
    const tools = [...new Set((result?.evidence?.tools || []).filter(Boolean).map(String))];
    const steps = [
      "Interpret the request and check the available session context.",
      tools.length ? `Run the selected operation${tools.length > 1 ? "s" : ""}: ${tools.map(toolLabel).join(", ")}.` : "Answer directly without a registered data operation.",
      "Check the returned status, evidence, and workspace files before composing the answer.",
    ];
    return `<ol class="run-outline">${steps.map((step) => `<li>${escapeHtml(step)}</li>`).join("")}</ol>`;
  }

  function evidenceList(title, values, renderItem = (value) => escapeHtml(value)) {
    if (!Array.isArray(values) || !values.length) return "";
    return `<section class="evidence-group"><h4>${escapeHtml(title)}</h4><ul>${values.map((value) => `<li>${renderItem(value)}</li>`).join("")}</ul></section>`;
  }

  function evidencePanel(result) {
    const evidence = result?.evidence || {};
    const citationItems = Array.isArray(evidence.citations) ? evidence.citations : [];
    const citations = citationItems.map((item) => {
      if (typeof item === "string") return escapeHtml(item);
      const title = item?.title || item?.name || item?.id || "Citation";
      const source = item?.source || item?.pmid || item?.year || "";
      const label = `${title}${source ? ` · ${source}` : ""}`;
      return item?.url ? `<a href="${escapeHtml(item.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(label)}</a>` : escapeHtml(label);
    });
    const files = (evidence.files || []).map((path) => {
      const value = String(path || "");
      return `<a href="${escapeHtml(workspaceFileUrl(value))}" title="${escapeHtml(value)}">${escapeHtml(fileNameFromPath(value))}</a>`;
    });
    const outputs = Array.isArray(evidence.outputs) ? evidence.outputs : [];
    const outputCards = outputs.map((item) => `<li><strong>${escapeHtml(toolLabel(item?.tool))}</strong><span>${escapeHtml(item?.summary || item?.status || "Result returned.")}</span></li>`).join("");
    const groups = [
      evidenceList("Tools used", evidence.tools, (value) => escapeHtml(toolLabel(value))),
      evidenceList("Databases", evidence.databases),
      evidenceList("Queries", evidence.query_terms),
      evidenceList("Records", evidence.record_ids),
      evidenceList("Files", files, (value) => value),
      evidenceList("Sources", citations, (value) => value),
      evidenceList("Links", evidence.urls, (value) => `<a href="${escapeHtml(value)}" target="_blank" rel="noopener noreferrer">${escapeHtml(value)}</a>`),
      evidenceList("Errors", evidence.tool_errors, (value) => escapeHtml(value?.error || value?.tool || value)),
    ].filter(Boolean).join("");
    return `${groups || `<div class="run-empty">No structured evidence was returned.</div>`}${outputCards ? `<section class="evidence-group evidence-outputs"><h4>Tool results</h4><ul>${outputCards}</ul></section>` : ""}`;
  }

  function runtimePanel(result, runtime, status) {
    const metrics = [
      ["Status", status.label],
      ["Model", modelLabelForKey(runtime.model_key || result.model_key)],
      ["Elapsed", formatElapsed(runtime.elapsed_seconds)],
      ["Tools", String(runtime.tool_count ?? (result.evidence?.tools || []).length)],
      ["Files", String(runtime.file_count ?? (result.evidence?.files || []).length)],
      ["Max turns", runtime.max_turns == null ? "—" : String(runtime.max_turns)],
    ];
    return `<div class="run-metrics">${metrics.map(([label, value]) => `<div class="run-metric"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`).join("")}</div>`;
  }

  function approvalPlanHtml(result) {
    const decision = result?.approval_decision;
    if (!decision || (!decision.plan && !decision.arguments)) return "";
    const reviewed = decision.plan ? { action: decision.arguments, plan: decision.plan } : decision.arguments;
    const title = decision.approved ? "Approved pipeline plan" : "Rejected operation plan";
    return `<details class="run-plan-record" open><summary>${escapeHtml(title)} <span>${escapeHtml(decision.tool_name || "Tool request")}</span></summary><pre>${escapeHtml(JSON.stringify(reviewed, null, 2))}</pre></details>`;
  }

  function resultDetails(result) {
    if (!result) return "";
    const runtime = result.runtime || {};
    const status = debugStatus(result);
    const pipelineOutputs = artifactViewers.collectPipelineOutputRecords(result);
    const hasRuntimeDetails = Boolean(result.runtime || result.trace || result.evidence || result.approval_required);
    const runtimeDetails = hasRuntimeDetails ? `
      <div class="run-debug" aria-label="Runtime details"${result.approval_decision ? ' data-default-tab="plan"' : ""}>
        <div class="run-tabs" role="tablist" aria-label="Runtime detail sections">
          <button type="button" class="run-tab" role="tab" aria-selected="false" data-runtime-tab="runtime"><span>Runtime</span><small>${escapeHtml(status.label)} · ${escapeHtml(formatElapsed(runtime.elapsed_seconds))}</small></button>
          <button type="button" class="run-tab" role="tab" aria-selected="false" data-runtime-tab="plan"><span>Plan &amp; execution</span><small>${(result.trace || []).length} events</small></button>
          <button type="button" class="run-tab" role="tab" aria-selected="false" data-runtime-tab="evidence"><span>Evidence</span><small>${(result.evidence?.citations || []).length} sources</small></button>
          <button type="button" class="run-tab" role="tab" aria-selected="false" data-runtime-tab="trace"><span>Trace</span><small>technical</small></button>
        </div>
        <section class="run-panel" role="tabpanel" data-runtime-panel="runtime" hidden>${runtimePanel(result, runtime, status)}</section>
        <section class="run-panel" role="tabpanel" data-runtime-panel="plan" hidden><p class="run-debug-note">This shows the agent’s registered operations and runtime events, without exposing private model reasoning.</p>${runOutline(result)}${executionTimeline(result)}</section>
        <section class="run-panel" role="tabpanel" data-runtime-panel="evidence" hidden><div class="evidence-panel">${evidencePanel(result)}</div></section>
        <section class="run-panel" role="tabpanel" data-runtime-panel="trace" hidden><div class="trace-technical">${technicalTrace(result)}</div></section>
        <div class="approval-controls"></div>
      </div>
    ` : "";
    return `${artifactViewers.pipelineDownloadsHtml(result, pipelineOutputs)}${pipelineOutputs.length ? "" : artifactViewers.collectedBundleHtml(result)}${pipelineOutputs.length ? "" : artifactViewers.figureArtifactsHtml(result)}${pipelineOutputs.length ? "" : artifactViewers.structureViewerHtml(result)}${approvalPlanHtml(result)}${runtimeDetails}`;
  }

  function initializeRuntimeTabs(root = document) {
    root.querySelectorAll(".run-debug").forEach((group) => {
      if (group.dataset.tabsBound === "true") return;
      group.dataset.tabsBound = "true";
      const tabs = [...group.querySelectorAll("[data-runtime-tab]")];
      const panels = [...group.querySelectorAll("[data-runtime-panel]")];
      let activeKey = null;
      const select = (key) => {
        activeKey = activeKey === key ? null : key;
        tabs.forEach((tab) => {
          const active = activeKey === tab.dataset.runtimeTab;
          tab.classList.toggle("is-active", active);
          tab.setAttribute("aria-selected", String(active));
        });
        panels.forEach((panel) => { panel.hidden = activeKey !== panel.dataset.runtimePanel; });
      };
      tabs.forEach((tab) => tab.addEventListener("click", () => select(tab.dataset.runtimeTab)));
      select(group.dataset.defaultTab || null);
    });
  }

  function renderMessageText(role, text) {
    return role === "assistant" && typeof window.renderMarkdown === "function"
      ? window.renderMarkdown(text)
      : escapeHtml(text);
  }

  function renderMessage(role, text, result = null) {
    const message = document.createElement("article");
    message.className = `message ${role}`;
    const avatar = role === "assistant" ? agentIcon : "You";
    message.innerHTML = `<div class="avatar">${avatar}</div><div class="bubble"><div class="bubble-text markdown-body">${renderMessageText(role, text)}</div>${resultDetails(result)}</div>`;
    chat.appendChild(message);
    const approvalHost = message.querySelector(".approval-controls");
    if (approvalHost && window.mountToolApprovals) {
      window.mountToolApprovals(approvalHost, result, {
        url: "/approve",
        streamUrl: "/approve_stream",
        isBusy: () => getRunning() || getSessionLoading(),
        onBusy: onApprovalBusy,
        onResult: onApprovalResult,
      });
    }
    initializeRuntimeTabs(message);
    artifactViewers.initializeStructureViewers(message);
  }

  return { renderMessage, resultDetails, initializeRuntimeTabs };
}
