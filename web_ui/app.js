let config = {
  default_model_key: "",
  default_max_skill_steps: 5,
  models: [],
};

const modelSelect = document.getElementById("model");
const maxStepsInput = document.getElementById("maxSteps");
const chat = document.getElementById("chat");
const chatScroll = document.getElementById("chatScroll");
const promptInput = document.getElementById("prompt");
const sendButton = document.getElementById("send");
const stopButton = document.getElementById("stop");
const statusPill = document.getElementById("status");
const thinkingBar = document.getElementById("thinkingBar");
const thinkingMeta = document.getElementById("thinkingMeta");
const thinkingDetails = document.getElementById("thinkingDetails");
const thinkingLogs = document.getElementById("thinkingLogs");
const composer = document.getElementById("composer");
const newChatButton = document.getElementById("newChat");
const sessionList = document.getElementById("sessionList");
const sessionCount = document.getElementById("sessionCount");
const activeModel = document.getElementById("activeModel");
const activeSession = document.getElementById("activeSession");
const uploadButton = document.getElementById("uploadButton");
const uploadInput = document.getElementById("uploadInput");
const uploadList = document.getElementById("uploadList");
const uploadCount = document.getElementById("uploadCount");
const uploadInputLabel = document.getElementById("uploadInputLabel");

const LEGACY_CHAT_STORAGE_KEY = "bioagent.web.chat.v1";
const SESSION_STORAGE_KEY = "bioagent.web.sessions.v1";
const ACTIVE_SESSION_KEY = "bioagent.web.active_session_id.v1";
const MAX_STORED_MESSAGES = 80;
const MAX_SESSIONS = 50;
const DEFAULT_UPLOAD_INPUT_LABEL = "input_path";
let structureSuffixes = [".cif", ".mmcif", ".pdb"];
let imageSuffixes = [".svg"];

let runtimeTimer = null;
let runtimeStartedAt = 0;
let activeAbortController = null;
let requestStopped = false;
let isRunning = false;
let thinkingLogLines = [];
let sessions = [];
let activeSessionId = "";
let uploads = [];
let lastAutoUploadInputLabel = DEFAULT_UPLOAD_INPUT_LABEL;

async function loadConfig() {
  const response = await fetch("/config");
  if (!response.ok) {
    throw new Error(`Failed to load /config: HTTP ${response.status}`);
  }
  config = await response.json();
  applyArtifactConfig(config.artifacts || {});
  renderModelOptions();
}

function applyArtifactConfig(artifactConfig) {
  structureSuffixes = normalizeSuffixes(artifactConfig.structure_suffixes, structureSuffixes);
  imageSuffixes = normalizeSuffixes(artifactConfig.image_suffixes, imageSuffixes);
}

function normalizeSuffixes(value, fallback) {
  if (!Array.isArray(value) || !value.length) return fallback;
  return value
    .map((suffix) => String(suffix || "").trim().toLowerCase())
    .filter((suffix) => suffix.startsWith("."));
}

function renderModelOptions() {
  modelSelect.innerHTML = "";
  for (const model of config.models || []) {
    const option = document.createElement("option");
    option.value = model.key;
    option.textContent = `${model.label} (${model.key})`;
    if (model.key === config.default_model_key) {
      option.selected = true;
    }
    modelSelect.appendChild(option);
  }
  maxStepsInput.value = config.default_max_skill_steps || 5;
  updateActiveModel();
}

function updateActiveModel() {
  const selected = (config.models || []).find((model) => model.key === modelSelect.value);
  activeModel.textContent = selected ? selected.label : "Model ready";
}

function generateSessionId() {
  if (window.crypto && typeof window.crypto.randomUUID === "function") {
    return `chat_${window.crypto.randomUUID()}`;
  }
  return `chat_${Date.now()}_${Math.random().toString(16).slice(2)}`;
}

function nowIso() {
  return new Date().toISOString();
}

function titleFromText(text) {
  const title = String(text || "").replace(/\s+/g, " ").trim();
  return title ? title.slice(0, 64) : "New chat";
}

function formatSessionTime(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatSessionMeta(session) {
  const time = formatSessionTime(session.updated_at) || "No activity";
  const count = Array.isArray(session.messages) ? session.messages.length : 0;
  const messageText = count === 1 ? "1 message" : `${count} messages`;
  return `${time} · ${messageText}`;
}

function formatBytes(value) {
  const bytes = Number(value || 0);
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}

function createSession(title = "New chat") {
  const timestamp = nowIso();
  return {
    id: generateSessionId(),
    title,
    messages: [],
    created_at: timestamp,
    updated_at: timestamp,
  };
}

function normalizeSession(raw) {
  if (!raw || !raw.id) return null;
  return {
    id: String(raw.id),
    title: String(raw.title || "New chat"),
    messages: Array.isArray(raw.messages) ? raw.messages.slice(-MAX_STORED_MESSAGES) : [],
    created_at: raw.created_at || nowIso(),
    updated_at: raw.updated_at || raw.created_at || nowIso(),
  };
}

function migrateLegacyChat() {
  const raw = localStorage.getItem(LEGACY_CHAT_STORAGE_KEY);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw);
    const messages = Array.isArray(parsed?.messages) ? parsed.messages : [];
    if (!messages.length) return null;
    const session = createSession("Previous chat");
    session.messages = messages
      .filter((message) => message && ["assistant", "user"].includes(message.role))
      .slice(-MAX_STORED_MESSAGES);
    const firstUser = session.messages.find((message) => message.role === "user");
    session.title = firstUser ? titleFromText(firstUser.text) : "Previous chat";
    return session;
  } catch (error) {
    console.warn("Failed to migrate old chat history.", error);
    return null;
  } finally {
    localStorage.removeItem(LEGACY_CHAT_STORAGE_KEY);
  }
}

