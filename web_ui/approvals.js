/* Shared approval controls for the full and embedded chat interfaces. */

async function readApprovalResponse(response, onProgress) {
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.error || `HTTP ${response.status}`);
  }
  if (!response.body) {
    throw new Error("Approval response streaming is not available in this browser.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let result = null;
  const handleFrame = (frame) => {
    if (!frame.trim()) return;
    let event = "message";
    const dataLines = [];
    for (const line of frame.split(/\r?\n/)) {
      if (line.startsWith("event:")) event = line.slice("event:".length).trim();
      if (line.startsWith("data:")) dataLines.push(line.slice("data:".length).trimStart());
    }
    if (!dataLines.length) return;
    const payload = JSON.parse(dataLines.join("\n"));
    if (event === "status" || event === "log") {
      onProgress?.(payload.message || "Resuming the run…");
    } else if (event === "result") {
      result = payload;
    } else if (event === "error") {
      throw new Error(payload.error || "Approval request failed.");
    }
  };

  try {
    while (true) {
      const { value, done } = await reader.read();
      buffer += done ? decoder.decode() : decoder.decode(value, { stream: true });
      const frames = buffer.split(/\r?\n\r?\n/);
      buffer = frames.pop() || "";
      frames.forEach(handleFrame);
      if (done) break;
    }
    if (buffer.trim()) handleFrame(buffer);
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
  if (!result) throw new Error("Approval stream ended before returning a result.");
  return result;
}

function approvalResultError(result) {
  if (!result || typeof result !== "object") return "Approval request failed.";
  if (result.error) return String(result.error);
  if (result.status === "error" || result.runtime?.status === "error") {
    return String(result.answer || "Approval request failed.");
  }
  return "";
}

window.mountToolApprovals = function (container, result, options) {
  if (!result?.approval_required || !Array.isArray(result.approvals)) return;
  const panel = document.createElement("div");
  panel.className = "tool-approvals";
  for (const item of result.approvals) {
    const row = document.createElement("section");
    row.className = "approval-item";
    const title = document.createElement("strong");
    title.textContent = `Review ${item.tool_name}`;

    // Keep the requested plan in its own persistent details block. The
    // decision status below can change after approval without replacing the
    // plan the user reviewed.
    const plan = document.createElement("details");
    plan.className = "approval-plan";
    plan.open = true;
    const planSummary = document.createElement("summary");
    planSummary.textContent = item.plan ? "Pipeline plan" : "Requested operation";
    const planBody = document.createElement("pre");
    planBody.textContent = JSON.stringify(item.plan ? { action: item.arguments, plan: item.plan } : item.arguments, null, 2);
    plan.append(planSummary, planBody);

    const actions = document.createElement("div");
    actions.className = "approval-actions";
    const status = document.createElement("p");
    status.className = "approval-status";
    status.setAttribute("role", "status");
    status.hidden = true;
    row.append(title, plan, actions, status);

    for (const approved of [true, false]) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = approved ? "Approve" : "Reject";
      button.addEventListener("click", async () => {
        if (options.isBusy()) return;
        const buttons = panel.querySelectorAll("button");
        buttons.forEach((control) => { control.disabled = true; });
        options.onBusy(true);
        status.hidden = false;
        status.dataset.status = "running";
        status.textContent = approved
          ? "Approval submitted. Execution is in progress…"
          : "Rejection submitted. Finishing the request…";
        try {
          const response = await fetch(options.streamUrl || options.url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              session_id: result.session_id,
              approval_id: item.approval_id,
              approved,
            }),
          });
          const next = options.streamUrl
            ? await readApprovalResponse(response, (message) => {
              status.hidden = false;
              status.dataset.status = "running";
              status.textContent = message;
            })
            : await response.json();
          const resultError = approvalResultError(next);
          if (!response.ok || resultError) {
            throw new Error(resultError || `HTTP ${response.status}`);
          }
          status.dataset.status = approved ? "done" : "rejected";
          status.textContent = approved
            ? (next.approval_required
              ? "Approved. Reviewing the remaining requested operation…"
              : "Approved. Execution details are shown in the next run panel.")
            : (next.approval_required
              ? "Rejected. Reviewing the remaining requested operation…"
              : "Rejected. No pipeline execution was started.");
          plan.open = false;
          const decision = {
            approved,
            approval_id: item.approval_id,
            tool_name: item.tool_name,
            arguments: item.arguments || null,
            plan: item.plan || null,
          };

          // The server may pause again when the original run contained more
          // than one approval-controlled call. Replace this panel with the
          // server's remaining approvals so stale buttons cannot be clicked
          // and the user sees exactly one current approval state.
          if (next.approval_required && Array.isArray(next.approvals) && next.approvals.length) {
            options.onResult?.(next, { approved, item, intermediate: true });
            container.replaceChildren();
            window.mountToolApprovals(container, next, options);
            return;
          }

          options.onResult({
            ...next,
            approval_decision: decision,
          }, { approved, item });
        } catch (error) {
          status.dataset.status = "error";
          status.textContent = error.message;
          buttons.forEach((control) => { control.disabled = false; });
        } finally {
          options.onBusy(false);
        }
      });
      row.appendChild(button);
    }
    panel.appendChild(row);
  }
  container.appendChild(panel);
};
