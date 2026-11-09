import { useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { WebsiteSession } from '../../../../web_bridge/frontend/WebsiteProvider';
import { useWebsiteBridge } from '../../../../web_bridge/frontend/useWebsiteBridge';
import type { FormEvent, KeyboardEvent } from 'react';
import { createApiClient } from '../../api';
import type { AppConfig, Message, RunResult, StreamFrame, WorkspaceFile } from '../../types';
import { workspacePathOf } from '../../types';
import { MessageView } from '../messages/MessageView';
import { RunProgress } from '../messages/RunProgress';
import { useRunProgress } from '../messages/useRunProgress';
import { AgentIcon } from '../../components/icons';
import './assistant.css';

const contextLabels: Record<string, string> = { title: 'Page', url: 'URL', sample_name: 'Sample', program: 'Tab', project_id: 'Project', sample_id: 'Sample', result_type: 'Results' };
const emptyConfig: AppConfig = { default_model_key: '', default_max_turns: 5, models: [] };

function apiUrl(path: string) { return new URL(path, window.location.href).toString(); }

function modelLabel(model: { key: string; label?: string; cost_tier?: string }) {
  return `${model.label || model.key} (${model.cost_tier || 'Unknown cost'})`;
}

function fileLabel(file: WorkspaceFile) {
  const path = workspacePathOf(file);
  return file.name || path.split('/').pop() || path || 'File';
}
function workspaceFiles(value: unknown): WorkspaceFile[] { return Array.isArray(value) ? value.filter(item => item && typeof item === 'object') as WorkspaceFile[] : []; }

export function AssistantPage() {
  const websiteSession = useContext(WebsiteSession);
  const query = useMemo(() => new URLSearchParams(window.location.search), []);
  const embedded = query.get('embedded') === '1';
  const [sessionId, setSessionId] = useState('');
  const [config, setConfig] = useState<AppConfig>(emptyConfig);
  const [selectedModel, setSelectedModel] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const { entries: progressEntries, reset: resetProgress, onFrame: onProgressFrame, finish: finishProgress } = useRunProgress();
  const [prompt, setPrompt] = useState('');
  const [files, setFiles] = useState<WorkspaceFile[]>([]);
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [stopping, setStopping] = useState(false);
  const [status, setStatus] = useState('Connecting to assistant…');
  const [logs, setLogs] = useState<string[]>([]);
  const [configError, setConfigError] = useState('');
  const [uploading, setUploading] = useState(false);
  const [creatingChat, setCreatingChat] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const creatingChatRef = useRef(false);
  const sessionRef = useRef(sessionId);
  const api = useMemo(() => createApiClient(window.fetch.bind(window), new URL('./', window.location.href).href), []);

  useEffect(() => { sessionRef.current = sessionId; }, [sessionId]);

  const appendLog = useCallback((message: unknown) => {
    const line = String(message || '').trim();
    if (!line) return;
    setLogs(previous => [...previous, line].slice(-40));
  }, []);

  const refreshWebsiteFiles = useCallback(async () => {
    const value = await api.loadWorkspace(sessionRef.current);
    setFiles(workspaceFiles(value.workspace?.files));
  }, [api]);
  const { context, websiteRef, websiteError, setWebsiteError, websiteRequired,
    postParent, newConversation, disconnect, notifyRunComplete } = useWebsiteBridge({
    sessionRef, onLog: appendLog, onStatus: setStatus, onFilesChanged: refreshWebsiteFiles,
  });

  const appendCompletedRun = useCallback((result: RunResult) => {
    const answer = String(result.answer || 'No answer returned.');
    const activity = finishProgress(answer);
    setMessages(previous => [...previous, { role: 'assistant', text: answer, result, progress: activity, created_at: new Date().toISOString() }]);
    setActiveRunId(null); setStopping(false);
    notifyRunComplete({ ...result, answer });
  }, [finishProgress, notifyRunComplete]);

  const receiveProgress = useCallback((frame: StreamFrame) => {
    if (frame.payload.run_id && ['run_status', 'queued', 'cancelling'].includes(frame.event)) setActiveRunId(String(frame.payload.run_id));
    if (frame.event === 'cancelling' || frame.payload.status === 'cancelling') { setStopping(true); setStatus('Stopping…'); }
    onProgressFrame(frame);
  }, [onProgressFrame]);

  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();
    (async () => {
      try {
        const loaded = await api.loadConfig();
        const created = websiteSession ? { session_id: websiteSession } : await api.createSession();
        if (cancelled) return;
        sessionRef.current = created.session_id; setSessionId(created.session_id);
        postParent({ type: 'agent-ready', session_id: created.session_id });
        const [history, workspace] = await Promise.all([api.loadMessages(created.session_id, true), api.loadWorkspace(created.session_id)]);
        if (cancelled) return;
        const restored = [...(history.messages || [])];
        if (history.pending_approval && !history.active_run) restored.push({ role: 'assistant', text: String(history.pending_approval.answer || ''), result: history.pending_approval });
        setMessages(restored); setFiles(workspaceFiles(workspace.workspace?.files));
        setConfig(loaded); setSelectedModel(loaded.default_model_key || loaded.models[0]?.key || ''); setReady(true); setConfigError(''); setStatus(websiteRef.current ? 'Connected to website' : 'Ready');
        if (history.active_run?.run_id) {
          setBusy(true); setActiveRunId(history.active_run.run_id); abortRef.current = controller;
          try { appendCompletedRun(await api.watchRun(history.active_run.run_id, controller.signal, receiveProgress)); await refreshWebsiteFiles().catch(error => appendLog(`File refresh failed: ${String(error)}`)); }
          finally { if (!cancelled) { setBusy(false); abortRef.current = null; } }
        }
      } catch (error) {
        if (!cancelled) { setConfigError(error instanceof Error ? error.message : String(error)); setStatus('Could not connect to assistant.'); }
      }
    })();
    return () => { cancelled = true; controller.abort(); abortRef.current?.abort(); };
  }, [api, postParent, websiteSession, appendCompletedRun, receiveProgress, refreshWebsiteFiles, appendLog]);

  const submit = useCallback(async (event?: FormEvent) => {
    event?.preventDefault();
    const text = prompt.trim();
    if (!text || busy || !ready || (websiteRequired && !websiteRef.current)) return;
    setPrompt(''); resetProgress(); setMessages(previous => [...previous, { role: 'user', text, created_at: new Date().toISOString() }]);
    setLogs([]); setBusy(true); setStopping(false); setActiveRunId(null); setStatus('Working on your request…'); setWebsiteError('');
    const controller = new AbortController(); abortRef.current = controller;
    try {
      const runOptions = {
        sessionId: sessionRef.current, modelKey: selectedModel || config.default_model_key || config.models[0]?.key || '', maxTurns: Math.max(1, Number(config.default_max_turns || 5)), signal: controller.signal,
        website: websiteRef.current ? { binding_id: websiteRef.current.binding_id, token: websiteRef.current.token } : undefined,
        onFrame: (frame: StreamFrame) => {
          if (frame.event === 'log' || frame.event === 'status') appendLog(frame.payload.message);
          receiveProgress(frame);
        },
      };
      const result = await api.run(text, runOptions);
      setSessionId(String(result.session_id || sessionRef.current));
      appendCompletedRun(result);
      await refreshWebsiteFiles().catch(error => appendLog(`File refresh failed: ${String(error)}`));
      setStatus('Ready');
    } catch (error) {
      const stopped = (error as Error).name === 'AbortError';
      const text = stopped ? 'Stopped waiting. Work already started on the server may continue.' : `Request failed: ${error instanceof Error ? error.message : String(error)}`;
      const activity = finishProgress();
      setMessages(previous => [...previous, { role: 'assistant', text, progress: activity, created_at: new Date().toISOString() }]);
      setStatus(stopped ? text : 'Request failed. You can try again.');
    } finally { abortRef.current = null; setBusy(false); }
  }, [api, appendCompletedRun, appendLog, busy, config, finishProgress, receiveProgress, prompt, ready, resetProgress, selectedModel, websiteRequired, refreshWebsiteFiles]);

  const stop = async () => {
    if (!activeRunId || stopping) return;
    setStopping(true); setStatus('Stopping…');
    try { await api.cancelRun(activeRunId); }
    catch (error) { setStopping(false); setStatus(`Could not confirm Stop: ${(error as Error).message}`); }
  };

  const upload = useCallback(async (list: FileList | null) => {
    if (!list?.length || busy || uploading) return;
    setUploading(true); setStatus('Uploading files…');
    try { const result = await api.uploadFiles(sessionRef.current, Array.from(list)); setSessionId(String(result.session_id || sessionRef.current)); setFiles(previous => [...previous, ...workspaceFiles(result.files)]); setStatus('Files attached.'); }
    catch (error) { setStatus(`Upload failed: ${error instanceof Error ? error.message : String(error)}`); }
    finally {
      try { const payload = await api.loadWorkspace(sessionRef.current); setFiles(workspaceFiles(payload.workspace?.files)); } catch { /* Keep the upload error and retry on refresh. */ }
      setUploading(false);
    }
  }, [api, busy, uploading]);

  const newChat = useCallback(async () => {
    if (busy || creatingChatRef.current || (!messages.length && !files.length)) return;
    creatingChatRef.current = true;
    setCreatingChat(true);
    let next: string;
    try { next = websiteSession && websiteRef.current ? await newConversation() : (await api.createSession()).session_id; }
    catch (error) { setStatus(`Could not create chat: ${(error as Error).message}`); creatingChatRef.current = false; setCreatingChat(false); return; }
    disconnect(); sessionRef.current = next; resetProgress(); setSessionId(next); setMessages([]); setFiles([]); setLogs([]); setPrompt(''); setStatus(ready ? 'Ready' : 'Connecting to assistant…');
    postParent({ type: 'agent-ready', session_id: next });
    creatingChatRef.current = false;
    setCreatingChat(false);
  }, [api, busy, postParent, ready, resetProgress, newConversation, disconnect, websiteSession, messages.length, files.length]);

  useEffect(() => { const onKey = (event: globalThis.KeyboardEvent) => { if (event.key === 'Escape' && window.parent !== window) postParent({ type: 'agent-close' }); }; window.addEventListener('keydown', onKey); return () => window.removeEventListener('keydown', onKey); }, [postParent]);

  const contextChips = Object.entries({ ...(typeof context.selection === 'object' && context.selection ? context.selection : {}), ...context }).filter(([key, value]) => contextLabels[key] && typeof value === 'string' && value.trim()).map(([key, value]) => <span className="assistant-context-chip" key={key} title={`${contextLabels[key]}: ${String(value)}`}>{contextLabels[key]}: {String(value).trim().slice(0, 200)}</span>);
  const onPromptKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => { if (event.key === 'Enter' && !event.shiftKey && !(event.nativeEvent as globalThis.KeyboardEvent).isComposing) { event.preventDefault(); void submit(); } };
  const fileLinks = (result: RunResult | null | undefined) => workspaceFiles(result?.artifacts ?? result?.files).map(file => { const path = workspacePathOf(file); return path ? <a key={path} href={`${apiUrl('workspace/file')}?path=${encodeURIComponent(path)}&session_id=${encodeURIComponent(sessionId)}`} target="_blank" rel="noopener noreferrer">{fileLabel(file)}</a> : null; });

  return <main className={`assistant-page ${embedded ? 'assistant-embedded' : ''}`} aria-label="Assistant">
    {!embedded && <header className="assistant-header"><div className="assistant-brand"><AssistantLogo /><div><strong>Assistant</strong><small>Your analysis companion</small></div></div><button id="newChat" className="assistant-text-button" type="button" onClick={newChat} disabled={busy || creatingChat}>New chat</button></header>}
    {embedded && <button id="newChat" className="assistant-text-button" type="button" onClick={newChat} disabled={busy || creatingChat}>New chat</button>}
    {contextChips.length > 0 && <div id="contextSummary" className="assistant-context-summary" aria-label="Current workspace context">{contextChips}</div>}
    <section id="messages" className="assistant-messages" role="log" aria-live="polite">
      {!messages.length && !busy && <div className="assistant-welcome"><AssistantLogo large /><h1>How can I help?</h1><p>Ask about your results or attach a file to get started.</p><button id="welcomePrompt" className="assistant-suggestion" type="button" onClick={() => setPrompt('Help me understand a results table.')}>Help me understand a results table</button></div>}
      {messages.map((message, index) => <div className="assistant-message-shell" key={`${message.created_at || 'message'}-${index}`}><MessageView showDetails={!embedded} message={message} config={config} sessionId={sessionId} busy={busy} onProgress={receiveProgress} onApproval={(next, meta) => { if (!meta?.intermediate) { appendCompletedRun(next); setFiles(workspaceFiles(next.workspace_files ?? next.files)); } }} onBusy={value => { if (value) resetProgress(); setBusy(value); }} />{fileLinks(message.result)}</div>)}
      {busy && <RunProgress entries={progressEntries} running />}
    </section>
    <div className="assistant-progress"><span id="status" role="status">{status}</span>{configError && <button id="retryConfig" type="button" className="assistant-text-button" onClick={() => window.location.reload()}>Retry connection</button>}{websiteError && <button id="retryWebsite" type="button" className="assistant-text-button" onClick={() => window.location.reload()}>Retry website connection</button>}<details id="progressDetails" hidden={!logs.length}><summary>Logs</summary><pre id="progressLog">{logs.join('\n')}</pre></details></div>
    <form id="composer" className="assistant-composer" onSubmit={submit}><ul id="uploadList" className="assistant-file-list" hidden={!files.length}>{files.map(file => <li key={workspacePathOf(file)}><a href={`${apiUrl('workspace/file')}?path=${encodeURIComponent(workspacePathOf(file))}&session_id=${encodeURIComponent(sessionId)}`} download title={`Download ${fileLabel(file)}`}>{fileLabel(file)}</a></li>)}</ul><label className="assistant-sr-only" htmlFor="prompt">Message assistant</label><textarea id="prompt" rows={2} value={prompt} onChange={event => setPrompt(event.target.value)} onKeyDown={onPromptKeyDown} disabled={busy || creatingChat} placeholder="Ask assistant…" /><div className="assistant-model-row"><label htmlFor="model">Model</label><select id="model" disabled={busy || creatingChat || !ready} value={selectedModel} onChange={event => setSelectedModel(event.target.value)}>{config.models.map(model => <option key={model.key} value={model.key}>{modelLabel(model)}</option>)}</select></div><div className="assistant-actions"><label className="assistant-attach"><input id="uploadInput" type="file" multiple hidden onChange={event => upload(event.target.files)} />Attach</label><button id="stop" type="button" className="assistant-stop" hidden={!busy} disabled={!activeRunId || stopping} onClick={stop}>{stopping ? 'Stopping…' : 'Stop'}</button><button id="send" type="submit" className="assistant-send" disabled={busy || creatingChat || !ready || (websiteRequired && !websiteRef.current)}>{busy ? 'Working…' : <>Send <span aria-hidden="true">↑</span></>}</button></div></form>
  </main>;
}

function AssistantLogo({ large = false }: { large?: boolean }) {
  return <span className={`assistant-logo ${large ? 'large' : ''}`} aria-hidden="true"><AgentIcon size={large ? 50 : 34} /></span>;
}

export default AssistantPage;
