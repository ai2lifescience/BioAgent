import { createApiClient } from "/static/api-client.js";
import { createSessionState } from "/static/session-state.js";
import { createSessionSidebar } from "/static/session-sidebar.js";
import { createWorkspacePanel } from "/static/workspace-panel.js";
import { createArtifactViewers } from "/static/artifact-viewers.js";
import { createMessageRenderer } from "/static/message-renderer.js";
import {
  compactList,
  escapeHtml,
  formatElapsed,
  nowIso,
  titleFromText,
} from "/static/ui-utils.js";

let config = {
  default_model_key: "",
  default_max_turns: 5,
  models: [],
  pipelines: [],
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

const SIDEBAR_COLLAPSED_KEY = "agent.web.sidebar_collapsed.v3";
let structureSuffixes = [".cif", ".mmcif", ".pdb"];
// Keep the renderer useful while /config is loading or unavailable. The server
// may later narrow/extend this list, but common image artifacts should render
// from saved conversation results on the first page load as well.
let imageSuffixes = [".gif", ".jpeg", ".jpg", ".png", ".svg", ".webp"];

let runtimeTimer = null;
let runtimeStartedAt = 0;
let activeAbortController = null;
let requestStopped = false;
let isRunning = false;
let isSessionLoading = false;
let thinkingLogLines = [];
let workspacePanel;

const api = createApiClient();
const sessionStore = createSessionState({ api });

const SEND_ICON = `
  <svg width="17" height="17" viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <path d="M5 12h14M13 6l6 6-6 6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
  </svg>`;
const PAUSE_ICON = `
  <svg width="17" height="17" viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <rect x="7" y="6" width="3.5" height="12" rx="1" fill="currentColor"/>
    <rect x="13.5" y="6" width="3.5" height="12" rx="1" fill="currentColor"/>
  </svg>`;
const AGENT_ICON = `
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

const artifactViewers = createArtifactViewers({
  getStructureSuffixes: () => structureSuffixes,
  getImageSuffixes: () => imageSuffixes,
  workspaceFileUrl: (path, options) => workspacePanel.fileUrl(path, options),
});
const sessionSidebar = createSessionSidebar({ sessionList, sessionCount, sessionStore });
workspacePanel = createWorkspacePanel({
  elements: {
    count: workspaceCount,
    summary: workspaceSummary,
    list: uploadList,
    search: workspaceSearch,
    filter: workspaceFilter,
    uploadButton,
    uploadInput,
    composerFileHint,
  },
  api,
  getSessionId: () => sessionStore.activeSessionId,
  isBusy: () => isRunning || isSessionLoading,
  onError: (message) => addMessage("assistant", message),
});

const messageRenderer = createMessageRenderer({
  chat,
  agentIcon: AGENT_ICON,
  artifactViewers,
  workspaceFileUrl: (path, options) => workspacePanel.fileUrl(path, options),
  getConfig: () => config,
  formatModelLabel,
  getRunning: () => isRunning,
  getSessionLoading: () => isSessionLoading,
  onApprovalBusy: (busy) => {
    isRunning = busy;
    sendButton.disabled = busy || isSessionLoading;
  },
  onApprovalResult: (next, meta = {}) => {
    finishThinking(next);
    if (!meta.intermediate) addMessage("assistant", next.answer || "", next);
  },
});

// Keep the empty state useful while /config is loading or when the UI is
// served by an older backend that does not expose the pipeline catalog yet.
const PIPELINE_FALLBACKS = [
  { name: "antimicrobial_resistance_detection", display_name: "Antimicrobial resistance detection" },
  { name: "bacterial_functional_annotation", display_name: "Bacterial functional annotation" },
  { name: "bacterial_genome_annotation", display_name: "Bacterial genome annotation" },
  { name: "bacterial_genome_mutation_analysis", display_name: "Bacterial genome mutation analysis" },
  { name: "bacterial_read_variant_analysis", display_name: "Bacterial read variant analysis" },
  { name: "bacterial_virulence_factor_detection", display_name: "Bacterial virulence-factor detection" },
  { name: "metagenomic_de_novo_assembly", display_name: "Metagenomic de novo assembly" },
  { name: "metagenomic_pathogen_identification", display_name: "Metagenomic pathogen identification" },
  { name: "metagenomic_read_quality_control", display_name: "Metagenomic read quality control" },
  {
    name: "pathogen_variant_risk_assessment",
    display_name: "Pathogen variant risk assessment",
    parameters: { pathogen: { required: true, choices: ["H1N1", "H3N2", "SARS_CoV_2"] } },
  },
  { name: "rna_secondary_structure_prediction", display_name: "RNA secondary-structure prediction" },
  { name: "template_bio", display_name: "DNA analysis template" },
  { name: "template_nextflow", display_name: "Nextflow pipeline template" },
  { name: "template_shell", display_name: "Shell metadata assignment template" },
  { name: "template_snakemake", display_name: "Snakemake pipeline template" },
  { name: "template_wdl", display_name: "WDL pipeline template" },
  { name: "viral_genome_mutation_analysis", display_name: "Viral genome mutation analysis" },
  { name: "viral_molecular_typing", display_name: "Viral molecular typing" },
];

const PIPELINE_PARAMETER_CHOICES = {
  viral_molecular_typing: {
    name: "pathogen",
    label: "Choose pathogen for Molecular Typing",
    options: ["H1N1", "H3N2", "SARS_CoV_2"],
  },
  pathogen_variant_risk_assessment: {
    name: "pathogen",
    label: "Choose pathogen for Risk Assessment",
    options: ["H1N1", "H3N2", "SARS_CoV_2"],
  },
};

async function loadConfig() {
  config = await api.loadConfig();
  applyArtifactConfig(config.files || {});
  renderModelOptions();
  renderPipelineExamples();
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

function pipelineCatalogForExamples() {
  const catalog = Array.isArray(config.pipelines) && config.pipelines.length
    ? config.pipelines
    : PIPELINE_FALLBACKS;
  return catalog.filter((entry) => entry && entry.name && !entry.error);
}

function pipelineExampleButtonHtml(entry) {
  const name = String(entry.name);
  const label = String(entry.display_name || name);
  const override = PIPELINE_PARAMETER_CHOICES[name];
  let parameterName = override?.name || "";
  let options = override?.options || [];

  if (!options.length) {
    for (const [candidateName, spec] of Object.entries(entry.parameters || {})) {
      if (spec && spec.required && Array.isArray(spec.choices) && spec.choices.length) {
        parameterName = candidateName;
        options = spec.choices;
        break;
      }
    }
  }

  if (parameterName && options.length) {
    const template = `Run pipeline with pipeline_name: ${name} ${parameterName}: {${parameterName}}`;
    const parameterLabel = override?.label || `Choose ${label} ${parameterName}`;
    return `<button class="example-button" data-example-template="${escapeHtml(template)}" data-param-name="${escapeHtml(parameterName)}" data-param-label="${escapeHtml(parameterLabel)}" data-param-options="${escapeHtml(options.join(","))}">${escapeHtml(label)}</button>`;
  }

  return `<button class="example-button" data-example="Run pipeline with pipeline_name: ${escapeHtml(name)}">${escapeHtml(label)}</button>`;
}

function pipelineExamplesHtml() {
  return pipelineCatalogForExamples().map(pipelineExampleButtonHtml).join("");
}

function renderPipelineExamples(root = document) {
  root.querySelectorAll(".more-examples .examples").forEach((container) => {
    container.innerHTML = pipelineExamplesHtml();
  });
  bindExampleButtons(root);
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
          <details class="more-examples" open>
            <summary>More pipelines</summary>
            <div class="examples">
              ${pipelineExamplesHtml()}
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
            <li><span>2</span><div><strong>Work</strong><small>Pipeline2Agent selects tools and inspects your files.</small></div></li>
            <li><span>3</span><div><strong>Review</strong><small>Approve pipelines and download verified outputs.</small></div></li>
          </ol>
        </section>
      </div>
    </div>
  `;
}

