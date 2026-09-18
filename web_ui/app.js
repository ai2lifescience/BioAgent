let config = {
  default_model_key: "",
  default_max_turns: 5,
  models: [],
};

const modelSelect = document.getElementById("model");
const maxTurnsInput = document.getElementById("maxTurns");
const chat = document.getElementById("chat");
const chatScroll = document.getElementById("chatScroll");
const promptInput = document.getElementById("prompt");
const sendButton = document.getElementById("send");
const composer = document.getElementById("composer");
const composerAttach = document.getElementById("composerAttach");
const composerFileHint = document.getElementById("composerFileHint");
const exampleParamPrompt = document.getElementById("exampleParamPrompt");
const exampleParamPromptLabel = document.getElementById("exampleParamPromptLabel");
const exampleParamPromptOptions = document.getElementById("exampleParamPromptOptions");
const exampleParamPromptDismiss = document.getElementById("exampleParamPromptDismiss");
const newChatButton = document.getElementById("newChat");
const appShell = document.querySelector(".app");
const toggleSidebarButton = document.getElementById("toggleSidebar");
const sessionList = document.getElementById("sessionList");
const sessionCount = document.getElementById("sessionCount");
const uploadButton = document.getElementById("uploadButton");
const uploadInput = document.getElementById("uploadInput");
const uploadList = document.getElementById("uploadList");
const workspaceCount = document.getElementById("workspaceCount");
const workspaceSummary = document.getElementById("workspaceSummary");
const workspaceRefresh = document.getElementById("workspaceRefresh");
const workspaceSearch = document.getElementById("workspaceSearch");
const workspaceFilter = document.getElementById("workspaceFilter");
const workspaceDropzone = document.getElementById("workspaceDropzone");

const ACTIVE_SESSION_KEY = "bioagent.web.active_session_id.v1";
const SIDEBAR_COLLAPSED_KEY = "bioagent.web.sidebar_collapsed.v3";
let structureSuffixes = [".cif", ".mmcif", ".pdb"];
let imageSuffixes = [".svg"];

let runtimeTimer = null;
let runtimeStartedAt = 0;
let activeAbortController = null;
let requestStopped = false;
let isRunning = false;
let isSessionLoading = false;
let thinkingLogLines = [];
let sessions = [];
let activeSessionId = "";
let workspaceFiles = [];

const SEND_ICON = `
  <svg width="17" height="17" viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <path d="M5 12h14M13 6l6 6-6 6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
  </svg>`;
const PAUSE_ICON = `
  <svg width="17" height="17" viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <rect x="7" y="6" width="3.5" height="12" rx="1" fill="currentColor"/>
    <rect x="13.5" y="6" width="3.5" height="12" rx="1" fill="currentColor"/>
  </svg>`;
const BIOAGENT_ICON = `
  <svg class="avatar-icon" viewBox="0 0 512 512" fill="none" aria-hidden="true">
    <defs><linearGradient id="bsod-screen" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#159BEA"/><stop offset="1" stop-color="#1486D8"/></linearGradient></defs>
    <path d="M256 112c-4-38 10-58 34-67" stroke="#25283A" stroke-width="10" stroke-linecap="round"/>
    <circle cx="300" cy="40" r="18" fill="#159BEA" stroke="#25283A" stroke-width="8"/>
    <rect x="79" y="164" width="35" height="118" rx="17" fill="#D3D2D1" stroke="#25283A" stroke-width="9"/>
    <rect x="398" y="164" width="35" height="118" rx="17" fill="#D3D2D1" stroke="#25283A" stroke-width="9"/>
    <rect x="101" y="126" width="310" height="213" rx="48" fill="url(#bsod-screen)" stroke="#25283A" stroke-width="10"/>
    <path d="M128 162c23-19 52-27 87-27h94c34 0 62 8 77 25" stroke="#63C6F3" stroke-width="9" stroke-linecap="round" opacity=".7"/>
    <rect x="181" y="204" width="13" height="52" rx="6.5" fill="#202332"/>
    <rect x="318" y="204" width="13" height="52" rx="6.5" fill="#202332"/>
    <ellipse cx="166" cy="275" rx="23" ry="12" fill="#F58FAE"/>
    <ellipse cx="346" cy="275" rx="23" ry="12" fill="#F58FAE"/>
    <path d="M241 275c7 9 23 9 30 0" stroke="#63D2F5" stroke-width="8" stroke-linecap="round"/>
    <path d="M104 319c-23 17-28 44-14 61 9 11 23 11 30 1l20-31" fill="#D3D2D1" stroke="#25283A" stroke-width="9" stroke-linecap="round" stroke-linejoin="round"/>
    <path d="M408 319c23 17 28 44 14 61-9 11-23 11-30 1l-20-31" fill="#D3D2D1" stroke="#25283A" stroke-width="9" stroke-linecap="round" stroke-linejoin="round"/>
    <rect x="171" y="331" width="170" height="105" rx="25" fill="#F1F0ED" stroke="#25283A" stroke-width="9"/>
    <rect x="224" y="352" width="64" height="53" rx="8" fill="#168EDC" stroke="#25283A" stroke-width="7"/>
    <rect x="244" y="368" width="24" height="18" rx="3" fill="#82D8F5"/>
    <path d="M190 433v39c0 9 7 16 16 16h31v-55" fill="#C9C8C6" stroke="#25283A" stroke-width="9" stroke-linejoin="round"/>
    <path d="M322 433v39c0 9-7 16-16 16h-31v-55" fill="#C9C8C6" stroke="#25283A" stroke-width="9" stroke-linejoin="round"/>
  </svg>`;
const PIN_ICON = `
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <path d="m9 4 6 0 1 5 3 3v1H5v-1l3-3 1-5Z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>
    <path d="M12 13v7" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
  </svg>`;
const EDIT_ICON = `
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <path d="m4 16.5-.8 4.3 4.3-.8L19 8.5 15.5 5 4 16.5Z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>
    <path d="m13.8 6.7 3.5 3.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
  </svg>`;
const MORE_ICON = `
  <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
    <circle cx="5" cy="12" r="1.7"/><circle cx="12" cy="12" r="1.7"/><circle cx="19" cy="12" r="1.7"/>
  </svg>`;