function loadSessions() {
  try {
    const raw = localStorage.getItem(SESSION_STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : {};
    sessions = (Array.isArray(parsed?.sessions) ? parsed.sessions : [])
      .map(normalizeSession)
      .filter(Boolean);
  } catch (error) {
    console.warn("Failed to load sessions.", error);
    sessions = [];
    localStorage.removeItem(SESSION_STORAGE_KEY);
  }

  if (!sessions.length) {
    const migrated = migrateLegacyChat();
    sessions = migrated ? [migrated] : [createSession()];
  }

  activeSessionId = localStorage.getItem(ACTIVE_SESSION_KEY) || sessions[0].id;
  if (!sessions.some((session) => session.id === activeSessionId)) {
    activeSessionId = sessions[0].id;
  }
  saveSessions();
}

function saveSessions() {
  sessions = sessions
    .map(normalizeSession)
    .filter(Boolean)
    .sort((left, right) => String(right.updated_at).localeCompare(String(left.updated_at)))
    .slice(0, MAX_SESSIONS);
  localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify({ sessions }));
  localStorage.setItem(ACTIVE_SESSION_KEY, activeSessionId);
}

function currentSession() {
  let session = sessions.find((item) => item.id === activeSessionId);
  if (!session) {
    session = createSession();
    sessions.unshift(session);
    activeSessionId = session.id;
    saveSessions();
  }
  return session;
}

function updateCurrentSession(updater) {
  const session = currentSession();
  updater(session);
  session.messages = session.messages.slice(-MAX_STORED_MESSAGES);
  session.updated_at = nowIso();
  saveSessions();
  renderSessionList();
  updateActiveSession();
}

function emptyStateHtml() {
  return `
    <div class="empty-state">
      <div>
        <h1>Ask BioAgent</h1>
      </div>
      <div class="empty-grid">
        <button class="example-button" data-example="Download 10 NCBI records for PhiX174 genes A G">NCBI retrieval</button>
        <button class="example-button" data-example="Analyze the structure of 3GOU">Analyze PDB 3GOU</button>
        <button class="example-button" data-example="Compare PhiX174 and M13 genome structure, host range, and applications.">Compare biology</button>
        <button class="example-button" data-example="Inspect file runtime/downloads/ncbi_phix174/phix174_A.fasta">Inspect file</button>
        <button class="example-button" data-example="Please test skill calling by running the example skill with message hello and tag smoke.">Test skill calling</button>
      </div>
    </div>
  `;
}

function renderCurrentChat() {
  chat.innerHTML = "";
  const messages = currentSession().messages || [];
  if (!messages.length) {
    chat.innerHTML = emptyStateHtml();
    bindExampleButtons(chat);
    renderUploadInsertOptions();
    return;
  }
  for (const message of messages) {
    renderMessage(message.role, message.text || "", message.result || null);
  }
  renderUploadInsertOptions();
  scrollBottom();
}

function renderSessionList() {
  sessionCount.textContent = String(sessions.length);
  sessionList.innerHTML = "";
  if (!sessions.length) {
    sessionList.innerHTML = `<div class="session-empty">No saved chats.</div>`;
    return;
  }
  for (const session of sessions) {
    const item = document.createElement("div");
    item.className = `session-item ${session.id === activeSessionId ? "active" : ""}`;
    item.dataset.sessionId = session.id;
    item.innerHTML = `
      <button class="session-select" type="button">
        <span class="session-title">${escapeHtml(session.title || "New chat")}</span>
        <span class="session-meta">${escapeHtml(formatSessionMeta(session))}</span>
      </button>
      <button class="session-delete" type="button" aria-label="Delete ${escapeHtml(session.title || "session")}" title="Delete session">&times;</button>
    `;
    sessionList.appendChild(item);
  }
}

function updateActiveSession() {
  activeSession.textContent = currentSession().title || "New chat";
}

function switchSession(sessionId) {
  if (isRunning || !sessionId || sessionId === activeSessionId) return;
  activeSessionId = sessionId;
  saveSessions();
  renderSessionList();
  renderCurrentChat();
  updateActiveSession();
  loadUploads().catch((error) => console.warn("Failed to load uploads.", error));
  resetThinkingBar();
  promptInput.focus();
}

async function deleteSessionById(sessionId) {
  if (isRunning || !sessionId) return;
  sessions = sessions.filter((session) => session.id !== sessionId);
  try {
    await fetch(`/sessions/${encodeURIComponent(sessionId)}`, { method: "DELETE" });
  } catch (error) {
    console.warn("Failed to delete server session.", error);
  }
  if (!sessions.length) {
    sessions = [createSession()];
  }
  if (activeSessionId === sessionId) {
    activeSessionId = sessions[0].id;
  }
  saveSessions();
  renderSessionList();
  renderCurrentChat();
  updateActiveSession();
  loadUploads().catch((error) => console.warn("Failed to load uploads.", error));
  resetThinkingBar();
}

function startNewChat() {
  if (isRunning) return;
  const session = createSession();
  sessions.unshift(session);
  activeSessionId = session.id;
  saveSessions();
  renderSessionList();
  renderCurrentChat();
  updateActiveSession();
  loadUploads().catch((error) => console.warn("Failed to load uploads.", error));
  resetThinkingBar();
  promptInput.focus();
}

function renderUploadList() {
  uploadCount.textContent = String(uploads.length);
  uploadList.innerHTML = "";
  if (!uploads.length) {
    uploadList.innerHTML = `<div class="upload-empty">No files uploaded for this chat.</div>`;
    return;
  }
  for (const upload of uploads) {
    const item = document.createElement("div");
    item.className = "upload-item";
    item.dataset.artifactId = upload.id || "";
    item.dataset.path = upload.path || "";
    const name = upload.filename || upload.label || fileNameFromPath(upload.path);
    item.innerHTML = `
      <div class="upload-main">
        <div class="upload-name" title="${escapeHtml(name)}">${escapeHtml(name)}</div>
        <div class="upload-meta">${escapeHtml(formatBytes(upload.size))}</div>
      </div>
      <div class="upload-actions">
        <button class="upload-use" type="button" data-upload-use>Use</button>
        <a class="upload-open" href="${escapeHtml(artifactUrl(upload.path))}" target="_blank" rel="noopener noreferrer">Open</a>
        <button class="upload-delete" type="button" data-upload-delete title="Delete upload">&times;</button>
      </div>
    `;
    uploadList.appendChild(item);
  }
}

