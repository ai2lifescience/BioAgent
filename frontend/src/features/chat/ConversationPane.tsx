import { useCallback, useEffect, useRef, useState } from 'react';
import { createApiClient } from '../../api';
import type { AppConfig, Message, RunResult, StreamFrame, WorkspaceFile } from '../../types';
import { workspacePathOf } from '../../types';
import { Composer } from './Composer';
import { QuickStarts } from './QuickStarts';
import { WorkspacePanel } from '../workspace/WorkspacePanel';
import { MessageView } from '../messages';
import { RunProgress } from '../messages/RunProgress';
import { useRunProgress } from '../messages/useRunProgress';
import { LineIcon } from '../../components/icons';

export type ConversationStatus = 'idle' | 'queued' | 'running' | 'cancelling' | 'cancelled' | 'pending_approval' | 'uploading' | 'reconnecting' | 'succeeded' | 'failed';
const api = createApiClient(undefined, '', 'poll');
const nowIso = () => new Date().toISOString();
function workspaceFiles(value: unknown): WorkspaceFile[] {
  return Array.isArray(value) ? value.filter(item => item && typeof item === 'object') as WorkspaceFile[] : [];
}
interface Props {
  sessionId: string; active: boolean; config: AppConfig;
  onStatus: (id: string, status: ConversationStatus) => void;
  onMessage: (id: string, text?: string) => void;
  onOpenNavigation: () => void;
}

/** A mounted pane owns one conversation for its entire lifetime. Async callbacks
 * never consult the selected sidebar ID, including uploads and approval resumes. */