function renderCurrentChat() {
  artifactViewers.disposeGenomeViewers(chat);
  chat.innerHTML = "";
  const messages = sessionStore.currentSession().messages || [];
  if (!messages.length) {
    chat.innerHTML = emptyStateHtml();
    bindExampleButtons(chat);
    return;
  }
  for (const message of messages) {
    messageRenderer.renderMessage(message.role, message.text || "", message.result || null);
  }
  scrollBottom();
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
  workspacePanel.setFiles([]);
  artifactViewers.disposeGenomeViewers(chat);
  chat.textContent = "Loading conversation…";
  try {
    await Promise.all([sessionStore.loadConversation(sessionStore.activeSessionId), loadWorkspace()]);
    renderCurrentChat();
    sessionSidebar.render();
    resetThinkingBar();
  } catch (error) {
    renderCurrentChat();
    messageRenderer.renderMessage("assistant", `Could not load this chat: ${error.message}`);
  } finally {
    setSessionLoading(false);
  }
}

async function switchSession(sessionId) {
  if (isRunning || isSessionLoading || !sessionId || sessionId === sessionStore.activeSessionId) return;
  sessionStore.activeSessionId = sessionId;
  sessionStore.rememberActiveSession();
  sessionSidebar.render();
  await loadActiveSession();
  promptInput.focus();
}