async function loadUploads() {
  if (!activeSessionId) {
    uploads = [];
    renderUploadList();
    return;
  }
  const response = await fetch(`/uploads?session_id=${encodeURIComponent(activeSessionId)}`);
  if (!response.ok) {
    throw new Error(`Upload list failed: HTTP ${response.status}`);
  }
  const payload = await response.json();
  uploads = Array.isArray(payload.uploads) ? payload.uploads : [];
  renderUploadList();
}

async function uploadSelectedFiles(files) {
  const selected = Array.from(files || []);
  if (!selected.length || isRunning) return;
  const formData = new FormData();
  formData.append("session_id", activeSessionId);
  for (const file of selected) {
    formData.append("files", file, file.name);
  }

  uploadButton.disabled = true;
  uploadButton.textContent = "Uploading";
  try {
    const response = await fetch("/upload", {
      method: "POST",
      body: formData,
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || `Upload failed: HTTP ${response.status}`);
    }
    if (payload.session_id && payload.session_id !== activeSessionId) {
      const session = currentSession();
      session.id = payload.session_id;
      activeSessionId = payload.session_id;
      saveSessions();
      renderSessionList();
      updateActiveSession();
    }
    uploads = Array.isArray(payload.uploads) ? payload.uploads : [];
    await loadUploads();
  } catch (error) {
    addMessage("assistant", `Upload failed: ${error.message}`);
  } finally {
    uploadInput.value = "";
    uploadButton.disabled = false;
    uploadButton.textContent = "Upload";
  }
}

function insertTextAtCursor(value) {
  const text = String(value || "");
  const start = promptInput.selectionStart ?? promptInput.value.length;
  const end = promptInput.selectionEnd ?? promptInput.value.length;
  const before = promptInput.value.slice(0, start);
  const after = promptInput.value.slice(end);
  const needsSpaceBefore = before && !/\s$/.test(before);
  const needsSpaceAfter = after && !/^\s/.test(after);
  promptInput.value = `${before}${needsSpaceBefore ? " " : ""}${text}${needsSpaceAfter ? " " : ""}${after}`;
  const cursor = before.length + (needsSpaceBefore ? 1 : 0) + text.length;
  promptInput.focus();
  promptInput.setSelectionRange(cursor, cursor);
}