async function loadConfig() {
  const response = await fetch("/config");
  if (!response.ok) {
    throw new Error(`Failed to load /config: HTTP ${response.status}`);
  }
  config = await response.json();
  applyArtifactConfig(config.files || {});
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
    option.textContent = formatModelLabel(model);
    if (model.key === config.default_model_key) {
      option.selected = true;
    }
    modelSelect.appendChild(option);
  }
  maxTurnsInput.value = config.default_max_turns || 5;
}

function formatModelLabel(model) {
  const label = model.label || model.key;
  const cost = model.cost_tier || "Unknown cost";
  return `${label} (${cost})`;
}

function setSidebarCollapsed(collapsed) {
  const nextState = Boolean(collapsed);
  appShell.classList.toggle("sidebar-collapsed", nextState);
  appShell.classList.toggle("sidebar-expanded", !nextState);
  toggleSidebarButton.setAttribute("aria-expanded", String(!nextState));
  const label = nextState ? "Expand sidebar" : "Collapse sidebar";
  toggleSidebarButton.setAttribute("aria-label", label);
  toggleSidebarButton.title = label;
  localStorage.setItem(SIDEBAR_COLLAPSED_KEY, String(nextState));
}

function initializeSidebar() {
  const stored = localStorage.getItem(SIDEBAR_COLLAPSED_KEY);
  const phoneDefault = window.matchMedia("(max-width: 700px)").matches;
  setSidebarCollapsed(stored === null ? phoneDefault : stored === "true");
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
  const count = Number(session.message_count || 0);
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
    message_count: 0,
    created_at: timestamp,
    updated_at: timestamp,
    pinned: false,
  };
}

function normalizeSession(raw) {
  const id = raw?.session_id;
  if (!id) return null;
  return {
    id: String(id),
    title: String(raw.title || "New chat"),
    messages: [],
    message_count: Number(raw.message_count || 0),
    created_at: raw.created_at || nowIso(),
    updated_at: raw.updated_at || raw.created_at || nowIso(),
    pinned: Boolean(raw.pinned),
  };
}

function sortedSessions() {
  return [...sessions].sort((left, right) => {
    if (left.pinned !== right.pinned) return left.pinned ? -1 : 1;
    return new Date(right.updated_at).getTime() - new Date(left.updated_at).getTime();
  });
}

async function loadSessions() {
  const response = await fetch("/sessions");
  if (!response.ok) {
    throw new Error(`Failed to load sessions: HTTP ${response.status}`);
  }
  const payload = await response.json();
  sessions = (Array.isArray(payload.sessions) ? payload.sessions : [])
    .map(normalizeSession)
    .filter(Boolean);
  if (!sessions.length) sessions = [createSession()];

  activeSessionId = localStorage.getItem(ACTIVE_SESSION_KEY) || sessions[0].id;
  if (!sessions.some((session) => session.id === activeSessionId)) {
    activeSessionId = sessions[0].id;
  }
  rememberActiveSession();
}

function rememberActiveSession() {
  localStorage.setItem(ACTIVE_SESSION_KEY, activeSessionId);
}

async function loadConversation(sessionId) {
  if (!sessionId) return;
  const response = await fetch(`/sessions/${encodeURIComponent(sessionId)}/messages`);
  if (!response.ok) {
    throw new Error(`Failed to load conversation: HTTP ${response.status}`);
  }
  const payload = await response.json();
  if (sessionId !== activeSessionId) return;
  const session = sessions.find((item) => item.id === sessionId);
  if (!session) return;
  session.messages = (Array.isArray(payload.messages) ? payload.messages : [])
    .filter((message) => message && ["assistant", "user"].includes(message.role))
    .map((message) => ({
      role: message.role,
      text: String(message.text || ""),
      result: null,
      created_at: message.created_at || null,
    }));
  session.message_count = session.messages.length;
  if (payload.pending_approval) {
    session.messages.push({
      role: "assistant",
      text: payload.pending_approval.answer,
      result: payload.pending_approval,
    });
  }
}

function currentSession() {
  let session = sessions.find((item) => item.id === activeSessionId);
  if (!session) {
    session = createSession();
    sessions.unshift(session);
    activeSessionId = session.id;
    rememberActiveSession();
  }
  return session;
}

function updateCurrentSession(updater) {
  const session = currentSession();
  updater(session);
  session.message_count = session.messages.length;
  session.updated_at = nowIso();
  rememberActiveSession();
  renderSessionList();
}