async function deleteSessionById(sessionId) {
  if (isRunning || isSessionLoading || !sessionId) return;
  setSessionLoading(true);
  try {
    await api.deleteSession(sessionId);
    sessionStore.sessions = sessionStore.sessions.filter((session) => session.id !== sessionId);
    if (!sessionStore.sessions.length) sessionStore.sessions = [sessionStore.createSession()];
    if (!sessionStore.sessions.some((session) => session.id === sessionStore.activeSessionId)) sessionStore.activeSessionId = sessionStore.sessions[0].id;
    sessionStore.rememberActiveSession();
    sessionSidebar.render();
    await loadActiveSession();
  } catch (error) {
    messageRenderer.renderMessage("assistant", `Could not delete this chat: ${error.message}`);
  } finally {
    setSessionLoading(false);
  }
}

async function updateSessionById(sessionId, changes) {
  if (isRunning || isSessionLoading || !sessionId) return;
  const session = sessionStore.sessions.find((item) => item.id === sessionId);
  if (!session) return;
  setSessionLoading(true);
  try {
    const payload = await api.updateSession(sessionId, changes);
    if (Object.prototype.hasOwnProperty.call(changes, "title")) session.title = String(payload.title || "New chat");
    if (Object.prototype.hasOwnProperty.call(changes, "pinned")) session.pinned = Boolean(payload.pinned);
    session.updated_at = payload.updated_at || nowIso();
    sessionSidebar.render();
  } catch (error) {
    messageRenderer.renderMessage("assistant", `Could not update this chat: ${error.message}`);
  } finally {
    setSessionLoading(false);
  }
}

async function renameSessionById(sessionId) {
  const session = sessionStore.sessions.find((item) => item.id === sessionId);
  if (!session || isRunning || isSessionLoading) return;
  const title = window.prompt("Rename chat", session.title || "New chat");
  if (title === null) return;
  const cleaned = title.replace(/\s+/g, " ").trim().slice(0, 80);
  if (!cleaned || cleaned === session.title) return;
  await updateSessionById(sessionId, { title: cleaned });
}

async function toggleSessionPin(sessionId) {
  const session = sessionStore.sessions.find((item) => item.id === sessionId);
  if (!session) return;
  await updateSessionById(sessionId, { pinned: !session.pinned });
}

