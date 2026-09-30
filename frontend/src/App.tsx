import { useCallback, useEffect, useRef, useState } from 'react';
import { createApiClient } from './api';
import type { AppConfig, Message, Pipeline, SessionSummary, StreamFrame, WorkspaceFile } from './types';
import { sessionIdOf, workspacePathOf } from './types';
import './styles.css';
import { SessionSidebar as FeatureSessionSidebar } from './features/sessions/SessionSidebar';
import { WorkspacePanel as FeatureWorkspacePanel } from './features/workspace/WorkspacePanel';
import { Composer as FeatureComposer } from './features/chat/Composer';
import { MessageView } from './features/messages';
import { RunProgress } from './features/messages/RunProgress';
import { useRunProgress } from './features/messages/useRunProgress';
import { LineIcon } from './components/icons';

const api = createApiClient();
const ACTIVE_SESSION_KEY = 'agent.web.active_session_id.v1';
const SIDEBAR_KEY = 'agent.web.sidebar_collapsed.v3';

const fallbackPipelines: Pipeline[] = [
  ['antimicrobial_resistance_detection', 'Antimicrobial resistance detection'],
  ['bacterial_functional_annotation', 'Bacterial functional annotation'],
  ['bacterial_genome_annotation', 'Bacterial genome annotation'],
  ['bacterial_genome_mutation_analysis', 'Bacterial genome mutation analysis'],
  ['bacterial_read_variant_analysis', 'Bacterial read variant analysis'],
  ['bacterial_virulence_factor_detection', 'Bacterial virulence-factor detection'],
  ['metagenomic_de_novo_assembly', 'Metagenomic de novo assembly'],
  ['metagenomic_pathogen_identification', 'Metagenomic pathogen identification'],
  ['metagenomic_read_quality_control', 'Metagenomic read quality control'],
  ['rna_secondary_structure_prediction', 'RNA secondary-structure prediction'],
  ['template_bio', 'DNA analysis template'], ['template_nextflow', 'Nextflow pipeline template'],
  ['template_shell', 'Shell metadata assignment template'], ['template_snakemake', 'Snakemake pipeline template'],
  ['template_wdl', 'WDL pipeline template'], ['viral_genome_mutation_analysis', 'Viral genome mutation analysis'],
  ['viral_molecular_typing', 'Viral molecular typing'],
].map(([name, display_name]) => ({ name, display_name }));

