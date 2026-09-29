import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { FormEvent, KeyboardEvent } from 'react';
import { createApiClient } from '../../api';
import type { AppConfig, Message, RunResult, StreamFrame, WorkspaceFile } from '../../types';
import { workspacePathOf } from '../../types';
import { MessageView } from '../messages/MessageView';
import { AgentIcon } from '../../components/icons';
import './assistant.css';

type WebsiteBinding = { binding_id: string; token: string; session_id: string; site_id?: string };
type WebsiteRequest = { call_id: string; run_id?: string; method?: string; arguments?: Record<string, unknown>; revision?: string; deadline?: number; session_id?: string };
type AssistantContext = Record<string, unknown>;

const contextLabels: Record<string, string> = { project_id: 'Project', sample_id: 'Sample', result_type: 'Results' };
const emptyConfig: AppConfig = { default_model_key: '', default_max_turns: 5, models: [] };

function createSessionId() {
  const random = globalThis.crypto?.randomUUID?.();
  if (random) return `assistant_${random.replaceAll('-', '')}`;
  const bytes = new Uint8Array(16);
  globalThis.crypto?.getRandomValues(bytes);
  return `assistant_${Array.from(bytes, (value) => value.toString(16).padStart(2, '0')).join('')}`;
}

function parentOriginFromQuery() {
  try {
    const raw = new URLSearchParams(window.location.search).get('parent_origin') || window.location.origin;
    const origin = new URL(raw, window.location.origin);
    return origin.protocol === 'http:' || origin.protocol === 'https:' ? origin.origin : window.location.origin;
  } catch { return window.location.origin; }
}

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
  const query = useMemo(() => new URLSearchParams(window.location.search), []);
  const parentOrigin = useMemo(parentOriginFromQuery, []);
  const embedded = query.get('embedded') === '1';
  const websiteRequired = Boolean(query.get('website_site'));
  const [sessionId, setSessionId] = useState(createSessionId);
  const [config, setConfig] = useState<AppConfig>(emptyConfig);
  const [selectedModel, setSelectedModel] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [streamingMessages, setStreamingMessages] = useState<Message[]>([]);
  const [streamingDraft, setStreamingDraft] = useState('');
  const [prompt, setPrompt] = useState('');
  const [files, setFiles] = useState<WorkspaceFile[]>([]);
  const [context, setContext] = useState<AssistantContext>(() => {
    const initial: AssistantContext = {};
    for (const key of Object.keys(contextLabels)) {
      const value = query.get(key);
      if (value) initial[key] = value;
    }
    return initial;
  });
  const [website, setWebsite] = useState<WebsiteBinding | null>(null);
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState('Connecting to assistant…');
  const [logs, setLogs] = useState<string[]>([]);
  const [configError, setConfigError] = useState('');
  const [websiteError, setWebsiteError] = useState('');
  const [uploading, setUploading] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const websitePollRef = useRef(false);
  const streamingMessagesRef = useRef<Message[]>([]);
  const streamingDraftRef = useRef('');
  const websiteQueueRef = useRef(Promise.resolve());
  const websiteRef = useRef<WebsiteBinding | null>(null);
  const sessionRef = useRef(sessionId);
  const contextRef = useRef(context);
  const parentRef = useRef(parentOrigin);
  const api = useMemo(() => createApiClient(window.fetch.bind(window), new URL('./', window.location.href).href), []);

  useEffect(() => { websiteRef.current = website; }, [website]);
  useEffect(() => { sessionRef.current = sessionId; }, [sessionId]);
  useEffect(() => { contextRef.current = context; }, [context]);

  const appendLog = useCallback((message: unknown) => {
    const line = String(message || '').trim();
    if (!line) return;
    setLogs(previous => [...previous, line].slice(-40));
  }, []);

  const resetStreaming = useCallback(() => {
    streamingMessagesRef.current = [];
    streamingDraftRef.current = '';
    setStreamingMessages([]);
    setStreamingDraft('');
  }, []);

  const appendStreamDelta = useCallback((delta: unknown) => {
    const value = String(delta || '');
    if (!value) return;
    streamingDraftRef.current += value;
    setStreamingDraft(streamingDraftRef.current);
  }, []);

  const finishStreamedResponse = useCallback(() => {
    const text = streamingDraftRef.current;
    if (text.trim()) {
      const next = [...streamingMessagesRef.current, { role: 'assistant' as const, text, created_at: new Date().toISOString() }];
      streamingMessagesRef.current = next;
      setStreamingMessages(next);
    }
    streamingDraftRef.current = '';
    setStreamingDraft('');
  }, []);

  const appendCompletedRun = useCallback((result: RunResult) => {
    const streamed = [...streamingMessagesRef.current];
    if (streamingDraftRef.current.trim()) streamed.push({ role: 'assistant', text: streamingDraftRef.current, created_at: new Date().toISOString() });
    const answer = String(result.answer || 'No answer returned.');
    const last = streamed[streamed.length - 1];
    const incoming = last?.role === 'assistant' && last.text.trim() === answer.trim()
      ? streamed.map((item, index) => index === streamed.length - 1 ? { ...item, result } : item)
      : [...streamed, { role: 'assistant' as const, text: answer, result, created_at: new Date().toISOString() }];
    resetStreaming();
    setMessages(previous => [...previous, ...incoming]);
  }, [resetStreaming]);

  const websitePost = useCallback(async <T,>(path: string, body: unknown): Promise<T> => {
    const response = await fetch(apiUrl(path), {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(String((payload as { error?: unknown })?.error || `Website bridge HTTP ${response.status}`));
    return payload as T;
  }, []);

  const postParent = useCallback((message: Record<string, unknown>) => {
    if (window.parent !== window) window.parent.postMessage(message, parentRef.current);
  }, []);

  const setSafeContext = useCallback((value: unknown) => {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return;
    try {
      if (JSON.stringify(value).length > 64 * 1024) throw new Error('Website context is too large');
      setContext({ ...(value as AssistantContext) });
    } catch (error) { appendLog(error instanceof Error ? error.message : 'Website context is invalid.'); }
  }, [appendLog]);

  const queueContextUpdate = useCallback((nextContext: AssistantContext, contextUpdateId = '') => {
    const binding = websiteRef.current;
    if (!binding && !contextUpdateId) return;
    const task = websiteQueueRef.current.then(async () => {
      try {
        if (binding) await websitePost('website/context', { ...binding, context: nextContext });
        if (contextUpdateId) postParent({ type: 'agent-context-updated', session_id: sessionRef.current, context_update_id: contextUpdateId, revision: String(nextContext.revision || ''), ok: true });
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        appendLog(`Website context update failed: ${message}`);
        if (contextUpdateId) postParent({ type: 'agent-context-updated', session_id: sessionRef.current, context_update_id: contextUpdateId, revision: String(nextContext.revision || ''), ok: false, error: message });
      }
    });
    websiteQueueRef.current = task.catch(() => undefined);
  }, [appendLog, postParent, websitePost]);

  const pollWebsite = useCallback(async () => {
    if (websitePollRef.current) return;
    websitePollRef.current = true;
    try {
      while (websiteRef.current) {
        const binding = websiteRef.current;
        const payload = await websitePost<{ requests?: WebsiteRequest[] }>('website/poll', binding);
        if (binding !== websiteRef.current) continue;
        for (const request of payload.requests || []) {
          postParent({ type: 'agent-website-request', ...request, session_id: binding.session_id });
        }
        await new Promise(resolve => window.setTimeout(resolve, 250));
      }
    } catch (error) {
      if (websiteRef.current) appendLog(`Website bridge disconnected: ${error instanceof Error ? error.message : String(error)}`);
    } finally { websitePollRef.current = false; }
  }, [appendLog, postParent, websitePost]);

  const connectWebsite = useCallback(async (message: { ticket?: string; site_id?: string; instance_id?: string; capabilities?: string[]; session_id?: string }) => {
    if (message.session_id && message.session_id !== sessionRef.current) return;
    try {
      const binding = await websitePost<WebsiteBinding>('website/connect', {
        ticket: message.ticket, site_id: message.site_id, origin: parentRef.current,
        instance_id: message.instance_id, session_id: sessionRef.current,
        capabilities: message.capabilities || [], context: contextRef.current,
      });
      const next = { ...binding, site_id: message.site_id };
      websiteRef.current = next;
      setWebsite(next);
      setWebsiteError('');
      setStatus('Connected to website');
      postParent({ type: 'agent-website-connected', session_id: sessionRef.current, binding_id: next.binding_id });
      void pollWebsite();
    } catch (error) {
      const messageText = error instanceof Error ? error.message : String(error);
      setWebsiteError(messageText); setStatus(`Website connection failed: ${messageText}`); appendLog(`Website bridge unavailable: ${messageText}`);
      postParent({ type: 'agent-event', event: { type: 'website-error', message: messageText } });
    }
  }, [appendLog, pollWebsite, postParent, websitePost]);

  useEffect(() => {
    const onMessage = (event: MessageEvent) => {
      if (window.parent === window || event.source !== window.parent || event.origin !== parentRef.current) return;
      const data = event.data as Record<string, unknown> | null;
      if (!data || typeof data !== 'object') return;
      if (data.type === 'agent-context') {
        setSafeContext(data.context);
        queueContextUpdate((data.context && typeof data.context === 'object' ? data.context : {}) as AssistantContext, String(data.context_update_id || ''));
      } else if (data.type === 'agent-connect') {
        void connectWebsite(data as { ticket?: string; site_id?: string; instance_id?: string; capabilities?: string[]; session_id?: string });
      } else if (data.type === 'agent-website-response') {
        if (!websiteRef.current || data.session_id !== sessionRef.current || !data.call_id) return;
        void websitePost('website/respond', { ...websiteRef.current, call_id: data.call_id, run_id: data.run_id, revision: data.revision, result: data.result, error: data.error }).catch(error => appendLog(`Website response failed: ${error instanceof Error ? error.message : String(error)}`));
      } else if (data.type === 'agent-website-error') {
        const text = String(data.message || 'Website connection failed.'); setWebsiteError(text); setStatus(text); appendLog(text);
      } else if (data.type === 'agent-disconnect') {
        const binding = websiteRef.current; websiteRef.current = null; setWebsite(null); if (binding) void websitePost('website/disconnect', binding).catch(() => undefined);
      }
    };
    window.addEventListener('message', onMessage);
    postParent({ type: 'agent-ready', session_id: sessionRef.current });
    return () => window.removeEventListener('message', onMessage);
  }, [appendLog, connectWebsite, postParent, queueContextUpdate, setSafeContext, websitePost]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const loaded = await api.loadConfig();
        if (cancelled) return;
        setConfig(loaded); setSelectedModel(loaded.default_model_key || loaded.models[0]?.key || ''); setReady(true); setConfigError(''); setStatus(websiteRef.current ? 'Connected to website' : 'Ready');
      } catch (error) {
        if (!cancelled) { setConfigError(error instanceof Error ? error.message : String(error)); setStatus('Could not connect to assistant.'); }
      }
    })();
    return () => { cancelled = true; abortRef.current?.abort(); };
  }, [api]);

  const submit = useCallback(async (event?: FormEvent) => {
    event?.preventDefault();
    const text = prompt.trim();
    if (!text || busy || !ready || (websiteRequired && !websiteRef.current)) return;
    setPrompt(''); resetStreaming(); setMessages(previous => [...previous, { role: 'user', text, created_at: new Date().toISOString() }]);
    setLogs([]); setBusy(true); setStatus('Working on your request…'); setWebsiteError('');
    const controller = new AbortController(); abortRef.current = controller;
    try {
      const runOptions = {
        sessionId: sessionRef.current, modelKey: selectedModel || config.default_model_key || config.models[0]?.key || '', maxTurns: Math.max(1, Number(config.default_max_turns || 5)), signal: controller.signal,
        website: websiteRef.current ? { binding_id: websiteRef.current.binding_id, token: websiteRef.current.token } : undefined,
        onFrame: (frame: StreamFrame) => {
          if (frame.event === 'log' || frame.event === 'status') appendLog(frame.payload.message);
          if (frame.event === 'sdk_raw_response') {
            if (frame.payload.data_type === 'response.output_text.delta') appendStreamDelta(frame.payload.delta);
            else if (frame.payload.data_type === 'response.output_text.done') finishStreamedResponse();
          }
        },
      };
      const result = await api.run(text, runOptions);
      setSessionId(String(result.session_id || sessionRef.current));
      appendCompletedRun(result);
      setStatus('Ready');
    } catch (error) {
      const partial = [...streamingMessagesRef.current];
      if (streamingDraftRef.current.trim()) partial.push({ role: 'assistant', text: streamingDraftRef.current, created_at: new Date().toISOString() });
      resetStreaming();
      if (partial.length) setMessages(previous => [...previous, ...partial]);
      if ((error as Error).name !== 'AbortError') { const messageText = error instanceof Error ? error.message : String(error); setMessages(previous => [...previous, { role: 'assistant', text: messageText, created_at: new Date().toISOString() }]); setStatus('Request failed. You can try again.'); }
      else setStatus('Stopped waiting. Work already started on the server may continue.');
    } finally { abortRef.current = null; setBusy(false); }
  }, [api, appendCompletedRun, appendLog, appendStreamDelta, busy, config, finishStreamedResponse, prompt, ready, resetStreaming, selectedModel, websiteRequired]);

  const upload = useCallback(async (list: FileList | null) => {
    if (!list?.length || busy || uploading) return;
    setUploading(true); setStatus('Uploading files…');
    try { const result = await api.uploadFiles(sessionRef.current, Array.from(list)); setSessionId(String(result.session_id || sessionRef.current)); setFiles(previous => [...previous, ...workspaceFiles(result.files)]); setStatus('Files attached.'); }
    catch (error) { setStatus(`Upload failed: ${error instanceof Error ? error.message : String(error)}`); }
    finally { setUploading(false); }
  }, [api, busy, uploading]);

  const newChat = useCallback(() => {
    if (busy) return;
    const binding = websiteRef.current; if (binding) void websitePost('website/disconnect', binding).catch(() => undefined);
    websiteRef.current = null; setWebsite(null); const next = createSessionId(); resetStreaming(); setSessionId(next); setMessages([]); setFiles([]); setLogs([]); setPrompt(''); setStatus(ready ? 'Ready' : 'Connecting to assistant…');
    postParent({ type: 'agent-ready', session_id: next });
  }, [busy, postParent, ready, resetStreaming, websitePost]);

  useEffect(() => { const onKey = (event: globalThis.KeyboardEvent) => { if (event.key === 'Escape' && window.parent !== window) postParent({ type: 'agent-close' }); }; window.addEventListener('keydown', onKey); return () => window.removeEventListener('keydown', onKey); }, [postParent]);

  const contextChips = Object.entries(context).filter(([key, value]) => contextLabels[key] && typeof value === 'string' && value.trim()).map(([key, value]) => <span className="assistant-context-chip" key={key} title={`${contextLabels[key]}: ${String(value)}`}>{contextLabels[key]}: {String(value).trim().slice(0, 200)}</span>);
  const onPromptKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => { if (event.key === 'Enter' && !event.shiftKey && !(event.nativeEvent as globalThis.KeyboardEvent).isComposing) { event.preventDefault(); void submit(); } };
  const fileLinks = (result: RunResult | null | undefined) => workspaceFiles(result?.artifacts ?? result?.files).map(file => { const path = workspacePathOf(file); return path ? <a key={path} href={`${apiUrl('workspace/file')}?path=${encodeURIComponent(path)}&session_id=${encodeURIComponent(sessionId)}`} target="_blank" rel="noopener noreferrer">{fileLabel(file)}</a> : null; });

  return <main className={`assistant-page ${embedded ? 'assistant-embedded' : ''}`} aria-label="Assistant">
    {!embedded && <header className="assistant-header"><div className="assistant-brand"><AssistantLogo /><div><strong>Assistant</strong><small>Your analysis companion</small></div></div><button id="newChat" className="assistant-text-button" type="button" onClick={newChat} disabled={busy}>New chat</button></header>}
    {contextChips.length > 0 && <div id="contextSummary" className="assistant-context-summary" aria-label="Current workspace context">{contextChips}</div>}
    <section id="messages" className="assistant-messages" role="log" aria-live="polite">
      {!messages.length && !streamingMessages.length && !streamingDraft && <div className="assistant-welcome"><AssistantLogo large /><h1>How can I help?</h1><p>Ask about your results or attach a file to get started.</p><button id="welcomePrompt" className="assistant-suggestion" type="button" onClick={() => setPrompt('Help me understand a results table.')}>Help me understand a results table</button></div>}
      {messages.map((message, index) => <div className="assistant-message-shell" key={`${message.created_at || 'message'}-${index}`}><MessageView message={message} config={config} sessionId={sessionId} busy={busy} onApproval={(next, meta) => { if (!meta?.intermediate) setMessages(previous => [...previous, { role: 'assistant', text: String(next.answer || ''), result: next, created_at: new Date().toISOString() }]); }} onBusy={setBusy} />{fileLinks(message.result)}</div>)}
      {streamingMessages.map((message, index) => <div className="assistant-message-shell" key={`streamed-${message.created_at || 'message'}-${index}`}><MessageView message={message} config={config} sessionId={sessionId} busy={busy} onApproval={() => undefined} onBusy={setBusy} /></div>)}
      {streamingDraft && <div className="assistant-message-shell" key="streaming-draft"><MessageView message={{ role: 'assistant', text: streamingDraft }} config={config} sessionId={sessionId} busy={busy} onApproval={() => undefined} onBusy={setBusy} /></div>}
    </section>
    <div className="assistant-progress"><span id="status" role="status">{status}</span>{configError && <button id="retryConfig" type="button" className="assistant-text-button" onClick={() => window.location.reload()}>Retry connection</button>}{websiteError && <button id="retryWebsite" type="button" className="assistant-text-button" onClick={() => window.location.reload()}>Retry website connection</button>}<details id="progressDetails" hidden={!logs.length}><summary>Activity</summary><pre id="progressLog">{logs.join('\n')}</pre></details></div>
    <form id="composer" className="assistant-composer" onSubmit={submit}><ul id="uploadList" className="assistant-file-list" hidden={!files.length}>{files.map(file => <li key={workspacePathOf(file)}>{fileLabel(file)}</li>)}</ul><label className="assistant-sr-only" htmlFor="prompt">Message assistant</label><textarea id="prompt" rows={2} value={prompt} onChange={event => setPrompt(event.target.value)} onKeyDown={onPromptKeyDown} disabled={busy} placeholder="Ask assistant…" /><div className="assistant-model-row"><label htmlFor="model">Model</label><select id="model" disabled={busy || !ready} value={selectedModel} onChange={event => setSelectedModel(event.target.value)}>{config.models.map(model => <option key={model.key} value={model.key}>{modelLabel(model)}</option>)}</select></div><div className="assistant-actions"><label className="assistant-attach"><input id="uploadInput" type="file" multiple hidden onChange={event => upload(event.target.files)} />Attach</label><button id="stop" type="button" className="assistant-stop" hidden={!busy} onClick={() => abortRef.current?.abort()}>Stop waiting</button><button id="send" type="submit" className="assistant-send" disabled={busy || !ready || (websiteRequired && !websiteRef.current)}>{busy ? 'Working…' : <>Send <span aria-hidden="true">↑</span></>}</button></div></form>
  </main>;
}

function AssistantLogo({ large = false }: { large?: boolean }) {
  return <span className={`assistant-logo ${large ? 'large' : ''}`} aria-hidden="true"><AgentIcon size={large ? 50 : 34} /></span>;
}

export default AssistantPage;