function startNewChat() {
  if (isRunning || isSessionLoading) return;
  const session = sessionStore.createSession();
  sessionStore.sessions.unshift(session);
  sessionStore.activeSessionId = session.id;
  sessionStore.rememberActiveSession();
  sessionSidebar.render();
  workspacePanel.setFiles([]);
  renderCurrentChat();
  workspacePanel.load().catch((error) => console.warn("Failed to load workspace.", error));
  resetThinkingBar();
  hideExampleParamPrompt();
  promptInput.focus();
}

function loadWorkspace() {
  return workspacePanel.load();
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
          session_id: sessionStore.activeSessionId,
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
  if (result?.job_id) {
    sessionStore.currentSession().last_run_id = String(result.job_id);
  }
  if (result?.session_id && result.session_id !== sessionStore.activeSessionId) {
    const session = sessionStore.currentSession();
    session.id = result.session_id;
    sessionStore.activeSessionId = result.session_id;
  }
  if (Array.isArray(result?.workspace_files)) workspacePanel.setFiles(result.workspace_files);
  else if (Array.isArray(result?.files)) workspacePanel.setFiles(result.files);
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
        session_id: sessionStore.activeSessionId,
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

function addMessage(role, text, result = null) {
  if (chat.querySelector(".empty-state")) {
    artifactViewers.disposeGenomeViewers(chat);
    chat.innerHTML = "";
  }
  messageRenderer.renderMessage(role, text, result);
  sessionStore.updateCurrentSession((session) => {
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
  sessionSidebar.render();
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
  return api.run(request, {
    sessionId: sessionStore.activeSessionId,
    modelKey: modelSelect.value,
    maxTurns: Number(maxTurnsInput.value || config.default_max_turns || 5),
    signal,
    onFrame: handleStreamFrame,
  });
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
  workspaceSearch.addEventListener("input", () => workspacePanel.render());
  workspaceFilter.addEventListener("change", () => workspacePanel.render());
  uploadInput.addEventListener("change", () => {
    workspacePanel.uploadSelectedFiles(uploadInput.files);
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
    if (!isRunning && !isSessionLoading) workspacePanel.uploadSelectedFiles(event.dataTransfer?.files);
  });
  uploadList.addEventListener("click", (event) => {
    const item = event.target.closest(".workspace-file");
    if (!item) return;
    if (event.target.closest("[data-workspace-delete]")) {
      workspacePanel.deleteFile(item.dataset.workspacePath).catch((error) => {
        addMessage("assistant", `Remove file failed: ${error.message}`);
      });
    }
  });
  sessionList.addEventListener("click", (event) => {
    const item = event.target.closest(".session-item");
    if (!item) return;
    const sessionId = item.dataset.sessionId;
    if (event.target.closest("[data-session-menu]")) {
      sessionSidebar.openMenu(item, event.target.closest("[data-session-menu]"));
      return;
    }
    if (event.target.closest("[data-session-pin]")) {
      sessionSidebar.closeMenus();
      toggleSessionPin(sessionId);
      return;
    }
    if (event.target.closest("[data-session-rename]")) {
      sessionSidebar.closeMenus();
      renameSessionById(sessionId);
      return;
    }
    if (event.target.closest("[data-session-delete]")) {
      sessionSidebar.closeMenus();
      deleteSessionById(sessionId);
      return;
    }
    switchSession(sessionId);
  });
  document.addEventListener("click", (event) => {
    if (!event.target.closest(".session-item")) sessionSidebar.closeMenus();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") sessionSidebar.closeMenus();
  });
}

async function init() {
  initializeSidebar();
  setSessionLoading(true);
  try {
    await sessionStore.loadSessions();
  } catch (error) {
    console.warn("Failed to load sessions.", error);
    sessionStore.sessions = [sessionStore.createSession()];
    sessionStore.activeSessionId = sessionStore.sessions[0].id;
    sessionStore.rememberActiveSession();
  }
  bindEvents();
  sessionSidebar.render();
  try {
    await loadConfig();
  } catch (error) {
    addMessage("assistant", `Failed to load web configuration: ${error.message}`);
  }
  // Load configuration before rendering saved messages so artifact viewers
  // know about image formats when a page is refreshed.
  await loadActiveSession();
}

init();