const quickStarts = [
  ['NCBI genome map', 'Use ncbi_retrieval to download NCBI accession NC_001422.1 as a FASTA file.\nThen use the downloaded FASTA to find ORFs and render an interactive genome map.\nReturn the downloaded path, map path, and reference path.'],
  ['PDB structure viewer', 'Download PDB structure 1A3N as mmCIF, inspect its chains and ligands, and show the interactive 3D structure viewer.'],
  ['Metagenomic read quality control', 'Run the Metagenomic read quality control pipeline (pipeline_name: metagenomic_read_quality_control). Use any parameter values from my request and ask me for missing required values before executing.'],
  ['Knowledge ingest and retrieve', [
    'Build and query a durable knowledge collection using only `knowledge_ingest`, `knowledge_status`, and `knowledge_retrieve`.',
    '### 1. Ingest',
    'Create a new session-owned collection with these parameters:\n- `seed_urls`: ["https://rest.uniprot.org/uniprotkb/P0A7V8.txt"]\n- `allowed_domains`: ["rest.uniprot.org"]\n- `max_pages`: 1\n- `max_depth`: 0',
    'Poll `knowledge_status` until terminal. Report `job_id`, `collection_id`, status, fetched/indexed/chunks, skipped URLs, and errors. Proceed only if status is `succeeded`, indexed > 0, and chunks > 0; otherwise explain the reported failure or empty result and stop.',
    '### 2. Retrieve',
    'Use the returned `collection_id` in this same session. Call `knowledge_retrieve` twice with `top_k=8` and these exact question values:\n1. `FUNCTION`\n2. `InterPro`',
    'This collection contains only P0A7V8, so do not add other words to either query. Do not ingest again or use web/database tools.',
    '### 3. Present the evidence',
    '- Summarize the protein functions.\n- Show a two-column table of InterPro IDs and entry names exactly as recorded.\n- Put identifiers and entry names in inline code to preserve underscores; do not infer family/domain/site classifications.\n- Include source URLs, supporting chunk IDs, brief excerpts, and every `evidence_path`.\n- Explicitly identify anything unsupported by the retrieved evidence.',
  ].join('\n\n')],
  ['Plot synthetic data', 'Create and display a polished plot using only synthetic data generated inside the code.\nDo not depend on uploaded files, workspace data, databases, APIs, or internet access.\nGenerate the sample data programmatically, execute the code, save the plot as a PNG in the workspace, verify that it exists, show it directly in the chat, and return the exact path with a brief explanation.'],
  ['Research and report', [
    'Research the reliability of AI agents for scientific research, focusing on citation accuracy, reproducibility, and human oversight. Complete all steps below in this turn.',
    '### 1. Search and collect',
    'Use pubmed_search and web_search to find 6–8 relevant, distinct sources. Prefer primary research and official institutional publications. Record the search date and queries.',
    'Fetch PubMed records/abstracts and relevant web pages using the available tools, including web_fetch. Preserve source identifiers, URLs, publication dates, and actual returned workspace evidence paths.',
    'Distinguish abstracts from full-text sources. Report inaccessible sources and insufficient evidence. Distinguish evaluations of AI agents from studies of standalone language models.',
    '### 2. Retrieve and review',
    'Use evidence_retrieve with the actual returned evidence paths to select supporting excerpts.',
    'Before synthesis, use report_review to assess each source’s:\n- Study type and methods\n- Evaluation setting and sample\n- Main results\n- Uncertainty and limitations',
    'Compare conflicting findings and distinguish empirical evidence from opinion or guidance. Do not invent citations, paths, or numerical results.',
    '### 3. Synthesize and save',
    'Use report_synthesize, then report_write, to save a cited Markdown report containing:',
    '- Title and executive summary\n- Research question and search methods\n- Main findings with citations\n- Evidence comparison table: source, study type, setting/sample, results, and limitations\n- Conflicting evidence and uncertainty\n- Overall limitations and evidence gaps\n- Conclusion\n- References with PMID, DOI, or URL where available\n- Source-to-evidence mapping with exact workspace paths',
    '### 4. Read back and display',
    'After saving, use file_inspection to read the actual report_path returned by report_write.',
    'Display the saved report’s substantive contents directly in this chat, including its title, section headings, main findings with citations, evidence comparison table, uncertainty, limitations, evidence gaps, conclusion, references, and source evidence paths.',
    'Base this display on the saved file. Do not run new searches or regenerate the report after saving. If reading is truncated, read the remaining content when possible; otherwise explicitly disclose what could not be read. If verification fails, report the failure rather than claiming the file was verified.',
    'Use readable Markdown headings, lists, and tables. Show the report once, without raw tool JSON or duplicated summaries.',
    'End with:\n- Exact saved report_path\n- Number of distinct sources reviewed\n- Exact evidence artifact paths',
    'Do not return only a file path or download link.',
  ].join('\n\n')],
];
function nowIso() { return new Date().toISOString(); }
function newSession(): SessionSummary { const date = nowIso(); return { id: `web-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`, title: 'New chat', message_count: 0, created_at: date, updated_at: date, messages: [] }; }
function titleFromText(text: string) { return text.trim().replace(/\s+/g, ' ').slice(0, 48) || 'New chat'; }
function workspaceFiles(value: unknown): WorkspaceFile[] { return Array.isArray(value) ? value.filter(item => item && typeof item === 'object') as WorkspaceFile[] : []; }
function useIsMobile() {
  const [mobile, setMobile] = useState(() => window.matchMedia('(max-width: 700px)').matches);
  useEffect(() => {
    const query = window.matchMedia('(max-width: 700px)');
    const update = () => setMobile(query.matches);
    update();
    query.addEventListener?.('change', update);
    return () => query.removeEventListener?.('change', update);
  }, []);
  return mobile;
}
function Icon() { return <LineIcon name="chevron" />; }

function QuickStarts({ pipelines, onChoose }: { pipelines: Pipeline[]; onChoose: (text: string) => void }) {
  const pipelinePrompt = (entry: Pipeline) => {
    const label = entry.display_name || entry.name;
    return `Run the ${label} pipeline (pipeline_name: ${entry.name}). Use any parameter values from my request and ask me for missing required values before executing.`;
  };
  return <div className="empty-state"><div className="empty-intro"><span className="empty-kicker">A focused workspace for biology</span><h1>What are you working on?</h1><p>Ask a question, upload data, or run a reproducible pipeline. Results and files stay together in this chat.</p></div><div className="onboarding-card"><div className="section-heading"><div><span className="eyebrow">Quick starts</span><span className="section-note">Choose a starting point</span></div><span className="section-count">{pipelines.length} pipelines</span></div><div className="quick-grid">{quickStarts.map(([label, prompt]) => <button key={label} onClick={() => onChoose(prompt)}>{label}</button>)}</div><details open className="pipeline-list"><summary>More pipelines <span>Explore reproducible workflows</span></summary><div className="pipeline-grid">{pipelines.map(entry => <button key={entry.name} onClick={() => onChoose(pipelinePrompt(entry))}>{entry.display_name || entry.name}</button>)}</div></details></div><div className="workflow-card"><div className="section-heading"><div><span className="eyebrow">Simple workflow</span><span className="section-note">From question to result</span></div></div><ol><li><span>1</span><div><strong>Ask</strong><small>Describe the biology task in plain language.</small></div></li><li><span>2</span><div><strong>Work</strong><small>Pipeline2Agent selects tools and inspects your files.</small></div></li><li><span>3</span><div><strong>Review</strong><small>Approve pipelines and download verified outputs.</small></div></li></ol></div></div>;
}

