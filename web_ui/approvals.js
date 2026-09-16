/* Shared approval controls for the full and embedded chat interfaces. */
window.mountToolApprovals = function (container, result, options) {
  if (!result?.approval_required || !Array.isArray(result.approvals)) return;
  const panel = document.createElement("div");
  panel.className = "tool-approvals";
  for (const item of result.approvals) {
    const row = document.createElement("section");
    const title = document.createElement("strong");
    title.textContent = `Review ${item.tool_name}`;
    const args = document.createElement("pre");
    args.textContent = JSON.stringify(item.plan ? { action: item.arguments, plan: item.plan } : item.arguments, null, 2);
    row.append(title, args);
    for (const approved of [true, false]) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = approved ? "Approve" : "Reject";
      button.addEventListener("click", async () => {
        if (options.isBusy()) return;
        const buttons = panel.querySelectorAll("button");
        buttons.forEach((control) => { control.disabled = true; });
        options.onBusy(true);
        const progress = document.createElement("p");
        progress.textContent = "Submitting decision…";
        row.appendChild(progress);
        try {
          const response = await fetch(options.url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              session_id: result.session_id,
              approval_id: item.approval_id,
              approved,
            }),
          });
          const next = await response.json();
          if (!response.ok || next.error) throw new Error(next.error || `HTTP ${response.status}`);
          panel.textContent = approved ? "Approval submitted." : "Rejection submitted.";
          options.onResult(next);
        } catch (error) {
          progress.textContent = error.message;
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