function emptyStateHtml() {
  return `
    <div class="empty-state">
      <div class="empty-intro">
        <span class="empty-kicker">A focused workspace for biology</span>
        <h1>What are you working on?</h1>
        <p>Ask a question, upload data, or run a reproducible pipeline. Results and files stay together in this chat.</p>
      </div>
      <div class="empty-onboarding">
        <section class="empty-section">
          <div class="empty-section-header">
            <div>
              <span class="panel-eyebrow">Quick starts</span>
              <span class="empty-section-note">Choose a starting point</span>
            </div>
          </div>
          <div class="empty-grid">
            <button class="example-button" data-example="What is the GC content of this sequence?">Analyze a sequence</button>
            <button class="example-button" data-example="Download and analyze PDB structure 3GOU">Inspect a structure</button>
            <button class="example-button" data-example="Download 10 NCBI records for PhiX174 genes A G">Retrieve public data</button>
            <button class="example-button" data-example="List the files in my workspace and describe what they contain.">Explore workspace files</button>
            <button class="example-button" data-example="Search UniProt for BRCA1 human">Search UniProt</button>
            <button class="example-button" data-example="Summarize genome structure and host range of PhiX174 with trusted sources.">Species report</button>
          </div>
          <details class="more-examples">
            <summary>More pipelines</summary>
            <div class="examples">
              <button class="example-button" data-example="Run pipeline with pipeline_name: generic_bio">Generic bio pipeline</button>
              <button class="example-button" data-example="Run pipeline with pipeline_name: generic_shell">Shell pipeline</button>
              <button class="example-button" data-example="Run pipeline with pipeline_name: generic_snakemake">Snakemake pipeline</button>
              <button class="example-button" data-example="Run pipeline with pipeline_name: generic_nextflow">Nextflow pipeline</button>
              <button class="example-button" data-example="Run pipeline with pipeline_name: generic_wdl">WDL pipeline</button>
              <button class="example-button" data-example="Run pipeline with pipeline_name: metagenomic_qc">Metagenomic QC</button>
              <button class="example-button" data-example="Run pipeline with pipeline_name: alignment_based_Identification">Alignment-based identification</button>
              <button
                class="example-button"
                data-example-template="Run pipeline with pipeline_name: molecular_typing pathogen: {pathogen}"
                data-param-name="pathogen"
                data-param-label="Choose pathogen for Molecular Typing"
                data-param-options="H1N1,H3N2,SARS_CoV_2"
              >Molecular typing</button>
              <button class="example-button" data-example="Run pipeline with pipeline_name: de_novo_assembly">De novo assembly</button>
              <button
                class="example-button"
                data-example-template="Run pipeline with pipeline_name: risk_assessment pathogen: {pathogen}"
                data-param-name="pathogen"
                data-param-label="Choose pathogen for Risk Assessment"
                data-param-options="H1N1,H3N2,SARS_CoV_2"
              >Risk assessment</button>
            </div>
          </details>
        </section>
        <section class="empty-section empty-workflow">
          <div class="empty-section-header">
            <div>
              <span class="panel-eyebrow">Simple workflow</span>
              <span class="empty-section-note">From question to result</span>
            </div>
          </div>
          <ol class="workflow-steps">
            <li><span>1</span><div><strong>Ask</strong><small>Describe the biology task in plain language.</small></div></li>
            <li><span>2</span><div><strong>Work</strong><small>BioAgent selects tools and inspects your files.</small></div></li>
            <li><span>3</span><div><strong>Review</strong><small>Approve pipelines and download verified outputs.</small></div></li>
          </ol>
        </section>
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
    return;
  }
  for (const message of messages) {
    renderMessage(message.role, message.text || "", message.result || null);
  }
  scrollBottom();
}

function renderSessionList() {
  sessionCount.textContent = String(sessions.length);
  sessionList.innerHTML = "";
  if (!sessions.length) {
    sessionList.innerHTML = `<div class="session-empty">No saved chats.</div>`;
    return;
  }
  for (const session of sortedSessions()) {
    const item = document.createElement("div");
    item.className = `session-item ${session.id === activeSessionId ? "active" : ""} ${session.pinned ? "pinned" : ""}`;
    item.dataset.sessionId = session.id;
    item.innerHTML = `
      <button class="session-select" type="button">
        <span class="session-title-row">
          <span class="session-title">${escapeHtml(session.title || "New chat")}</span>
          ${session.pinned ? `<span class="session-pinned-badge" aria-label="Pinned">${PIN_ICON}</span>` : ""}
        </span>
        <span class="session-meta">${escapeHtml(formatSessionMeta(session))}</span>
      </button>
      <div class="session-actions">
        <button class="session-more" type="button" data-session-menu aria-haspopup="menu" aria-expanded="false" aria-label="Actions for ${escapeHtml(session.title || "session")}" title="Session actions">${MORE_ICON}</button>
        <div class="session-menu" role="menu" hidden>
          <button class="session-menu-item" type="button" role="menuitem" data-session-pin aria-pressed="${session.pinned ? "true" : "false"}">${PIN_ICON}<span>${session.pinned ? "Unpin chat" : "Pin chat"}</span></button>
          <button class="session-menu-item" type="button" role="menuitem" data-session-rename>${EDIT_ICON}<span>Rename chat</span></button>
          <button class="session-menu-item session-menu-delete" type="button" role="menuitem" data-session-delete><span class="session-menu-x" aria-hidden="true">&times;</span><span>Delete chat</span></button>
        </div>
      </div>
    `;
    sessionList.appendChild(item);
  }
}

function setSessionLoading(loading) {
  isSessionLoading = loading;
  sendButton.disabled = loading;
  uploadButton.disabled = loading || isRunning;
  newChatButton.disabled = loading || isRunning;
  setComposerControlsDisabled(loading || isRunning);
}

function setSendButtonState(running) {
  sendButton.classList.toggle("is-running", running);
  sendButton.setAttribute("aria-label", running ? "Pause current request" : "Send message");
  sendButton.title = running ? "Pause current request" : "Send message";
  sendButton.innerHTML = running ? PAUSE_ICON : SEND_ICON;
}

function setComposerControlsDisabled(disabled) {
  const nextState = Boolean(disabled);
  modelSelect.disabled = nextState;
  maxTurnsInput.disabled = nextState;
  composerAttach.disabled = nextState;
}

async function loadActiveSession() {
  setSessionLoading(true);
  workspaceFiles = [];
  renderWorkspace();
  chat.textContent = "Loading conversation…";
  try {
    await Promise.all([loadConversation(activeSessionId), loadWorkspace()]);
    renderCurrentChat();
    renderSessionList();
    resetThinkingBar();
  } catch (error) {
    renderCurrentChat();
    renderMessage("assistant", `Could not load this chat: ${error.message}`);
  } finally {
    setSessionLoading(false);
  }
}

async function switchSession(sessionId) {
  if (isRunning || isSessionLoading || !sessionId || sessionId === activeSessionId) return;
  activeSessionId = sessionId;
  rememberActiveSession();
  renderSessionList();
  await loadActiveSession();
  promptInput.focus();
}

async function deleteSessionById(sessionId) {
  if (isRunning || isSessionLoading || !sessionId) return;
  setSessionLoading(true);
  try {
    const response = await fetch(`/sessions/${encodeURIComponent(sessionId)}`, { method: "DELETE" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    sessions = sessions.filter((session) => session.id !== sessionId);
    if (!sessions.length) sessions = [createSession()];
    if (!sessions.some((session) => session.id === activeSessionId)) activeSessionId = sessions[0].id;
    rememberActiveSession();
    renderSessionList();
    await loadActiveSession();
  } catch (error) {
    renderMessage("assistant", `Could not delete this chat: ${error.message}`);
  } finally {
    setSessionLoading(false);
  }
}

async function updateSessionById(sessionId, changes) {
  if (isRunning || isSessionLoading || !sessionId) return;
  const session = sessions.find((item) => item.id === sessionId);
  if (!session) return;
  setSessionLoading(true);
  try {
    const response = await fetch(`/sessions/${encodeURIComponent(sessionId)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(changes),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
    if (Object.prototype.hasOwnProperty.call(changes, "title")) session.title = String(payload.title || "New chat");
    if (Object.prototype.hasOwnProperty.call(changes, "pinned")) session.pinned = Boolean(payload.pinned);
    session.updated_at = payload.updated_at || nowIso();
    renderSessionList();
  } catch (error) {
    renderMessage("assistant", `Could not update this chat: ${error.message}`);
  } finally {
    setSessionLoading(false);
  }
}