export function ConversationPane({ sessionId, active, config, onStatus, onMessage, onOpenNavigation }: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [files, setFiles] = useState<WorkspaceFile[]>([]);
  const [prompt, setPrompt] = useState('');
  const [model, setModel] = useState(config.default_model_key || config.models[0]?.key || '');
  const [turns, setTurns] = useState(config.default_max_turns || 20);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [stopping, setStopping] = useState(false);
  const [pending, setPending] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [status, setStatus] = useState<ConversationStatus>('idle');
  const [workspaceOpen, setWorkspaceOpen] = useState(false);
  const [workspaceSearch, setWorkspaceSearch] = useState('');
  const [workspaceFilter, setWorkspaceFilter] = useState('all');
  const [error, setError] = useState('');
  const [connection, setConnection] = useState('');
  const controller = useRef<AbortController | null>(null);
  const occupied = useRef(false);
  const approvalCompleted = useRef(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const progress = useRunProgress();
  const { reset, finish, onFrame } = progress;
  useEffect(() => { onStatus(sessionId, uploading ? 'uploading' : status); }, [sessionId, status, uploading, onStatus]);
  useEffect(() => { if (!active) setWorkspaceOpen(false); }, [active]);

  const refreshFiles = useCallback(async () => {
    const payload = await api.loadWorkspace(sessionId);
    setFiles(workspaceFiles(payload.workspace?.files));
  }, [sessionId]);
  const frame = useCallback((value: StreamFrame) => {
    if (['run_status', 'queued', 'cancelling'].includes(value.event) && value.payload.run_id) setActiveRunId(String(value.payload.run_id));
    if (value.event === 'run_status' && ['queued', 'running', 'cancelling'].includes(value.payload.status)) setStatus(value.payload.status);
    if (value.event === 'cancelling' || (value.event === 'run_status' && value.payload.status === 'cancelling')) { setStopping(true); setStatus('cancelling'); }
    if (value.event === 'connection') setConnection(String(value.payload.message || ''));
    onFrame(value);
  }, [onFrame]);
  const complete = useCallback((result: RunResult) => {
    const answer = String(result.answer || 'The run completed.');
    const activity = finish(answer);
    setMessages(previous => [...previous, { role: 'assistant', text: answer, result, progress: activity, created_at: nowIso() }]);
    const review = Boolean(result.approval_required);
    setPending(review);
    setStatus(review ? 'pending_approval' : result.run_status === 'cancelled' || result.status === 'cancelled' ? 'cancelled' : ['failed', 'blocked', 'interrupted'].includes(result.run_status || '') ? 'failed' : 'succeeded');
    setActiveRunId(null); setStopping(false);
    setRunning(false); occupied.current = false;
    setConnection(''); setError('');
    if (result.workspace_files || result.files) setFiles(workspaceFiles(result.workspace_files ?? result.files));
    void refreshFiles().catch(() => undefined);
    onMessage(sessionId);
  }, [finish, onMessage, refreshFiles, sessionId]);

  const watch = useCallback(async (runId: string, signal: AbortSignal) => {
    setActiveRunId(runId);
    occupied.current = true; setRunning(true); setPending(false); reset();
    try { complete(await api.watchRun(runId, signal, frame)); }
    catch (caught) {
      if (signal.aborted) return;
      setError(`Could not follow this run: ${(caught as Error).message}`);
      setStatus('reconnecting');
      // Keep this chat protected until its server state is known. Other chats
      // remain usable, and Retry below reconnects without submitting new work.
    }
  }, [complete, frame, reset]);

  const restore = useCallback(async (signal: AbortSignal, failedSubmission?: { error: string; draft: string }) => {
    setLoading(true);
    try {
      const [history, workspace] = await Promise.all([api.loadMessages(sessionId, true), api.loadWorkspace(sessionId)]);
      if (signal.aborted) return;
      const next = [...(history.messages || [])];
      if (history.pending_approval && !history.active_run) next.push({ role: 'assistant', text: String(history.pending_approval.answer || ''), result: history.pending_approval });
      setMessages(next); setFiles(workspaceFiles(workspace.workspace?.files));
      setError(''); setLoading(false);
      if (history.active_run?.run_id) {
        setStatus(history.active_run.status as ConversationStatus);
        await watch(history.active_run.run_id, signal);
      } else {
        occupied.current = false; setRunning(false); setPending(Boolean(history.pending_approval));
        setActiveRunId(null); setStopping(false);
        setStatus(history.pending_approval ? 'pending_approval' : failedSubmission ? 'failed' : 'idle'); setConnection(''); reset();
        if (failedSubmission) { setError(failedSubmission.error); setPrompt(previous => previous || failedSubmission.draft); }
      }
    } catch (caught) {
      if (!signal.aborted) { setError(`Could not load this chat: ${(caught as Error).message}`); setStatus('reconnecting'); }
    }
  }, [sessionId, watch, reset]);
  useEffect(() => {
    const current = new AbortController(); controller.current = current;
    void restore(current.signal);
    return () => { current.abort(); controller.current?.abort(); };
  }, [restore]);
  const reconnect = () => {
    controller.current?.abort();
    const current = new AbortController(); controller.current = current;
    void restore(current.signal);
  };
  const submit = async () => {
    const text = prompt.trim();
    if (!text || occupied.current || pending || loading || uploading) return;
    occupied.current = true; setRunning(true); setStatus('queued'); setError(''); reset(); setPrompt('');
    setActiveRunId(null); setStopping(false);
    setMessages(previous => [...previous, { role: 'user', text, created_at: nowIso() }]); onMessage(sessionId, text);
    const current = new AbortController(); controller.current = current;
    try { complete(await api.run(text, { sessionId, modelKey: model, maxTurns: turns, signal: current.signal, onFrame: frame })); }
    catch (caught) {
      if (current.signal.aborted) return;
      setError(`Request connection failed: ${(caught as Error).message}. Checking server state…`);
      // A POST response can be lost after enqueue. Restore the existing job;
      // never resubmit automatically or allow a second run over unknown work.
      await restore(current.signal, { error: `Request failed: ${(caught as Error).message}`, draft: text });
    }
  };
  const stop = async () => {
    if (!activeRunId || stopping) return;
    setStopping(true); setStatus('cancelling'); setError('');
    try {
      await api.cancelRun(activeRunId);
      // Keep watching for server confirmation; aborting fetch would only hide work.
    } catch (caught) {
      setStopping(false); setStatus('reconnecting');
      setError(`Could not confirm Stop: ${(caught as Error).message}. Retry Stop or reconnect.`);
    }
  };
  const upload = async (selected: FileList | File[] | null) => {
    if (!selected?.length || occupied.current || pending || loading) return;
    occupied.current = true; setUploading(true);
    try { await api.uploadFiles(sessionId, Array.from(selected)); await refreshFiles(); }
    catch (caught) { setError(`Upload failed: ${(caught as Error).message}`); }
    finally { occupied.current = false; setUploading(false); if (inputRef.current) inputRef.current.value = ''; }
  };
  const deleteFile = async (path: string) => {
    const result = await api.deleteWorkspaceFile(sessionId, path);
    if (!result.deleted) throw new Error(result.error || 'File was not deleted.');
    setFiles(previous => previous.filter(file => workspacePathOf(file) !== path));
  };
  return <div className="conversation-pane" data-session-id={sessionId} style={{ display: active ? 'contents' : 'none' }}>
    <main className="main-column">
      <div className="mobile-actions"><button className="mobile-menu-button" onClick={onOpenNavigation} aria-label="Open navigation"><LineIcon name="chevron" /></button><button className="mobile-workspace-button" onClick={() => setWorkspaceOpen(true)}>Workspace</button></div>
      <div className="chat-scroll"><div id={active ? 'chat' : undefined} className="chat-content">
        {error && <div className="error-banner" role="status">{error}<button onClick={reconnect}>Retry connection</button></div>}
        {connection && <div className="run-notice" role="status">{connection}</div>}
        {loading ? <div className="conversation-loading" role="status"><span className="spinner" /><div><strong>Loading conversation</strong><span>Restoring messages and workspace files…</span></div></div>
          : messages.length || running ? messages.map((message, i) => <MessageView key={`${message.created_at || i}-${i}`} message={message} config={config} sessionId={sessionId} busy={running}
            onBusy={value => {
              if (value) { approvalCompleted.current = false; occupied.current = true; reset(); setRunning(true); setStatus('queued'); }
              else if (!approvalCompleted.current) reconnect();
            }} onProgress={frame} onApproval={(next, meta) => {
              approvalCompleted.current = true;
              if (meta?.intermediate) {
                setMessages(previous => previous.map((item, index) => index === i ? { ...item, text: String(next.answer || item.text), result: next } : item));
                setRunning(false); occupied.current = false; setPending(true); setStatus('pending_approval'); reset();
              } else { complete(next); }
            }} />)
          : <QuickStarts capabilities={config.capabilities} pipelines={config.pipelines || []} isolated={config.isolated_execution} onChoose={setPrompt} />}
        {running && <><p className="run-notice" role="status">{stopping ? 'Stopping' : status === 'queued' ? 'Queued' : 'Working'} — you can switch chats or start another conversation.</p><RunProgress entries={progress.entries} running /></>}
        {pending && !running && <p className="run-notice">Review the pending approval above before sending another message.</p>}
      </div></div>
      <Composer models={config.models} prompt={prompt} onPromptChange={setPrompt} fileCount={files.length} running={running}
        disabled={loading || pending || uploading} model={model} turns={turns} onModelChange={setModel} onTurnsChange={setTurns}
        onSubmit={submit} onStop={stop} stopping={stopping} stopDisabled={!activeRunId}
        onAttach={() => inputRef.current?.click()} sendId={active ? 'send' : undefined} />
    </main>
    <WorkspacePanel maxFileBytes={config.storage_limits?.file_bytes} sessionId={sessionId} files={files} search={workspaceSearch} filter={workspaceFilter}
      busy={running || pending || loading} uploading={uploading} mobileOpen={active && workspaceOpen} onClose={() => setWorkspaceOpen(false)}
      onSearch={setWorkspaceSearch} onFilter={setWorkspaceFilter} onUpload={upload} onRefresh={() => void refreshFiles().catch(caught => setError(String(caught)))} onDelete={deleteFile} />
    <input ref={inputRef} hidden type="file" multiple onChange={event => void upload(event.target.files)} />
  </div>;
}