function latestPipelineInputRequest() {
  const messages = currentSession().messages || [];
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (message.role !== "assistant") continue;
    const structured = pipelineInputRequestFromResult(message.result);
    if (structured) {
      return structured;
    }
    const text = String(message.text || "");
    const match = text.match(/Pipeline\s+`([^`]+)`\s+needs input file information/i);
    if (match) {
      return {
        pipelineName: match[1],
        text,
        requestedInputs: [],
      };
    }
    return null;
  }
  return null;
}

function pipelineInputRequestFromResult(result) {
  const outputs = result?.evidence?.outputs;
  if (!Array.isArray(outputs)) return null;
  for (let index = outputs.length - 1; index >= 0; index -= 1) {
    const output = outputs[index];
    if (!output || output.skill !== "pipeline_runner" || !output.needs_input) continue;
    const requestedInputs = Array.isArray(output.requested_inputs)
      ? output.requested_inputs.filter((item) => item && item.slot)
      : [];
    return {
      pipelineName: String(output.pipeline_name || ""),
      text: "",
      requestedInputs,
    };
  }
  return null;
}

function pipelineInputSlotsFromText(text) {
  const slots = [];
  const seen = new Set();
  const pattern = /^-\s+.+?\(`([^`]+)`(?:,\s*(?:config|key)\s+`([^`]+)`)?\):/gim;
  let match;
  while ((match = pattern.exec(String(text || ""))) !== null) {
    const clean = String(match[1] || "").trim();
    if (!clean || seen.has(clean)) continue;
    seen.add(clean);
    slots.push(clean);
  }
  return slots;
}

function pipelineInputSlotsFromRequest(request) {
  if (!request) return [];
  if (Array.isArray(request.requestedInputs) && request.requestedInputs.length) {
    return request.requestedInputs
      .map((item) => String(item.slot || "").trim())
      .filter(Boolean);
  }
  return pipelineInputSlotsFromText(request.text);
}

function renderUploadInsertOptions() {
  if (!uploadInputLabel) return;
  const selected = uploadInputLabel.value.trim();
  const pending = latestPipelineInputRequest();
  const requestedSlots = pipelineInputSlotsFromRequest(pending);
  const options = requestedSlots.length ? requestedSlots : [DEFAULT_UPLOAD_INPUT_LABEL];
  const seen = new Set();
  const uniqueOptions = options.filter((option) => {
    if (seen.has(option)) return false;
    seen.add(option);
    return true;
  });

  uploadInputLabel.innerHTML = [
    ...uniqueOptions.map((option) => `<option value="${escapeHtml(option)}">${escapeHtml(option)}</option>`),
    '<option value="">raw path</option>',
  ].join("");

  if (
    requestedSlots.length &&
    (!selected || selected === DEFAULT_UPLOAD_INPUT_LABEL || selected === lastAutoUploadInputLabel)
  ) {
    uploadInputLabel.value = requestedSlots[0];
    lastAutoUploadInputLabel = requestedSlots[0];
  } else if (!selected && !requestedSlots.length) {
    uploadInputLabel.value = DEFAULT_UPLOAD_INPUT_LABEL;
    lastAutoUploadInputLabel = DEFAULT_UPLOAD_INPUT_LABEL;
  } else if (uniqueOptions.includes(selected)) {
    uploadInputLabel.value = selected;
  } else {
    uploadInputLabel.value = uniqueOptions[0] || "";
  }
}

function requestPrefixForPendingPipeline() {
  const pending = latestPipelineInputRequest();
  return pending?.pipelineName ? `Run pipeline with pipeline_name: ${pending.pipelineName}` : "";
}

function uploadPathSnippet(path) {
  const cleanPath = String(path || "").trim();
  if (!cleanPath) return "";
  const label = uploadInputLabel?.value.trim() || "";
  if (!label) {
    return `"${cleanPath}"`;
  }
  return `${label}: "${cleanPath}"`;
}

function useUploadPath(path) {
  const snippet = uploadPathSnippet(path);
  if (!snippet) return;
  if (!promptInput.value.trim()) {
    const prefix = requestPrefixForPendingPipeline();
    if (prefix) {
      promptInput.value = `${prefix} ${snippet}`;
      promptInput.focus();
      promptInput.setSelectionRange(promptInput.value.length, promptInput.value.length);
      return;
    }
  }
  insertTextAtCursor(snippet);
}

async function deleteUploadById(artifactId) {
  if (!artifactId || isRunning) return;
  const response = await fetch(
    `/uploads/${encodeURIComponent(artifactId)}?session_id=${encodeURIComponent(activeSessionId)}`,
    { method: "DELETE" },
  );
  const payload = await response.json();
  if (!response.ok || !payload.deleted) {
    throw new Error(payload.error || "Upload was not deleted.");
  }
  await loadUploads();
}

function formatElapsed(seconds) {
  const value = Number(seconds || 0);
  if (value < 60) return `${value.toFixed(value < 10 ? 1 : 0)}s`;
  const minutes = Math.floor(value / 60);
  const remainder = Math.round(value % 60);
  return `${minutes}m ${remainder}s`;
}

function compactList(values, emptyText = "none", limit = 3) {
  const items = (values || []).filter(Boolean).map(String);
  if (!items.length) return emptyText;
  const shown = items.slice(0, limit).join(", ");
  return items.length > limit ? `${shown} +${items.length - limit}` : shown;
}

function appendThinkingLog(message) {
  thinkingLogLines.push(String(message || ""));
  thinkingLogs.textContent = thinkingLogLines.length
    ? thinkingLogLines.join("\n")
    : "No thinking log yet.";
}

function renderThinkingPanel(payload = {}) {
  const runtime = payload.runtime || payload;
  const logs = runtime.logs || thinkingLogLines;
  thinkingLogs.textContent = logs.length ? logs.join("\n") : "No thinking log yet.";
}

function runtimeMeta(runtime = {}) {
  return [
    `Elapsed: ${formatElapsed(runtime.elapsed_seconds)}`,
    `Skills: ${compactList(runtime.skills)}`,
    `Tools: ${compactList(runtime.tools)}`,
    `Files: ${runtime.file_count || 0}`,
  ];
}

function setThinkingDisplay(state, metaItems = [], payload = null) {
  thinkingBar.className = `thinking-bar ${state}`;
  statusPill.className = "status-pill";
  if (state === "running") statusPill.classList.add("busy");
  if (state === "done") statusPill.classList.add("done");
  if (state === "warning") statusPill.classList.add("warning");
  if (state === "error") statusPill.classList.add("error");
  if (state === "stopped") statusPill.classList.add("stopped");
  statusPill.textContent = {
    ready: "Ready",
    running: "Running",
    done: "Done",
    warning: "Warning",
    error: "Error",
    stopped: "Stopped",
  }[state] || "Ready";
  thinkingMeta.innerHTML = metaItems.map((item) => `<span>${escapeHtml(item)}</span>`).join("");
  if (payload) {
    renderThinkingPanel(payload);
  }
}

function resetThinkingBar() {
  thinkingLogLines = [];
  thinkingDetails.open = false;
  setThinkingDisplay("ready", runtimeMeta({ elapsed_seconds: 0 }), {
    runtime: { logs: [] },
  });
}

function startThinking(request) {
  isRunning = true;
  sendButton.disabled = true;
  stopButton.disabled = false;
  thinkingDetails.open = false;
  thinkingLogLines = [];
  appendThinkingLog("Browser request started.");
  runtimeStartedAt = Date.now();
  if (runtimeTimer) clearInterval(runtimeTimer);
  const update = () => {
    const elapsed = (Date.now() - runtimeStartedAt) / 1000;
    setThinkingDisplay(
      "running",
      runtimeMeta({ elapsed_seconds: elapsed }),
      {
        runtime: {
          status: "running",
          elapsed_seconds: elapsed,
          model_key: modelSelect.value || "default",
          session_id: activeSessionId,
          request,
          max_skill_steps: Number(maxStepsInput.value || config.default_max_skill_steps || 5),
          logs: thinkingLogLines,
        },
        trace: [],
        evidence: {},
        verification: {},
      },
    );
  };
  update();
  runtimeTimer = setInterval(update, 500);
}

function finishThinking(result) {
  if (runtimeTimer) {
    clearInterval(runtimeTimer);
    runtimeTimer = null;
  }
  isRunning = false;
  sendButton.disabled = false;
  stopButton.disabled = true;
  if (result?.session_id && result.session_id !== activeSessionId) {
    const session = currentSession();
    session.id = result.session_id;
    activeSessionId = result.session_id;
  }
  const runtime = result?.runtime || {};
  const verification = runtime.verification || result?.verification?.status || "ok";
  const state = verification === "error" ? "error" : verification === "warning" ? "warning" : "done";
  setThinkingDisplay(state, runtimeMeta(runtime), result);
  loadUploads().catch((error) => console.warn("Failed to load uploads.", error));
}

function failThinking(error) {
  if (runtimeTimer) {
    clearInterval(runtimeTimer);
    runtimeTimer = null;
  }
  isRunning = false;
  sendButton.disabled = false;
  stopButton.disabled = true;
  const runtime = error?.result?.runtime || {};
  setThinkingDisplay("error", runtimeMeta(runtime), error?.result || { runtime });
}

function stopThinking() {
  if (runtimeTimer) {
    clearInterval(runtimeTimer);
    runtimeTimer = null;
  }
  isRunning = false;
  sendButton.disabled = false;
  stopButton.disabled = true;
  const elapsed = runtimeStartedAt ? (Date.now() - runtimeStartedAt) / 1000 : 0;
  setThinkingDisplay(
    "stopped",
    runtimeMeta({ elapsed_seconds: elapsed }),
    {
      runtime: {
        status: "stopped",
        elapsed_seconds: elapsed,
        model_key: modelSelect.value || "default",
        session_id: activeSessionId,
        logs: [
          ...thinkingLogLines,
          "Browser request aborted by user.",
          "The current synchronous backend cannot guarantee server-side cancellation.",
        ],
      },
      trace: [],
      evidence: {},
      verification: {},
    },
  );
}

function stopCurrentRequest() {
  if (!isRunning || !activeAbortController) return;
  requestStopped = true;
  activeAbortController.abort();
  stopThinking();
  addMessage("assistant", "Stopped waiting for this request.");
}

function scrollBottom() {
  chatScroll.scrollTop = chatScroll.scrollHeight;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function prettyJson(value) {
  return escapeHtml(JSON.stringify(value ?? {}, null, 2));
}

function verificationClass(result) {
  const status = result?.verification?.status || "ok";
  if (status === "error") return "error";
  if (status === "warning") return "warning";
  return "ok";
}

function resultSummaryTags(result) {
  const tags = [];
  const verification = result?.verification?.status || "ok";
  tags.push(`<span class="tag ${verificationClass(result)}">verification: ${escapeHtml(verification)}</span>`);
  if (result?.route?.mode) {
    tags.push(`<span class="tag">route: ${escapeHtml(result.route.mode)}</span>`);
  }
  if (result?.plan?.mode) {
    tags.push(`<span class="tag">plan: ${escapeHtml(result.plan.mode)}</span>`);
  }
  return tags.length ? `<div class="meta-row">${tags.join("")}</div>` : "";
}

function fileNameFromPath(path) {
  const clean = String(path || "").split(/[?#]/)[0];
  return clean.split(/[\\/]/).filter(Boolean).pop() || clean || "structure";
}

function isStructurePath(path) {
  const clean = String(path || "").toLowerCase().split(/[?#]/)[0];
  return structureSuffixes.some((suffix) => clean.endsWith(suffix));
}

function isImagePath(path) {
  const clean = String(path || "").toLowerCase().split(/[?#]/)[0];
  return imageSuffixes.some((suffix) => clean.endsWith(suffix));
}

function structureFormat(path) {
  const clean = String(path || "").toLowerCase();
  return clean.endsWith(".pdb") ? "pdb" : "cif";
}

function addStructureArtifact(artifacts, seen, path, label = "") {
  const cleanPath = String(path || "").trim();
  if (!cleanPath || !isStructurePath(cleanPath) || seen.has(cleanPath)) return;
  seen.add(cleanPath);
  artifacts.push({
    path: cleanPath,
    label: label || fileNameFromPath(cleanPath),
    pdbId: pdbIdFromLabelOrPath(label, cleanPath),
    format: structureFormat(cleanPath),
  });
}

function pdbIdFromLabelOrPath(label, path) {
  const combined = `${label || ""} ${fileNameFromPath(path || "")}`;
  const match = combined.match(/\b([0-9][A-Za-z0-9]{3})\b/);
  return match ? match[1].toUpperCase() : "";
}

function collectStructureArtifacts(result) {
  const artifacts = [];
  const seen = new Set();
  for (const item of result?.artifacts || []) {
    if (item?.kind === "structure" && item?.source_skill === "protein_structure_analysis") {
      addStructureArtifact(artifacts, seen, item?.path, item?.label || item?.source_skill);
    }
  }
  if (artifacts.length) return artifacts;

  const evidence = result?.evidence || {};
  for (const item of evidence.outputs || []) {
    if (item?.skill === "protein_structure_analysis") {
      addStructureArtifact(artifacts, seen, item?.structure_path, item?.pdb_id || item?.summary);
    }
  }
  for (const item of evidence.tool_outputs || []) {
    if (item?.skill === "protein_structure_analysis" && item?.tool === "protein_structure_analyze") {
      addStructureArtifact(artifacts, seen, item?.structure_path, item?.pdb_id || item?.summary);
    }
  }
  return artifacts;
}

function addFigureArtifact(artifacts, seen, path, label = "") {
  const cleanPath = String(path || "").trim();
  if (!cleanPath || !isImagePath(cleanPath) || seen.has(cleanPath)) return;
  seen.add(cleanPath);
  artifacts.push({
    path: cleanPath,
    label: label || fileNameFromPath(cleanPath),
  });
}

function collectFigureArtifacts(result) {
  const artifacts = [];
  const seen = new Set();
  for (const item of result?.artifacts || []) {
    if (item?.kind === "image") {
      addFigureArtifact(artifacts, seen, item?.path, item?.label || item?.source_skill);
    }
  }
  if (artifacts.length) return artifacts;

  const evidence = result?.evidence || {};
  for (const item of evidence.outputs || []) {
    addFigureArtifact(artifacts, seen, item?.image_path, item?.label || item?.summary || item?.skill);
    addFigureArtifact(artifacts, seen, item?.genome_map_path, item?.label || item?.summary || item?.skill);
  }
  for (const item of evidence.tool_outputs || []) {
    addFigureArtifact(artifacts, seen, item?.image_path, item?.label || item?.summary || item?.tool);
    addFigureArtifact(artifacts, seen, item?.genome_map_path, item?.label || item?.summary || item?.tool);
  }
  return artifacts;
}

function artifactUrl(path, options = {}) {
  const params = new URLSearchParams({ path: String(path || "") });
  if (options.viewer) {
    params.set("viewer", options.viewer);
  }
  return `/artifact?${params.toString()}`;
}

function collectPipelineOutputRecords(result) {
  const records = [];
  const seen = new Set();
  const evidence = result?.evidence || {};
  const candidates = [
    ...(Array.isArray(evidence.outputs) ? evidence.outputs : []),
    ...(Array.isArray(evidence.tool_outputs) ? evidence.tool_outputs : []),
  ];

  for (const candidate of candidates) {
    const isPipeline = candidate?.skill === "pipeline_runner" || candidate?.tool === "pipeline_runner";
    if (!isPipeline || !Array.isArray(candidate.output_records)) continue;
    for (const record of candidate.output_records) {
      const path = String(record?.path || "").trim();
      if (!path || record?.exists === false || seen.has(path)) continue;
      seen.add(path);
      records.push({
        path,
        label: String(record?.label || record?.name || fileNameFromPath(path)),
        kind: String(record?.kind || "file"),
      });
    }
  }

  if (records.length) return records;
  const excludedKinds = new Set(["config", "directory", "input", "upload"]);
  for (const artifact of result?.artifacts || []) {
    const path = String(artifact?.path || "").trim();
    if (
      artifact?.source_skill !== "pipeline_runner" ||
      !path ||
      excludedKinds.has(String(artifact?.kind || "")) ||
      seen.has(path)
    ) continue;
    seen.add(path);
    records.push({
      path,
      label: String(artifact?.label || fileNameFromPath(path)),
      kind: String(artifact?.kind || "file"),
    });
  }
  return records;
}

function pipelineNameFromResult(result) {
  const outputs = result?.evidence?.outputs;
  if (Array.isArray(outputs)) {
    for (let index = outputs.length - 1; index >= 0; index -= 1) {
      if (outputs[index]?.skill === "pipeline_runner" && outputs[index]?.pipeline_name) {
        return String(outputs[index].pipeline_name);
      }
    }
  }
  return "pipeline";
}

function pipelineDownloadsHtml(result, records = collectPipelineOutputRecords(result)) {
  if (!records.length) return "";
  const pipelineName = pipelineNameFromResult(result);
  const links = records.map((record) => {
    const filename = fileNameFromPath(record.path);
    const url = artifactUrl(record.path);
    return `
      <a class="pipeline-download" href="${escapeHtml(url)}" download="${escapeHtml(filename)}"
        title="${escapeHtml(record.path)}">
        <span>${escapeHtml(record.label)}</span>
        <small>${escapeHtml(filename)} · ${escapeHtml(record.kind)}</small>
      </a>
    `;
  }).join("");
  return `
    <section class="pipeline-downloads" aria-label="Pipeline result downloads">
      <div class="pipeline-downloads-heading">
        <strong>Result downloads</strong>
        <span>${records.length} files</span>
      </div>
      <div class="pipeline-download-grid">${links}</div>
      <p class="pipeline-download-note">
        Result contents are not previewed automatically.
        To review them here, ask: <q>Collect and show all results from the ${escapeHtml(pipelineName)} pipeline run.</q>
      </p>
    </section>
  `;
}

function collectedBundleHtml(result) {
  const bundles = (result?.artifacts || []).filter((artifact) => (
    artifact?.source_skill === "pipeline_results" &&
    artifact?.kind === "compressed" &&
    String(artifact?.path || "").toLowerCase().endsWith(".zip")
  ));
  if (!bundles.length) return "";
  return bundles.map((artifact) => {
    const filename = fileNameFromPath(artifact.path);
    return `
      <section class="pipeline-downloads" aria-label="Collected result bundle">
        <div class="pipeline-downloads-heading"><strong>Collected result bundle</strong></div>
        <div class="pipeline-download-grid">
          <a class="pipeline-download" href="${escapeHtml(artifactUrl(artifact.path))}"
            download="${escapeHtml(filename)}">
            <span>Download all collected results</span>
            <small>${escapeHtml(filename)} · ZIP archive</small>
          </a>
        </div>
      </section>
    `;
  }).join("");
}

function figureArtifactsHtml(result) {
  const artifacts = collectFigureArtifacts(result);
  if (!artifacts.length) return "";
  return artifacts.map((artifact) => {
    const title = artifact.label && artifact.label !== artifact.path
      ? artifact.label
      : fileNameFromPath(artifact.path);
    const url = artifactUrl(artifact.path);
    return `
      <figure class="artifact-figure">
        <div class="artifact-figure-frame">
          <img src="${escapeHtml(url)}" alt="${escapeHtml(title)}" loading="lazy">
        </div>
        <figcaption>
          <span>${escapeHtml(title)}</span>
          <a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">Open figure</a>
        </figcaption>
      </figure>
    `;
  }).join("");
}

function structureViewerHtml(result) {
  const artifacts = collectStructureArtifacts(result);
  if (!artifacts.length) return "";
  return artifacts.map((artifact, index) => {
    const title = artifact.label && artifact.label !== artifact.path
      ? `${artifact.label} · ${fileNameFromPath(artifact.path)}`
      : fileNameFromPath(artifact.path);
    return `
      <details class="structure-viewer-details">
        <summary>3D structure: ${escapeHtml(title)} <span>Open viewer</span></summary>
        <div class="structure-viewer"
          data-structure-path="${escapeHtml(artifact.path)}"
          data-pdb-id="${escapeHtml(artifact.pdbId)}"
          data-structure-format="${escapeHtml(artifact.format)}">
          <div class="structure-toolbar" aria-label="Structure display controls">
            <button type="button" data-style="cartoon" class="active">Cartoon</button>
            <button type="button" data-style="stick">Stick</button>
            <button type="button" data-style="sphere">Sphere</button>
            <button type="button" data-style="line">Line</button>
          </div>
          <div class="structure-canvas" role="img" aria-label="Interactive molecular structure viewer">
            <div class="structure-loading">Loading 3D viewer...</div>
          </div>
          <div class="structure-path">${escapeHtml(artifact.path)}</div>
        </div>
      </details>
    `;
  }).join("");
}

function resultDetails(result) {
  if (!result) return "";
  const runtime = result.runtime || {};
  const pipelineOutputs = collectPipelineOutputRecords(result);
  return `
    ${pipelineDownloadsHtml(result, pipelineOutputs)}
    ${pipelineOutputs.length ? "" : collectedBundleHtml(result)}
    ${pipelineOutputs.length ? "" : figureArtifactsHtml(result)}
    ${pipelineOutputs.length ? "" : structureViewerHtml(result)}
    ${resultSummaryTags(result)}
    <div class="result-diagnostics">
      <details>
        <summary>Runtime</summary>
        <pre>${prettyJson(runtime)}</pre>
      </details>
      <details>
        <summary>Evidence</summary>
        <pre>${prettyJson(result.evidence)}</pre>
      </details>
      <details>
        <summary>Verification</summary>
        <pre>${prettyJson(result.verification)}</pre>
      </details>
      <details>
        <summary>Route and plan</summary>
        <pre>${prettyJson({ route: result.route, plan: result.plan })}</pre>
      </details>
      <details>
        <summary>Trace</summary>
        <pre>${prettyJson(result.trace)}</pre>
      </details>
    </div>
  `;
}

function compactStoredResult(result) {
  if (!result) return null;
  return {
    session_id: result.session_id || null,
    run: result.run || null,
    runtime: result.runtime || null,
    artifacts: result.artifacts || null,
    evidence: result.evidence || null,
    verification: result.verification || null,
    route: result.route || null,
    plan: result.plan || null,
    trace: result.trace || null,
  };
}

function renderMessageText(role, text) {
  if (role === "assistant" && typeof window.renderMarkdown === "function") {
    return window.renderMarkdown(text);
  }
  return escapeHtml(text);
}

function renderMessage(role, text, result = null) {
  const message = document.createElement("article");
  message.className = `message ${role}`;
  const avatar = role === "assistant" ? "BA" : "You";
  message.innerHTML = `
    <div class="avatar">${avatar}</div>
    <div class="bubble">
      <div class="bubble-text markdown-body">${renderMessageText(role, text)}</div>
      ${resultDetails(result)}
    </div>
  `;
  chat.appendChild(message);
  initializeStructureViewers(message);
}

function initializeStructureViewers(root = document) {
  root.querySelectorAll(".structure-viewer-details").forEach((details) => {
    if (details.dataset.bound === "true") return;
    details.dataset.bound = "true";
    details.addEventListener("toggle", () => {
      if (details.open) {
        loadStructureViewer(details);
      }
    });
    details.querySelectorAll("[data-style]").forEach((button) => {
      button.addEventListener("click", () => {
        applyStructureStyle(details, button.dataset.style || "cartoon");
      });
    });
  });
}

async function loadStructureViewer(details) {
  if (details.dataset.loaded === "true" || details.dataset.loading === "true") return;
  const container = details.querySelector(".structure-canvas");
  const viewerElement = details.querySelector(".structure-viewer");
  if (!container || !viewerElement) return;
  if (!window.$3Dmol) {
    container.innerHTML = `<div class="structure-error">3Dmol.js did not load. Check network access to the CDN.</div>`;
    return;
  }
  if (!browserSupportsWebGL()) {
    container.innerHTML = `
      <div class="structure-error">
        <div>
          WebGL is not available in this browser context, so the 3D viewer cannot start.<br>
          Try Chrome/Firefox with hardware acceleration enabled, or use the local structure file in PyMOL/ChimeraX.
        </div>
      </div>
    `;
    return;
  }

  details.dataset.loading = "true";
  const path = viewerElement.dataset.structurePath || "";
  const pdbId = viewerElement.dataset.pdbId || "";
  try {
    container.innerHTML = "";
    const response = await fetch(artifactUrl(path, { viewer: "pdb" }));
    if (!response.ok) {
      const text = await response.text();
      throw new Error(`Local artifact request failed: HTTP ${response.status} ${text.slice(0, 160)}`);
    }
    const structureText = await response.text();
    renderStructureText(details, container, structureText, "pdb");
  } catch (error) {
    if (pdbId) {
      try {
        await renderStructureFromPdbId(details, container, pdbId);
        return;
      } catch (fallbackError) {
        container.innerHTML = structureLoadErrorHtml(path, error, fallbackError);
      }
    } else {
      container.innerHTML = structureLoadErrorHtml(path, error);
    }
  } finally {
    details.dataset.loading = "false";
  }
}

function renderStructureText(details, container, structureText, format) {
  ensureViewerContainerReady(container);
  const viewer = window.$3Dmol.createViewer(container, {
    backgroundColor: "white",
    antialias: true,
  });
  const model = viewer.addModel(structureText, format);
  if (!model) {
    throw new Error(`3Dmol could not parse ${format} structure text.`);
  }
  details._bioagentViewer = viewer;
  details.dataset.loaded = "true";
  applyStructureStyle(details, activeStructureStyle(details));
}

function renderStructureFromPdbId(details, container, pdbId) {
  return new Promise((resolve, reject) => {
    container.innerHTML = "";
    let viewer;
    try {
      ensureViewerContainerReady(container);
      viewer = window.$3Dmol.createViewer(container, {
        backgroundColor: "white",
        antialias: true,
      });
    } catch (error) {
      reject(error);
      return;
    }
    let settled = false;
    const timeout = window.setTimeout(() => {
      if (!settled) {
        settled = true;
        reject(new Error(`PDB fallback timed out for ${pdbId}.`));
      }
    }, 15000);
    try {
      window.$3Dmol.download(`pdb:${pdbId}`, viewer, { format: "pdb" }, (model) => {
        if (settled) return;
        window.clearTimeout(timeout);
        if (!model) {
          settled = true;
          reject(new Error(`3Dmol PDB fallback returned no model for ${pdbId}.`));
          return;
        }
        details._bioagentViewer = viewer;
        details.dataset.loaded = "true";
        applyStructureStyle(details, activeStructureStyle(details));
        settled = true;
        resolve();
      });
    } catch (error) {
      window.clearTimeout(timeout);
      settled = true;
      reject(error);
    }
  });
}

function browserSupportsWebGL() {
  try {
    const canvas = document.createElement("canvas");
    return Boolean(
      canvas.getContext("webgl2") ||
      canvas.getContext("webgl") ||
      canvas.getContext("experimental-webgl")
    );
  } catch (error) {
    return false;
  }
}

function ensureViewerContainerReady(container) {
  const rect = container.getBoundingClientRect();
  if (rect.width < 20 || rect.height < 20) {
    throw new Error(
      `3D viewer container is not ready yet (${Math.round(rect.width)}x${Math.round(rect.height)}).`
    );
  }
}

function errorMessage(error) {
  if (!error) return "unknown error";
  return error.message || String(error);
}

function structureLoadErrorHtml(path, error, fallbackError = null) {
  const localMessage = errorMessage(error);
  const fallbackMessage = fallbackError ? `<br>Fallback: ${escapeHtml(errorMessage(fallbackError))}` : "";
  return `
    <div class="structure-error">
      <div>
        Failed to load structure.<br>
        Local file: ${escapeHtml(path)}<br>
        Error: ${escapeHtml(localMessage)}
        ${fallbackMessage}
      </div>
    </div>
  `;
}

function activeStructureStyle(details) {
  const active = details.querySelector("[data-style].active");
  return active?.dataset?.style || "cartoon";
}

function applyStructureStyle(details, style) {
  const viewer = details._bioagentViewer;
  details.querySelectorAll("[data-style]").forEach((button) => {
    button.classList.toggle("active", button.dataset.style === style);
  });
  if (!viewer) {
    if (details.open) {
      loadStructureViewer(details);
    }
    return;
  }

  viewer.setStyle({}, {});
  if (style === "stick") {
    viewer.setStyle({}, { stick: { radius: 0.16, colorscheme: "Jmol" } });
  } else if (style === "sphere") {
    viewer.setStyle({}, { sphere: { scale: 0.28, colorscheme: "Jmol" } });
  } else if (style === "line") {
    viewer.setStyle({}, { line: { colorscheme: "Jmol" } });
  } else {
    viewer.setStyle({ hetflag: false }, { cartoon: { color: "spectrum" } });
    viewer.setStyle({ hetflag: true }, { stick: { radius: 0.22, colorscheme: "greenCarbon" } });
    viewer.setStyle({ resn: "HOH" }, {});
  }
  viewer.zoomTo();
  viewer.render();
  if (typeof viewer.resize === "function") {
    setTimeout(() => {
      viewer.resize();
      viewer.render();
    }, 0);
  }
}

function addMessage(role, text, result = null, options = {}) {
  if (chat.querySelector(".empty-state")) {
    chat.innerHTML = "";
  }
  renderMessage(role, text, result);
  if (options.persist !== false) {
    updateCurrentSession((session) => {
      if (role === "user" && session.messages.filter((message) => message.role === "user").length === 0) {
        session.title = titleFromText(text);
      }
      session.messages.push({
        role,
        text: String(text || ""),
        result: compactStoredResult(result),
        created_at: nowIso(),
      });
    });
  }
  renderUploadInsertOptions();
  scrollBottom();
}

function parseStreamFrame(frame) {
  let event = "message";
  const dataLines = [];
  for (const rawLine of frame.split(/\r?\n/)) {
    const line = rawLine.trimEnd();
    if (line.startsWith("event:")) {
      event = line.slice("event:".length).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice("data:".length).trimStart());
    }
  }
  const data = dataLines.join("\n");
  return {
    event,
    payload: data ? JSON.parse(data) : {},
  };
}

function handleStreamFrame(frame) {
  if (!frame.trim()) return { done: false, result: null };
  const { event, payload } = parseStreamFrame(frame);
  if (event === "status") {
    appendThinkingLog(payload.message || "Agent request started.");
    return { done: false, result: null };
  }
  if (event === "log") {
    appendThinkingLog(payload.message || "");
    return { done: false, result: null };
  }
  if (event === "result") {
    return { done: true, result: payload };
  }
  if (event === "error") {
    const error = new Error(payload.error || "Agent stream failed.");
    error.result = payload;
    throw error;
  }
  return { done: false, result: null };
}

async function runAgent(request, signal) {
  const payload = {
    request,
    session_id: activeSessionId,
    model_key: modelSelect.value,
    max_skill_steps: Number(maxStepsInput.value || config.default_max_skill_steps || 5),
  };
  const response = await fetch("/run_stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }
  if (!response.body) {
    throw new Error("Streaming response body is not available in this browser.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split(/\n\n/);
    buffer = frames.pop() || "";
    for (const frame of frames) {
      const parsed = handleStreamFrame(frame);
      if (parsed.done) {
        return parsed.result;
      }
    }
  }

  buffer += decoder.decode();
  if (buffer.trim()) {
    const parsed = handleStreamFrame(buffer);
    if (parsed.done) {
      return parsed.result;
    }
  }
  throw new Error("Agent stream ended before returning a result.");
}

async function submitPrompt(event) {
  event.preventDefault();
  if (isRunning) return;
  const text = promptInput.value.trim();
  if (!text) return;

  promptInput.value = "";
  addMessage("user", text);
  requestStopped = false;
  activeAbortController = new AbortController();
  startThinking(text);
  try {
    const result = await runAgent(text, activeAbortController.signal);
    finishThinking(result);
    addMessage("assistant", result.answer || "", result);
  } catch (error) {
    if (requestStopped || error.name === "AbortError") {
      return;
    }
    failThinking(error);
    addMessage("assistant", `Request failed: ${error.message}`);
  } finally {
    activeAbortController = null;
    requestStopped = false;
    promptInput.focus();
  }
}

function bindExampleButtons(root = document) {
  root.querySelectorAll("[data-example]").forEach((button) => {
    button.addEventListener("click", () => {
      promptInput.value = button.getAttribute("data-example");
      promptInput.focus();
    });
  });
}

function bindEvents() {
  composer.addEventListener("submit", submitPrompt);
  promptInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      composer.requestSubmit();
    }
  });

  bindExampleButtons(document);
  modelSelect.addEventListener("change", updateActiveModel);
  stopButton.addEventListener("click", stopCurrentRequest);
  newChatButton.addEventListener("click", startNewChat);
  uploadButton.addEventListener("click", () => {
    if (!isRunning) {
      uploadInput.click();
    }
  });
  uploadInput.addEventListener("change", () => {
    uploadSelectedFiles(uploadInput.files);
  });
  uploadList.addEventListener("click", (event) => {
    const item = event.target.closest(".upload-item");
    if (!item) return;
    if (event.target.closest("[data-upload-use]")) {
      useUploadPath(item.dataset.path);
      return;
    }
    if (event.target.closest("[data-upload-delete]")) {
      deleteUploadById(item.dataset.artifactId).catch((error) => {
        addMessage("assistant", `Delete upload failed: ${error.message}`);
      });
    }
  });
  sessionList.addEventListener("click", (event) => {
    const item = event.target.closest(".session-item");
    if (!item) return;
    const sessionId = item.dataset.sessionId;
    if (event.target.closest(".session-delete")) {
      deleteSessionById(sessionId);
      return;
    }
    switchSession(sessionId);
  });
}

async function init() {
  loadSessions();
  bindEvents();
  renderSessionList();
  renderCurrentChat();
  updateActiveSession();
  resetThinkingBar();
  renderUploadList();
  renderUploadInsertOptions();
  loadUploads().catch((error) => console.warn("Failed to load uploads.", error));
  try {
    await loadConfig();
  } catch (error) {
    addMessage("assistant", `Failed to load web configuration: ${error.message}`);
  }
}

init();