async function renameSessionById(sessionId) {
  const session = sessions.find((item) => item.id === sessionId);
  if (!session || isRunning || isSessionLoading) return;
  const title = window.prompt("Rename chat", session.title || "New chat");
  if (title === null) return;
  const cleaned = title.replace(/\s+/g, " ").trim().slice(0, 80);
  if (!cleaned || cleaned === session.title) return;
  await updateSessionById(sessionId, { title: cleaned });
}

async function toggleSessionPin(sessionId) {
  const session = sessions.find((item) => item.id === sessionId);
  if (!session) return;
  await updateSessionById(sessionId, { pinned: !session.pinned });
}

function closeSessionMenus() {
  sessionList.querySelectorAll(".session-menu:not([hidden])").forEach((menu) => {
    menu.hidden = true;
    const button = menu.parentElement?.querySelector("[data-session-menu]");
    button?.setAttribute("aria-expanded", "false");
  });
}

function openSessionMenu(item, button) {
  const menu = item.querySelector(".session-menu");
  if (!menu) return;
  const wasOpen = !menu.hidden;
  closeSessionMenus();
  if (wasOpen) return;
  menu.hidden = false;
  const buttonRect = button.getBoundingClientRect();
  const menuRect = menu.getBoundingClientRect();
  const left = Math.max(8, Math.min(buttonRect.right - menuRect.width, window.innerWidth - menuRect.width - 8));
  const top = Math.max(8, Math.min(buttonRect.bottom + 4, window.innerHeight - menuRect.height - 8));
  menu.style.left = `${left}px`;
  menu.style.top = `${top}px`;
  button.setAttribute("aria-expanded", "true");
  menu.querySelector("[role=menuitem]")?.focus();
}

function startNewChat() {
  if (isRunning || isSessionLoading) return;
  const session = createSession();
  sessions.unshift(session);
  activeSessionId = session.id;
  rememberActiveSession();
  renderSessionList();
  workspaceFiles = [];
  renderWorkspace();
  renderCurrentChat();
  loadWorkspace().catch((error) => console.warn("Failed to load workspace.", error));
  resetThinkingBar();
  hideExampleParamPrompt();
  promptInput.focus();
}

function renderWorkspace() {
  workspaceCount.textContent = String(workspaceFiles.length);
  if (composerFileHint) {
    composerFileHint.textContent = workspaceFiles.length
      ? `${workspaceFiles.length} file${workspaceFiles.length === 1 ? "" : "s"} attached`
      : "Add files";
  }
  uploadList.classList.toggle("single-file", workspaceFiles.length === 1);
  uploadList.innerHTML = "";
  if (!workspaceFiles.length) {
    workspaceSummary.textContent = "Files are shared with this chat and its tools.";
    uploadList.innerHTML = `<div class="workspace-empty">No files in this workspace yet.</div>`;
    return;
  }
  const totalBytes = workspaceFiles.reduce((sum, file) => sum + Number(file.size || 0), 0);
  workspaceSummary.textContent = `${formatBytes(totalBytes)} · available to this chat and its tools`;
  const query = workspaceSearch.value.trim().toLowerCase();
  const filter = workspaceFilter.value;
  const visibleFiles = workspaceFiles.filter((file) => {
    const path = String(file.workspace_path || file.path || "");
    if (query && !path.toLowerCase().includes(query)) return false;
    const category = workspaceFileCategory(file).key;
    if (filter === "uploads") return category === "uploads";
    if (filter === "outputs") return category === "outputs";
    return true;
  });
  if (!visibleFiles.length) {
    uploadList.innerHTML = `<div class="workspace-empty">No matching files.</div>`;
    return;
  }
  const groups = new Map();
  for (const file of visibleFiles) {
    const category = workspaceFileCategory(file);
    if (!groups.has(category.key)) groups.set(category.key, { ...category, files: [] });
    groups.get(category.key).files.push(file);
  }
  const orderedGroups = ["uploads", "outputs"]
    .map((key) => groups.get(key))
    .filter(Boolean);
  for (const group of orderedGroups) {
    const section = document.createElement("section");
    section.className = "workspace-group";
    const heading = document.createElement("div");
    heading.className = "workspace-group-heading";
    heading.innerHTML = `<span>${escapeHtml(group.label)}</span><span>${group.files.length}</span>`;
    const contents = document.createElement("div");
    contents.className = "workspace-group-files";
    for (const file of group.files) {
      const item = document.createElement("div");
      item.className = "workspace-file";
      item.dataset.workspacePath = file.workspace_path || file.path || "";
      const name = file.name || fileNameFromPath(file.workspace_path || file.path);
      const workspacePath = file.workspace_path || file.path || "";
      item.innerHTML = `
        <div class="workspace-file-main">
          <div class="workspace-file-name" title="${escapeHtml(name)}">${escapeHtml(name)}</div>
          <div class="workspace-file-meta">${escapeHtml(formatBytes(file.size))} · <span class="workspace-file-kind">${escapeHtml(file.kind || "file")}</span></div>
          <div class="workspace-file-path" title="${escapeHtml(workspacePath)}">${escapeHtml(workspacePath)}</div>
        </div>
        <div class="workspace-file-actions">
          <a class="workspace-download" href="${escapeHtml(workspaceFileUrl(workspacePath))}" download>Download</a>
          <button class="workspace-remove" type="button" data-workspace-delete aria-label="Remove ${escapeHtml(name)}">Remove</button>
        </div>
      `;
      contents.appendChild(item);
    }
    section.append(heading, contents);
    uploadList.appendChild(section);
  }
}

