(() => {
  "use strict";

  const byId = (id) => document.getElementById(id);
  const messages = byId("messages");
  const prompt = byId("prompt");
  const model = byId("model");
  const status = byId("status");
  const welcome = messages.firstElementChild.cloneNode(true);
  const contextLabels = { project_id: "Project", sample_id: "Sample", result_type: "Results" };
  const query = new URLSearchParams(window.location.search);
  const parentOrigin = getParentOrigin();
  document.documentElement.classList.toggle("embedded-mode", query.get("embedded") === "1");
  const state = {
    sessionId: createSessionId(),
    ready: false,
    busy: false,
    abort: null,
    uploads: [],
    logs: [],
    context: {},
    maxTurns: 5,
  };

  function getParentOrigin() {
    try {
      const url = new URL(query.get("parent_origin") || window.location.origin);
      return ["http:", "https:"].includes(url.protocol) ? url.origin : window.location.origin;
    } catch (_) {
      return window.location.origin;
    }
  }

  function createSessionId() {
    // randomUUID is unavailable on plain HTTP LAN addresses.
    const bytes = new Uint8Array(16);
    window.crypto.getRandomValues(bytes);
    return `assistant_${Array.from(bytes, (value) => value.toString(16).padStart(2, "0")).join("")}`;
  }

  function apiUrl(path) {
    // Resolve under the current mount point, including a reverse-proxy prefix.
    return new URL(path, window.location.href).href;
  }

  function setContext(context) {
    if (!context || typeof context !== "object" || Array.isArray(context)) return;
    // Replace context as a whole so a new project cannot keep an old sample ID.
    state.context = {};
    const summary = byId("contextSummary");
    summary.replaceChildren();
    for (const [key, label] of Object.entries(contextLabels)) {
      const value = typeof context[key] === "string" ? context[key].trim().slice(0, 200) : "";
      if (!value) continue;
      state.context[key] = value;
      const chip = document.createElement("span");
      chip.className = "context-chip";
      chip.textContent = `${label}: ${value}`;
      chip.title = chip.textContent;
      summary.appendChild(chip);
    }
    summary.hidden = !summary.children.length;
  }

  function setBusy(busy) {
    state.busy = busy;
    byId("send").disabled = busy || !state.ready;
    byId("stop").disabled = !state.abort;
    byId("stop").hidden = !state.abort;
    byId("newChat").disabled = busy;
    byId("attachButton").disabled = busy;
    model.disabled = busy || !state.ready;
  }

  function addMessage(role, text, result = null) {
    messages.querySelector(".welcome")?.remove();
    const message = document.createElement("article");
    message.className = `message ${role}`;
    const label = document.createElement("span");
    label.className = "message-label";
    label.textContent = role === "user" ? "You" : role === "error" ? "Request failed" : "BioAgent";
    const body = document.createElement("div");
    body.className = "message-body";
    if (role === "assistant" && window.renderMarkdown) {
      body.innerHTML = window.renderMarkdown(String(text));
    } else {
      body.textContent = text;
    }
    const resultFiles = Array.isArray(result?.files) ? result.files : [];
    const paths = [...new Map(resultFiles
      .map((item) => [item?.workspace_path || item?.path, item])
      .filter(([path]) => typeof path === "string" && path)).entries()];
    if (paths.length) {
      const files = document.createElement("div");
      files.className = "message-files";
      for (const [path] of paths) {
        const link = document.createElement("a");
        link.href = apiUrl(`workspace/file?path=${encodeURIComponent(path)}&session_id=${encodeURIComponent(state.sessionId)}`);
        link.textContent = path.split("/").pop();
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        files.appendChild(link);
      }
      body.appendChild(files);
    }
    message.append(label, body);
    if (result?.approval_required && window.mountToolApprovals) {
      const approvals = document.createElement("div");
      approvals.className = "approval-controls";
      message.appendChild(approvals);
      window.mountToolApprovals(approvals, result, {
        url: apiUrl("approve"),
        isBusy: () => state.busy,
        onBusy: (busy) => { if (!busy) setBusy(false); else setBusy(true); },
        onResult: (next) => addMessage("assistant", next.answer || "", next),
      });
    }
    messages.appendChild(message);
    messages.scrollTop = messages.scrollHeight;
  }

  function requestText(text) {
    if (!Object.keys(state.context).length) return text;
    return `${text}\n\nWebsite context (user-supplied labels, not retrieved results):\n${JSON.stringify(state.context, null, 2)}`;
  }

  async function loadConfig() {
    state.ready = false;
    setBusy(false);
    byId("retryConfig").hidden = true;
    status.textContent = "Connecting to BioAgent…";
    try {
      const response = await fetch(apiUrl("config"));
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const config = await response.json();
      if (!Array.isArray(config.models) || !config.models.length) throw new Error("No models configured");
      model.replaceChildren();
      for (const item of config.models) {
        const option = document.createElement("option");
        option.value = item.key;
        option.textContent = `${item.label || item.key} (${item.cost_tier || "Unknown cost"})`;
        option.selected = item.key === config.default_model_key;
        model.appendChild(option);
      }
      state.maxTurns = Math.min(20, Math.max(1, Math.floor(Number(config.default_max_turns) || 5)));
      state.ready = true;
      status.textContent = "Ready";
    } catch (error) {
      status.textContent = `Could not connect: ${error.message}`;
      byId("retryConfig").hidden = false;
    }
    setBusy(false);
  }

  function appendProgress(message) {
    state.logs.push(String(message));
    state.logs = state.logs.slice(-30);
    byId("progressLog").textContent = state.logs.join("\n");
    byId("progressDetails").hidden = false;
  }

  function handleFrame(frame) {
    let event = "message";
    const data = [];
    for (const line of frame.split("\n")) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
    }
    if (!data.length) return null;
    const payload = JSON.parse(data.join("\n"));
    if (event === "log" || event === "status") appendProgress(payload.message || "Working…");
    if (event === "result") return payload;
    if (event === "error") throw new Error(payload.error || "Agent request failed");
    return null;
  }

  async function run(request, steps, signal) {
    const response = await fetch(apiUrl("run_stream"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        request,
        session_id: state.sessionId,
        model_key: model.value,
        max_turns: steps,
      }),
      signal,
    });
    if (!response.ok) throw new Error(`Service returned HTTP ${response.status}`);
    if (!response.body) throw new Error("This browser does not support streaming responses");
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    try {
      while (true) {
        const { value, done } = await reader.read();
        buffer += done ? decoder.decode() : decoder.decode(value, { stream: true });
        let boundary;
        while ((boundary = /\r?\n\r?\n/.exec(buffer))) {
          const frame = buffer.slice(0, boundary.index).replace(/\r\n/g, "\n");
          buffer = buffer.slice(boundary.index + boundary[0].length);
          const result = handleFrame(frame);
          if (result) return result;
        }
        if (done) break;
      }
      if (buffer.trim()) {
        const result = handleFrame(buffer.replace(/\r\n/g, "\n"));
        if (result) return result;
      }
      throw new Error("Connection closed before an answer arrived. Check Activity before retrying.");
    } finally {
      await reader.cancel().catch(() => {});
      reader.releaseLock();
    }
  }

  async function submitPrompt(event) {
    event.preventDefault();
    const text = prompt.value.trim();
    if (!text || state.busy || !state.ready) return;
    const steps = state.maxTurns;
    const request = requestText(text);
    prompt.value = "";
    addMessage("user", text);
    state.logs = [];
    byId("progressLog").textContent = "";
    byId("progressDetails").hidden = true;
    byId("progressDetails").open = false;
    state.abort = new AbortController();
    setBusy(true);
    status.textContent = "Working on your request…";
    try {
      const result = await run(request, steps, state.abort.signal);
      state.sessionId = result.session_id || state.sessionId;
      addMessage("assistant", result.answer || "No answer returned.", result);
      status.textContent = "Ready";
    } catch (error) {
      if (error.name === "AbortError") {
        status.textContent = "Stopped waiting. Work already started on the server may continue.";
      } else {
        addMessage("error", error.message);
        status.textContent = "Request failed. You can edit your message and try again.";
      }
      if (!prompt.value) prompt.value = text;
    } finally {
      state.abort = null;
      setBusy(false);
      prompt.focus();
    }
  }

  function renderUploads() {
    const list = byId("uploadList");
    list.replaceChildren();
    list.hidden = !state.uploads.length;
    for (const file of state.uploads) {
      const item = document.createElement("li");
      const button = document.createElement("button");
      const name = file.name || file.filename || String(file.path || "File").split("/").pop();
      button.type = "button";
      button.textContent = name;
      button.title = `Ask about ${name}`;
      button.addEventListener("click", () => {
        const reference = `Analyze the attached file ${JSON.stringify(name)}.`;
        prompt.value = prompt.value ? `${prompt.value}\n${reference}` : reference;
        prompt.focus();
      });
      item.appendChild(button);
      list.appendChild(item);
    }
  }

  async function uploadFiles() {
    const input = byId("uploadInput");
    if (state.busy || !input.files.length) return;
    const data = new FormData();
    data.append("session_id", state.sessionId);
    Array.from(input.files).forEach((file) => data.append("files", file));
    setBusy(true);
    status.textContent = "Uploading files…";
    try {
      const response = await fetch(apiUrl("workspace/files"), { method: "POST", body: data });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || `HTTP ${response.status}`);
      state.sessionId = result.session_id || state.sessionId;
      state.uploads.push(...(result.files || []));
      renderUploads();
      status.textContent = "Files attached. Select a file to ask about it.";
    } catch (error) {
      status.textContent = `Upload failed: ${error.message}`;
    } finally {
      input.value = "";
      setBusy(false);
    }
  }

  function newChat() {
    if (state.busy) return;
    state.sessionId = createSessionId();
    state.uploads = [];
    state.logs = [];
    messages.replaceChildren(welcome.cloneNode(true));
    prompt.value = "";
    byId("progressDetails").hidden = true;
    byId("progressLog").textContent = "";
    renderUploads();
    status.textContent = state.ready ? "Ready" : "Connect to BioAgent before sending.";
    prompt.focus();
  }

  setContext(Object.fromEntries(Object.keys(contextLabels).map((key) => [key, query.get(key)])));

  // Accept context only from the immediate embedding window at its named origin.
  window.addEventListener("message", (event) => {
    if (window.parent === window || event.source !== window.parent || event.origin !== parentOrigin) return;
    if (!event.data || event.data.type !== "bioagent-context" || !event.data.context) return;
    setContext(event.data.context);
  });
  if (window.parent !== window) window.parent.postMessage({ type: "bioagent-ready" }, parentOrigin);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && window.parent !== window) {
      window.parent.postMessage({ type: "bioagent-close" }, parentOrigin);
    }
  });
  byId("composer").addEventListener("submit", submitPrompt);
  prompt.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      byId("composer").requestSubmit();
    }
  });
  messages.addEventListener("click", (event) => {
    if (event.target.closest("#welcomePrompt")) {
      prompt.value = "Help me understand a results table.";
      prompt.focus();
    }
  });
  byId("stop").addEventListener("click", () => state.abort?.abort());
  byId("newChat").addEventListener("click", newChat);
  byId("attachButton").addEventListener("click", () => byId("uploadInput").click());
  byId("uploadInput").addEventListener("change", uploadFiles);
  byId("retryConfig").addEventListener("click", loadConfig);
  loadConfig();
})();