export default function App() {
  const [config, setConfig] = useState<AppConfig>({ default_model_key: '', default_max_turns: 20, models: [], pipelines: fallbackPipelines });
  const [sessions, setSessions] = useState<SessionSummary[]>([]); const [activeId, setActiveId] = useState(''); const [messages, setMessages] = useState<Message[]>([]); const [files, setFiles] = useState<WorkspaceFile[]>([]);
  // Keep the empty-state onboarding tied to a fully loaded conversation. When
  // activeId changes, the previous messages stay in memory but are not rendered
  // for the new session until both history and workspace data have arrived.
  // This prevents a transient welcome screen flashing between conversations.
  const [loadedConversationId, setLoadedConversationId] = useState<string | null>(null);
  const progress = useRunProgress();
  const [prompt, setPrompt] = useState(''); const [selectedModel, setSelectedModel] = useState(''); const [turns, setTurns] = useState(20); const [running, setRunning] = useState(false); const [uploading, setUploading] = useState(false); const [workspaceOpen, setWorkspaceOpen] = useState(false); const [loading, setLoading] = useState(true); const [sidebarCollapsed, setSidebarCollapsed] = useState(() => localStorage.getItem(SIDEBAR_KEY) === 'true'); const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false); const [workspaceSearch, setWorkspaceSearch] = useState(''); const [workspaceFilter, setWorkspaceFilter] = useState('all'); const [error, setError] = useState('');
  const isMobile = useIsMobile();
  const navigationCollapsed = isMobile ? !mobileSidebarOpen : sidebarCollapsed;
  const abortRef = useRef<AbortController | null>(null); const modelRef = useRef(''); const turnsRef = useRef(20); const inputRef = useRef<HTMLInputElement>(null);
  const pipelines = config.pipelines?.length ? config.pipelines : fallbackPipelines;
  const toggleNavigation = () => {
    if (isMobile) { setMobileSidebarOpen(open => !open); return; }
    const next = !sidebarCollapsed;
    setSidebarCollapsed(next);
    localStorage.setItem(SIDEBAR_KEY, String(next));
  };
  // Mobile navigation is temporary; it must never overwrite the desktop preference.
  useEffect(() => { setMobileSidebarOpen(false); }, [isMobile]);
  const loadWorkspace = useCallback(async (id: string) => { try { const payload = await api.loadWorkspace(id); if (id === activeId) setFiles(workspaceFiles(payload.workspace?.files)); } catch { /* workspace is optional */ } }, [activeId]);

  useEffect(() => { let cancelled = false; (async () => { let cfg: AppConfig | null = null; let sessionPayload: { sessions?: any[] } = {}; try { cfg = await api.loadConfig(); if (!cancelled) { setConfig({ ...cfg, pipelines: cfg.pipelines?.length ? cfg.pipelines : fallbackPipelines }); setSelectedModel(cfg.default_model_key || cfg.models?.[0]?.key || ''); setTurns(cfg.default_max_turns || 20); modelRef.current = cfg.default_model_key; turnsRef.current = cfg.default_max_turns || 20; } } catch (e) { if (!cancelled) setError(`Configuration unavailable: ${(e as Error).message}`); } try { sessionPayload = await api.listSessions(); } catch (e) { if (!cancelled) setError(`Could not load conversations: ${(e as Error).message}`); } if (cancelled) return; const loaded = (sessionPayload.sessions || []).map((raw: any) => ({ id: sessionIdOf(raw), title: String(raw.title || 'New chat'), message_count: Number(raw.message_count || 0), last_run_id: raw.last_run_id, created_at: raw.created_at || nowIso(), updated_at: raw.updated_at || raw.created_at || nowIso(), pinned: Boolean(raw.pinned), messages: [] } as SessionSummary)).filter(item => item.id); const next = loaded.length ? loaded : [newSession()]; const stored = localStorage.getItem(ACTIVE_SESSION_KEY); const id = next.some(item => item.id === stored) ? stored! : next[0].id; setSessions(next); setActiveId(id); if (!cfg) { modelRef.current = ''; turnsRef.current = 20; } if (!cancelled) setLoading(false); })(); return () => { cancelled = true; abortRef.current?.abort(); }; }, []);
  useEffect(() => {
    if (!activeId) return;
    localStorage.setItem(ACTIVE_SESSION_KEY, activeId);
    let cancelled = false;
    (async () => {
      try {
        const [messagesPayload, workspacePayload] = await Promise.all([api.loadMessages(activeId), api.loadWorkspace(activeId)]);
        if (cancelled) return;
        const next = messagesPayload.messages || [];
        if (messagesPayload.pending_approval) next.push({ role: 'assistant', text: String(messagesPayload.pending_approval.answer || ''), result: messagesPayload.pending_approval });
        setMessages(next);
        setFiles(workspaceFiles(workspacePayload.workspace?.files));
        setLoadedConversationId(activeId);
      } catch (e) {
        if (cancelled) return;
        setError(`Could not load this chat: ${(e as Error).message}`);
        setMessages([]);
        setFiles([]);
        // Render the empty state after an error rather than leaving a stale
        // conversation-loading view indefinitely.
        setLoadedConversationId(activeId);
      }
    })();
    return () => { cancelled = true; };
  }, [activeId]);
  const addMessage = (message: Message) => { setMessages(prev => [...prev, message]); setSessions(prev => prev.map(s => s.id === activeId ? { ...s, title: s.message_count ? s.title : titleFromText(message.text), message_count: (s.message_count || 0) + 1, updated_at: nowIso() } : s)); };
  const appendRunResult = (result: any, fallback: string) => {
    const answer = String(result?.answer || fallback || '');
    const activity = progress.finish(answer);
    setMessages(previous => [...previous, { role: 'assistant', text: answer, result: result || {}, progress: activity, created_at: nowIso() }]);
    // The sidebar count tracks request/response exchanges. A streamed run can
    // contain several assistant turns before its final answer, but it is still
    // one exchange in the persisted session metadata.
    setSessions(previous => previous.map(s => s.id === activeId ? { ...s, message_count: (s.message_count || 0) + 1, updated_at: nowIso() } : s));
  };
  const submit = async () => {
    const text = prompt.trim();
    if (!text || running || !activeId) return;
    setMobileSidebarOpen(false); setPrompt(''); progress.reset(); addMessage({ role: 'user', text, created_at: nowIso() });
    setRunning(true); setError(''); abortRef.current = new AbortController(); let logCount = 0;
    try {
      const result = await api.run(text, { sessionId: activeId, modelKey: modelRef.current || config.default_model_key, maxTurns: turnsRef.current || config.default_max_turns, signal: abortRef.current.signal, onFrame: (frame: StreamFrame) => {
        if (frame.event === 'log' || frame.event === 'status') logCount += 1;
        progress.onFrame(frame);
      } });
      setFiles(workspaceFiles(result?.workspace_files ?? result?.files ?? files));
      appendRunResult(result, logCount ? 'The run completed. See the execution details below.' : 'The run completed.');
    } catch (e) {
      const stopped = (e as Error).name === 'AbortError';
      const text = stopped ? 'Stopped waiting. Work already started on the server may continue.' : `Request failed: ${(e as Error).message}`;
      if (!stopped) setError(text);
      addMessage({ role: 'assistant', text, progress: progress.finish(), created_at: nowIso() });
    } finally { abortRef.current = null; setRunning(false); }
  };
  const choose = (text: string) => { setPrompt(text); };
  const selectSession = (id: string) => { if (!running && id !== activeId) { setActiveId(id); setFiles([]); } };
  const newChat = () => { if (running) return; const session = newSession(); progress.reset(); setSessions(prev => [session, ...prev]); setActiveId(session.id); setMessages([]); setFiles([]); setLoadedConversationId(session.id); setPrompt(''); setError(''); };
  const rename = async (id: string, requestedTitle?: string) => { const session = sessions.find(s => s.id === id); if (!session) return; const value = requestedTitle ?? window.prompt('Rename chat', session.title); const title = value?.replace(/\s+/g, ' ').trim().slice(0, 80); if (!title || title === session.title) return; try { await api.updateSession(id, { title }); setSessions(prev => prev.map(s => s.id === id ? { ...s, title, updated_at: nowIso() } : s)); } catch (e) { setError(`Could not rename this chat: ${(e as Error).message}`); } };
  const pin = async (id: string) => { const session = sessions.find(s => s.id === id); if (!session) return; try { await api.updateSession(id, { pinned: !session.pinned }); setSessions(prev => prev.map(s => s.id === id ? { ...s, pinned: !s.pinned } : s)); } catch { /* preserve local interaction if server is unavailable */ } };
  const remove = async (id: string) => { if (sessions.length <= 1 || running) return; await api.deleteSession(id); const remaining = sessions.filter(s => s.id !== id); setSessions(remaining); if (id === activeId) setActiveId(remaining[0].id); };
  const upload = async (selected: FileList | File[] | null) => { if (!selected || !selected.length || running || uploading || !activeId) return; setUploading(true); try { const payload = await api.uploadFiles(activeId, Array.from(selected)); setFiles(workspaceFiles(payload.files ?? payload.workspace?.files)); } catch (e) { setError(`Upload failed: ${(e as Error).message}`); } finally { setUploading(false); } };
  const deleteFile = async (path: string) => { try { const payload = await api.deleteWorkspaceFile(activeId, path); if (!payload?.deleted) throw new Error(payload?.error || 'File was not deleted.'); setFiles(prev => prev.filter(file => workspacePathOf(file) !== path)); } catch (e) { setError(`Remove file failed: ${(e as Error).message}`); throw e; } };
  (window as any).__activeSession = activeId;
  const conversationReady = loadedConversationId === activeId;
  const hasVisibleMessages = messages.length || running;
  return <div className={`app-shell ${navigationCollapsed ? 'sidebar-collapsed' : ''}`}><FeatureSessionSidebar sessions={sessions} activeId={activeId} collapsed={navigationCollapsed} mobileOpen={isMobile && mobileSidebarOpen} disabled={running || loading || !conversationReady} onToggle={toggleNavigation} onMobileClose={() => setMobileSidebarOpen(false)} onSelect={selectSession} onNew={newChat} onRename={async (id, title) => rename(id, title)} onPin={async (id, pinned) => pin(id)} onDelete={remove} /><main className="main-column"><div className="mobile-actions"><button className="mobile-menu-button" onClick={() => setMobileSidebarOpen(true)} aria-expanded={mobileSidebarOpen} aria-label="Open navigation"><Icon /></button><button className="mobile-workspace-button" onClick={() => setWorkspaceOpen(true)} aria-label="Open workspace">Workspace</button></div><div className="chat-scroll"><div id="chat" className="chat-content">{error && <div className="error-banner" role="status">{error}<button onClick={() => setError('')}>Dismiss</button></div>}{loading ? <div className="loading-state"><span className="spinner" /> Loading workspace…</div> : !conversationReady ? <div className="conversation-loading" role="status" aria-live="polite"><span className="spinner" /><div><strong>Loading conversation</strong><span>Restoring messages and workspace files…</span></div></div> : hasVisibleMessages ? <>{messages.map((message, i) => <MessageView key={`${message.created_at || i}-${i}`} message={message} config={config} sessionId={activeId} busy={running} onBusy={setRunning} onApproval={(next, meta) => { if (meta?.intermediate) { setMessages(previous => previous.map((item, index) => index === i ? { ...item, text: String(next.answer || item.text), result: next } : item)); return; } setMessages(previous => [...previous, { role: 'assistant', text: String(next.answer || 'The approved operation completed.'), result: next, created_at: nowIso() }]); }} />)}</> : <QuickStarts pipelines={pipelines} onChoose={choose} />}{running && <RunProgress entries={progress.entries} running />}</div></div><FeatureComposer models={config.models || []} prompt={prompt} onPromptChange={setPrompt} fileCount={files.length} running={running} disabled={loading || !conversationReady} model={selectedModel || config.default_model_key} turns={turns} onModelChange={value => { setSelectedModel(value); modelRef.current = value; }} onTurnsChange={value => { setTurns(value); turnsRef.current = value; }} onSubmit={submit} onStop={() => abortRef.current?.abort()} onAttach={() => inputRef.current?.click()} /></main><FeatureWorkspacePanel sessionId={activeId} files={files} search={workspaceSearch} filter={workspaceFilter} busy={running || loading || !conversationReady} uploading={uploading} mobileOpen={workspaceOpen} onClose={() => setWorkspaceOpen(false)} onSearch={setWorkspaceSearch} onFilter={setWorkspaceFilter} onUpload={upload} onRefresh={() => loadWorkspace(activeId)} onDelete={deleteFile} /><input ref={inputRef} hidden type="file" multiple onChange={e => upload(e.target.files)} /></div>;
}