function workspaceFileCategory(file) {
  const path = String(file?.workspace_path || file?.path || "");
  if (path.startsWith("uploads/")) return { key: "uploads", label: "Inputs" };
  return { key: "outputs", label: "Outputs" };
}

async function loadWorkspace() {
  if (!activeSessionId) {
    workspaceFiles = [];
    renderWorkspace();
    return;
  }
  const sessionId = activeSessionId;
  const response = await fetch(`/workspace?session_id=${encodeURIComponent(sessionId)}`);
  if (!response.ok) {
    throw new Error(`Workspace load failed: HTTP ${response.status}`);
  }
  const payload = await response.json();
  if (sessionId !== activeSessionId) return;
  workspaceFiles = Array.isArray(payload.workspace?.files) ? payload.workspace.files : [];
  workspaceFiles.sort((left, right) => String(left.workspace_path || "").localeCompare(String(right.workspace_path || "")));
  renderWorkspace();
}

async function uploadSelectedFiles(files) {
  const selected = Array.from(files || []);
  if (!selected.length || isRunning || isSessionLoading) return;
  const sessionId = activeSessionId;
  const formData = new FormData();
  formData.append("session_id", sessionId);
  for (const file of selected) {
    formData.append("files", file, file.name);
  }

  uploadButton.disabled = true;
  uploadButton.textContent = "Uploading";
  try {
    const response = await fetch("/workspace/files", {
      method: "POST",
      body: formData,
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || `Upload failed: HTTP ${response.status}`);
    }
    if (sessionId === activeSessionId) {
      await loadWorkspace();
    }
  } catch (error) {
    if (sessionId === activeSessionId) addMessage("assistant", `Upload failed: ${error.message}`);
  } finally {
    uploadInput.value = "";
    uploadButton.disabled = isSessionLoading || isRunning;
    uploadButton.textContent = "Upload";
  }
}

async function deleteWorkspaceFile(workspacePath) {
  if (!workspacePath || isRunning || isSessionLoading) return;
  const response = await fetch(
    `/workspace/files/${encodeURIComponent(workspacePath)}?session_id=${encodeURIComponent(activeSessionId)}`,
    { method: "DELETE" },
  );
  const payload = await response.json();
  if (!response.ok || !payload.deleted) {
    throw new Error(payload.error || "File was not deleted.");
  }
  await loadWorkspace();
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
}

function renderThinkingPanel(payload = {}) {
  const runtime = payload.runtime || payload;
  thinkingLogLines = Array.isArray(runtime.logs) ? runtime.logs : thinkingLogLines;
}

function runtimeMeta(runtime = {}) {
  return [
    `Elapsed: ${formatElapsed(runtime.elapsed_seconds)}`,
    `Tools: ${compactList(runtime.tools)}`,
    `Files: ${runtime.file_count || 0}`,
  ];
}

function setThinkingDisplay(state, metaItems = [], payload = null) {
  if (payload) {
    renderThinkingPanel(payload);
  }
}

function resetThinkingBar() {
  thinkingLogLines = [];
}

function startThinking(request) {
  isRunning = true;
  setSendButtonState(true);
  sendButton.disabled = false;
  setComposerControlsDisabled(true);
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
          max_turns: Number(maxTurnsInput.value || config.default_max_turns || 5),
          logs: thinkingLogLines,
        },
        trace: [],
        evidence: {},
        status: "ok",
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
  setSendButtonState(false);
  sendButton.disabled = isSessionLoading;
  setComposerControlsDisabled(isSessionLoading);
  if (result?.session_id && result.session_id !== activeSessionId) {
    const session = currentSession();
    session.id = result.session_id;
    activeSessionId = result.session_id;
  }
  workspaceFiles = Array.isArray(result?.files) ? result.files : workspaceFiles;
  const runtime = result?.runtime || {};
  const status = runtime.status || result?.status || "ok";
  const state = status === "error" ? "error" : status === "blocked" ? "warning" : "done";
  setThinkingDisplay(state, runtimeMeta(runtime), result);
  loadWorkspace().catch((error) => console.warn("Failed to load workspace.", error));
}

function failThinking(error) {
  if (runtimeTimer) {
    clearInterval(runtimeTimer);
    runtimeTimer = null;
  }
  isRunning = false;
  setSendButtonState(false);
  sendButton.disabled = isSessionLoading;
  setComposerControlsDisabled(isSessionLoading);
  const runtime = error?.result?.runtime || {};
  setThinkingDisplay("error", runtimeMeta(runtime), error?.result || { runtime });
}

function stopThinking() {
  if (runtimeTimer) {
    clearInterval(runtimeTimer);
    runtimeTimer = null;
  }
  isRunning = false;
  setSendButtonState(false);
  sendButton.disabled = isSessionLoading;
  setComposerControlsDisabled(isSessionLoading);
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
      status: "ok",
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

function statusClass(result) {
  const status = result?.status || "ok";
  if (status === "error") return "error";
  if (status === "warning") return "warning";
  return "ok";
}

function resultSummaryTags(result) {
  const tags = [];
  const status = result?.status || "ok";
  tags.push(`<span class="tag ${statusClass(result)}">status: ${escapeHtml(status)}</span>`);
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
  for (const item of result?.files || []) {
    if (item?.kind === "structure" && item?.source_skill === "protein_structure_analysis") {
      addStructureArtifact(artifacts, seen, item?.path, item?.label || item?.source_skill);
    }
  }
  if (artifacts.length) return artifacts;

  const evidence = result?.evidence || {};
  for (const item of evidence.outputs || []) {
    if (item?.tool === "protein_structure_analysis") {
      addStructureArtifact(artifacts, seen, item?.structure_path, item?.pdb_id || item?.summary);
    }
  }
  for (const item of evidence.tool_outputs || []) {
    if (item?.tool === "protein_structure_analysis" && item?.tool === "protein_structure_analyze") {
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
  for (const item of result?.files || []) {
    if (item?.kind === "image") {
      addFigureArtifact(artifacts, seen, item?.path, item?.label || item?.source_skill);
    }
  }
  if (artifacts.length) return artifacts;

  const evidence = result?.evidence || {};
  for (const item of evidence.outputs || []) {
    addFigureArtifact(artifacts, seen, item?.image_path, item?.label || item?.summary || item?.tool);
    addFigureArtifact(artifacts, seen, item?.genome_map_path, item?.label || item?.summary || item?.tool);
  }
  for (const item of evidence.tool_outputs || []) {
    addFigureArtifact(artifacts, seen, item?.image_path, item?.label || item?.summary || item?.tool);
    addFigureArtifact(artifacts, seen, item?.genome_map_path, item?.label || item?.summary || item?.tool);
  }
  return artifacts;
}

function workspaceFileUrl(path, options = {}) {
  const file = workspaceFiles.find((item) => item.path === path || item.workspace_path === path);
  const params = new URLSearchParams({ path: String(file?.workspace_path || path || "") });
  if (activeSessionId) params.set("session_id", activeSessionId);
  if (options.viewer) {
    params.set("viewer", options.viewer);
  }
  return `/workspace/file?${params.toString()}`;
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
    const isPipeline = ["pipeline_shell"].includes(candidate?.tool) || ["pipeline_shell"].includes(candidate?.tool);
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
  for (const artifact of result?.files || []) {
    const path = String(artifact?.path || "").trim();
    if (
      !["pipeline_shell"].includes(artifact?.source_skill) ||
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
      if (["pipeline_shell"].includes(outputs[index]?.tool) && outputs[index]?.pipeline_name) {
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
    const url = workspaceFileUrl(record.path);
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
  const bundles = (result?.files || []).filter((artifact) => (
    artifact?.source_skill === "pipeline_shell" &&
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
          <a class="pipeline-download" href="${escapeHtml(workspaceFileUrl(artifact.path))}"
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
    const url = workspaceFileUrl(artifact.path);
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

function modelLabelForKey(modelKey) {
  const key = String(modelKey || "").trim();
  const model = (config.models || []).find((item) => item.key === key);
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
  const tone = status === "ok"
    ? "ok"
    : status === "pending_approval" || status === "stopped"
      ? "warning"
      : "error";
  return { status, label: labels[status] || status, tone };
}

function toolLabel(tool) {
  const labels = {
    database_lookup: "Database lookup",
    biology_analysis: "Transform sequence / GenBank",
    alphafold_download: "Download AlphaFold structure",
    biology_specialist: "Biology specialist",
    document_read: "Read document",
    file_inspection: "Inspect file",
    genome_map: "Create genome map",
    ncbi_retrieval: "Retrieve NCBI records",
    pdb_download: "Download PDB structure",
    pipeline_shell: "Run pipeline command",
    pipeline_specialist: "Pipeline specialist",
    protein_structure_analysis: "Analyze protein structure",
    sequence_analysis: "Analyze sequence",
    retrieval_specialist: "Retrieval specialist",
    species_report: "Write species report",
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

function traceEventTitle(event, result) {
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

function executionTimeline(result) {
  const trace = Array.isArray(result?.trace) ? result.trace : [];
  const explicitTools = new Set(
    trace.filter((event) => event?.event === "tool_started").map((event) => event?.data?.tool).filter(Boolean),
  );
  const visible = trace.filter((event) => {
    const name = event?.event;
    if (["sdk_span_finished", "sdk_trace_started", "sdk_trace_finished"].includes(name)) return false;
    if (["sdk_tool_started", "sdk_tool_finished"].includes(name) && explicitTools.has(event?.data?.tool)) return false;
    return true;
  });
  if (!visible.length) {
    return `<div class="run-empty">No execution events were returned by the runtime.</div>`;
  }
  return `<ol class="run-timeline">${visible.map((event, index) => {
    const detail = traceEventDetail(event, result);
    const tone = event.event === "run_failed" || event.event === "guardrail_blocked"
      ? "error"
      : event.event === "tool_finished" && evidenceOutputForTool(result, event.data?.tool)?.status === "error"
        ? "error"
        : event.event === "run_finished" || event.event === "agent_finished"
          ? "done"
          : "";
    return `
      <li class="run-step ${tone}">
        <span class="run-step-index">${index + 1}</span>
        <div class="run-step-body">
          <strong>${escapeHtml(traceEventTitle(event, result))}</strong>
          ${detail ? `<span>${escapeHtml(detail)}</span>` : ""}
        </div>
      </li>`;
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
    return `
      <div class="trace-row">
        <time>${escapeHtml(formatTraceTime(event?.timestamp))}</time>
        <code>${escapeHtml(event?.event || "event")}</code>
        <span>${escapeHtml(details || "No event details")}</span>
      </div>`;
  }).join("")}</div>`;
}

function formatTraceTime(timestamp) {
  if (!timestamp) return "—";
  const value = new Date(timestamp);
  if (Number.isNaN(value.getTime())) return String(timestamp);
  return value.toLocaleTimeString([], { hour12: false });
}

function runOutline(result) {
  const tools = [...new Set((result?.evidence?.tools || []).filter(Boolean).map(String))];
  const steps = [
    "Interpret the request and check the available session context.",
    tools.length
      ? `Run the selected operation${tools.length > 1 ? "s" : ""}: ${tools.map(toolLabel).join(", ")}.`
      : "Answer directly without a registered data operation.",
    "Check the returned status, evidence, and workspace files before composing the answer.",
  ];
  return `<ol class="run-outline">${steps.map((step) => `<li>${escapeHtml(step)}</li>`).join("")}</ol>`;
}

function evidenceList(title, values, renderItem = (value) => escapeHtml(value)) {
  if (!Array.isArray(values) || !values.length) return "";
  return `
    <section class="evidence-group">
      <h4>${escapeHtml(title)}</h4>
      <ul>${values.map((value) => `<li>${renderItem(value)}</li>`).join("")}</ul>
    </section>`;
}

function evidencePanel(result) {
  const evidence = result?.evidence || {};
  const citationItems = Array.isArray(evidence.citations) ? evidence.citations : [];
  const citations = citationItems.map((item) => {
    if (typeof item === "string") return escapeHtml(item);
    const title = item?.title || item?.name || item?.id || "Citation";
    const source = item?.source || item?.pmid || item?.year || "";
    const label = `${title}${source ? ` · ${source}` : ""}`;
    return item?.url
      ? `<a href="${escapeHtml(item.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(label)}</a>`
      : escapeHtml(label);
  });
  const files = (evidence.files || []).map((path) => {
    const value = String(path || "");
    return `<a href="${escapeHtml(workspaceFileUrl(value))}" title="${escapeHtml(value)}">${escapeHtml(fileNameFromPath(value))}</a>`;
  });
  const outputs = Array.isArray(evidence.outputs) ? evidence.outputs : [];
  const outputCards = outputs.map((item) => `
    <li><strong>${escapeHtml(toolLabel(item?.tool))}</strong><span>${escapeHtml(item?.summary || item?.status || "Result returned.")}</span></li>
  `).join("");
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
  return `${groups || `<div class="run-empty">No structured evidence was returned.</div>`}
    ${outputCards ? `<section class="evidence-group evidence-outputs"><h4>Tool results</h4><ul>${outputCards}</ul></section>` : ""}`;
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
  return `<div class="run-metrics">${metrics.map(([label, value]) => `
    <div class="run-metric"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>
  `).join("")}</div>`;
}

function resultDetails(result) {
  if (!result) return "";
  const runtime = result.runtime || {};
  const status = debugStatus(result);
  const pipelineOutputs = collectPipelineOutputRecords(result);
  return `
    ${pipelineDownloadsHtml(result, pipelineOutputs)}
    ${pipelineOutputs.length ? "" : collectedBundleHtml(result)}
    ${pipelineOutputs.length ? "" : figureArtifactsHtml(result)}
    ${pipelineOutputs.length ? "" : structureViewerHtml(result)}
    <div class="run-debug" aria-label="Runtime details">
      <div class="run-tabs" role="tablist" aria-label="Runtime detail sections">
        <button type="button" class="run-tab" role="tab" aria-selected="false" data-runtime-tab="runtime">
          <span>Runtime</span><small>${escapeHtml(status.label)} · ${escapeHtml(formatElapsed(runtime.elapsed_seconds))}</small>
        </button>
        <button type="button" class="run-tab" role="tab" aria-selected="false" data-runtime-tab="plan">
          <span>Plan &amp; execution</span><small>${(result.trace || []).length} events</small>
        </button>
        <button type="button" class="run-tab" role="tab" aria-selected="false" data-runtime-tab="evidence">
          <span>Evidence</span><small>${(result.evidence?.citations || []).length} sources</small>
        </button>
        <button type="button" class="run-tab" role="tab" aria-selected="false" data-runtime-tab="trace">
          <span>Trace</span><small>technical</small>
        </button>
      </div>
      <section class="run-panel" role="tabpanel" data-runtime-panel="runtime" hidden>
        ${runtimePanel(result, runtime, status)}
      </section>
      <section class="run-panel" role="tabpanel" data-runtime-panel="plan" hidden>
        <p class="run-debug-note">This shows the agent’s registered operations and runtime events, without exposing private model reasoning.</p>
        ${runOutline(result)}
        ${executionTimeline(result)}
      </section>
      <section class="run-panel" role="tabpanel" data-runtime-panel="evidence" hidden>
        <div class="evidence-panel">${evidencePanel(result)}</div>
      </section>
      <section class="run-panel" role="tabpanel" data-runtime-panel="trace" hidden>
        <div class="trace-technical">${technicalTrace(result)}</div>
      </section>
      <div class="approval-controls"></div>
    </div>
  `;
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
      panels.forEach((panel) => {
        panel.hidden = activeKey !== panel.dataset.runtimePanel;
      });
    };
    tabs.forEach((tab) => tab.addEventListener("click", () => select(tab.dataset.runtimeTab)));
    select(null);
  });
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
  const avatar = role === "assistant" ? BIOAGENT_ICON : "You";
  message.innerHTML = `
    <div class="avatar">${avatar}</div>
    <div class="bubble">
      <div class="bubble-text markdown-body">${renderMessageText(role, text)}</div>
      ${resultDetails(result)}
    </div>
  `;
  chat.appendChild(message);
  const approvalHost = message.querySelector(".approval-controls");
  if (approvalHost && window.mountToolApprovals) {
    window.mountToolApprovals(approvalHost, result, {
      url: "/approve",
      isBusy: () => isRunning || isSessionLoading,
      onBusy: (busy) => {
        isRunning = busy;
        sendButton.disabled = busy || isSessionLoading;
      },
      onResult: (next) => {
        finishThinking(next);
        addMessage("assistant", next.answer || "", next);
      },
    });
  }
  initializeRuntimeTabs(message);
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
    const response = await fetch(workspaceFileUrl(path, { viewer: "pdb" }));
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

function addMessage(role, text, result = null) {
  if (chat.querySelector(".empty-state")) {
    chat.innerHTML = "";
  }
  renderMessage(role, text, result);
  updateCurrentSession((session) => {
    if (role === "user" && session.messages.filter((message) => message.role === "user").length === 0) {
      session.title = titleFromText(text);
    }
    session.messages.push({
      role,
      text: String(text || ""),
      result,
      created_at: nowIso(),
    });
  });
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
    max_turns: Number(maxTurnsInput.value || config.default_max_turns || 5),
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
  if (isRunning || isSessionLoading) return;
  const text = promptInput.value.trim();
  if (!text) return;

  // On a phone, give the active request the full-height chat surface. The
  // navigation remains available through the expand button after sending.
  if (window.matchMedia("(max-width: 700px)").matches) {
    setSidebarCollapsed(true);
  }
  promptInput.value = "";
  resizeComposer();
  hideExampleParamPrompt();
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

function fillExamplePrompt(text) {
  promptInput.value = text;
  resizeComposer();
  promptInput.focus();
  promptInput.setSelectionRange(text.length, text.length);
}

function resizeComposer() {
  promptInput.style.height = "auto";
  const minimum = window.matchMedia("(max-width: 700px)").matches ? 64 : 82;
  const height = Math.min(Math.max(promptInput.scrollHeight, minimum), 180);
  promptInput.style.height = `${height}px`;
}

function formatParamOptionLabel(value) {
  if (value === "SARS_CoV_2") {
    return "SARS-CoV-2";
  }
  return value;
}

function hideExampleParamPrompt() {
  if (!exampleParamPrompt) {
    return;
  }
  exampleParamPrompt.hidden = true;
  exampleParamPromptLabel.textContent = "";
  exampleParamPromptOptions.innerHTML = "";
}

function showExampleParamPrompt({ label, paramName, options, template }) {
  if (!exampleParamPrompt) {
    return;
  }
  exampleParamPromptLabel.textContent = label;
  exampleParamPromptOptions.innerHTML = "";
  options.forEach((value) => {
    const optionButton = document.createElement("button");
    optionButton.type = "button";
    optionButton.className = "example-param-option";
    optionButton.textContent = formatParamOptionLabel(value);
    optionButton.addEventListener("click", () => {
      const text = template.replaceAll(`{${paramName}}`, value);
      hideExampleParamPrompt();
      fillExamplePrompt(text);
    });
    exampleParamPromptOptions.appendChild(optionButton);
  });
  exampleParamPrompt.hidden = false;
  promptInput.focus();
}

function bindExampleButtons(root = document) {
  root.querySelectorAll(".example-button").forEach((button) => {
    if (button.dataset.exampleBound === "1") {
      return;
    }
    button.dataset.exampleBound = "1";
    button.addEventListener("click", () => {
      const template = button.getAttribute("data-example-template");
      if (template) {
        const paramName = button.getAttribute("data-param-name") || "value";
        const label = button.getAttribute("data-param-label") || `Choose ${paramName}`;
        const options = String(button.getAttribute("data-param-options") || "")
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean);
        if (options.length) {
          showExampleParamPrompt({ label, paramName, options, template });
          return;
        }
      }
      hideExampleParamPrompt();
      fillExamplePrompt(button.getAttribute("data-example") || "");
    });
  });
}

function bindEvents() {
  composer.addEventListener("submit", submitPrompt);
  sendButton.addEventListener("click", (event) => {
    if (!isRunning) return;
    event.preventDefault();
    stopCurrentRequest();
  });
  promptInput.addEventListener("input", resizeComposer);
  promptInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      composer.requestSubmit();
    }
  });

  bindExampleButtons(document);
  if (exampleParamPromptDismiss) {
    exampleParamPromptDismiss.addEventListener("click", hideExampleParamPrompt);
  }
  toggleSidebarButton.addEventListener("click", () => {
    setSidebarCollapsed(!appShell.classList.contains("sidebar-collapsed"));
  });
  newChatButton.addEventListener("click", startNewChat);
  composerAttach.addEventListener("click", () => {
    if (!isRunning && !isSessionLoading) {
      uploadInput.click();
    }
  });
  uploadButton.addEventListener("click", () => {
    if (!isRunning) {
      uploadInput.click();
    }
  });
  workspaceRefresh.addEventListener("click", () => {
    loadWorkspace().catch((error) => addMessage("assistant", `Workspace refresh failed: ${error.message}`));
  });
  workspaceSearch.addEventListener("input", renderWorkspace);
  workspaceFilter.addEventListener("change", renderWorkspace);
  uploadInput.addEventListener("change", () => {
    uploadSelectedFiles(uploadInput.files);
  });
  workspaceDropzone.addEventListener("click", () => {
    if (!isRunning && !isSessionLoading) uploadInput.click();
  });
  workspaceDropzone.addEventListener("keydown", (event) => {
    if ((event.key === "Enter" || event.key === " ") && !isRunning && !isSessionLoading) {
      event.preventDefault();
      uploadInput.click();
    }
  });
  for (const eventName of ["dragenter", "dragover"]) {
    workspaceDropzone.addEventListener(eventName, (event) => {
      event.preventDefault();
      if (!isRunning && !isSessionLoading) workspaceDropzone.classList.add("dragging");
    });
  }
  for (const eventName of ["dragleave", "drop"]) {
    workspaceDropzone.addEventListener(eventName, (event) => {
      event.preventDefault();
      workspaceDropzone.classList.remove("dragging");
    });
  }
  workspaceDropzone.addEventListener("drop", (event) => {
    if (!isRunning && !isSessionLoading) uploadSelectedFiles(event.dataTransfer?.files);
  });
  uploadList.addEventListener("click", (event) => {
    const item = event.target.closest(".workspace-file");
    if (!item) return;
    if (event.target.closest("[data-workspace-delete]")) {
      deleteWorkspaceFile(item.dataset.workspacePath).catch((error) => {
        addMessage("assistant", `Remove file failed: ${error.message}`);
      });
    }
  });
  sessionList.addEventListener("click", (event) => {
    const item = event.target.closest(".session-item");
    if (!item) return;
    const sessionId = item.dataset.sessionId;
    if (event.target.closest("[data-session-menu]")) {
      openSessionMenu(item, event.target.closest("[data-session-menu]"));
      return;
    }
    if (event.target.closest("[data-session-pin]")) {
      closeSessionMenus();
      toggleSessionPin(sessionId);
      return;
    }
    if (event.target.closest("[data-session-rename]")) {
      closeSessionMenus();
      renameSessionById(sessionId);
      return;
    }
    if (event.target.closest("[data-session-delete]")) {
      closeSessionMenus();
      deleteSessionById(sessionId);
      return;
    }
    switchSession(sessionId);
  });
  document.addEventListener("click", (event) => {
    if (!event.target.closest(".session-item")) closeSessionMenus();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeSessionMenus();
  });
}

async function init() {
  initializeSidebar();
  setSessionLoading(true);
  try {
    await loadSessions();
  } catch (error) {
    console.warn("Failed to load sessions.", error);
    sessions = [createSession()];
    activeSessionId = sessions[0].id;
    rememberActiveSession();
  }
  bindEvents();
  renderSessionList();
  await loadActiveSession();
  try {
    await loadConfig();
  } catch (error) {
    addMessage("assistant", `Failed to load web configuration: ${error.message}`);
  }
}

init();
