import { useCallback, useEffect, useRef, useState } from 'react';
import { createApiClient } from './api';
import type { AppConfig, SessionSummary } from './types';
import { sessionIdOf } from './types';
import './styles.css';
import { SessionSidebar } from './features/sessions/SessionSidebar';
import { ConversationPane, type ConversationStatus } from './features/chat/ConversationPane';
import { fallbackPipelines } from './features/chat/QuickStarts';

const api = createApiClient();
const ACTIVE_SESSION_KEY = 'agent.web.active_session_id.v1';
const SIDEBAR_KEY = 'agent.web.sidebar_collapsed.v3';
const nowIso = () => new Date().toISOString();
async function newSession(): Promise<SessionSummary> {
  const { session_id: id } = await api.createSession();
  return { id, title: 'New chat', message_count: 0, created_at: nowIso(), updated_at: nowIso() };
}
function useIsMobile() {
  const [mobile, setMobile] = useState(() => window.matchMedia('(max-width: 700px)').matches);
  useEffect(() => {
    const query = window.matchMedia('(max-width: 700px)');
    const update = () => setMobile(query.matches);
    query.addEventListener('change', update);
    return () => query.removeEventListener('change', update);
  }, []);
  return mobile;
}

export default function App() {
  const [config, setConfig] = useState<AppConfig>({ default_model_key: '', default_max_turns: 20, models: [], pipelines: fallbackPipelines });
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [activeId, setActiveId] = useState('');
  const [visited, setVisited] = useState<string[]>([]);
  const [statuses, setStatuses] = useState<Record<string, ConversationStatus>>({});
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const creatingRef = useRef(false);
  const [error, setError] = useState('');
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => localStorage.getItem(SIDEBAR_KEY) === 'true');
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const isMobile = useIsMobile();
  const navigationCollapsed = isMobile ? !mobileSidebarOpen : sidebarCollapsed;
  const selectSession = (id: string) => {
    setVisited(previous => previous.includes(id) ? previous : [...previous, id]);
    setActiveId(id);
    setMobileSidebarOpen(false);
    localStorage.setItem(ACTIVE_SESSION_KEY, id);
  };
  useEffect(() => { setMobileSidebarOpen(false); }, [isMobile]);
  useEffect(() => { (window as any).__activeSession = activeId; }, [activeId]);
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [cfg, payload, jobs] = await Promise.all([api.loadConfig(), api.listSessions(), api.listRuns()]);
        let loaded: SessionSummary[] = payload.sessions.map(raw => ({
          id: sessionIdOf(raw), title: String(raw.title || 'New chat'), message_count: Number(raw.message_count || 0),
          last_run_id: raw.last_run_id, created_at: raw.created_at || nowIso(), updated_at: raw.updated_at || raw.created_at || nowIso(), pinned: Boolean(raw.pinned),
        })).filter(item => item.id);
        if (!loaded.length) loaded = [await newSession()];
        if (cancelled) return;
        setConfig({ ...cfg, pipelines: cfg.pipelines ?? fallbackPipelines });
        setSessions(loaded);
        const stored = localStorage.getItem(ACTIVE_SESSION_KEY);
        const id = loaded.some(item => item.id === stored) ? stored! : loaded[0].id;
        // Also reconnect to work that was running in another chat before reload.
        const live = jobs.runs.filter(run => ['queued', 'running', 'cancelling', 'pending_approval'].includes(run.status || '') && loaded.some(item => item.id === run.session_id));
        setStatuses(Object.fromEntries(live.map(run => [run.session_id!, run.status as ConversationStatus])));
        setVisited([...new Set([id, ...live.map(run => run.session_id!)])]);
        setActiveId(id);
      } catch (caught) {
        if (!cancelled) setError(`Could not load workspace: ${(caught as Error).message}`);
      } finally { if (!cancelled) setLoading(false); }
    })();
    return () => { cancelled = true; };
  }, []);

  const updateStatus = useCallback((id: string, status: ConversationStatus) => {
    setStatuses(previous => previous[id] === status ? previous : { ...previous, [id]: status });
  }, []);
  const messageAdded = useCallback((id: string, text?: string) => {
    setSessions(previous => previous.map(item => item.id === id ? {
      ...item, title: !item.message_count && text ? text.replace(/\s+/g, ' ').slice(0, 48) : item.title,
      message_count: item.message_count + 1, updated_at: nowIso(),
    } : item));
  }, []);
  const newChat = async () => {
    if (creatingRef.current) return;
    // Keep one unused conversation available, including its draft and uploads.
    // Prefer the selected one so repeated clicks do not move between old blanks.
    const unused = (session: SessionSummary) => session.message_count === 0 && !session.last_run_id
      && !['queued', 'running', 'cancelling', 'pending_approval', 'reconnecting'].includes(statuses[session.id]);
    const existing = sessions.find(session => session.id === activeId && unused(session)) || sessions.find(unused);
    if (existing) { selectSession(existing.id); return; }
    creatingRef.current = true;
    setCreating(true);
    try { const session = await newSession(); setSessions(previous => [session, ...previous]); selectSession(session.id); }
    finally { creatingRef.current = false; setCreating(false); }
  };
  const locked = (id: string) => ['queued', 'running', 'cancelling', 'pending_approval', 'uploading', 'reconnecting'].includes(statuses[id]);
  const update = async (id: string, changes: { title?: string; pinned?: boolean }) => {
    if (locked(id)) return;
    await api.updateSession(id, changes);
    setSessions(previous => previous.map(item => item.id === id ? { ...item, ...changes } : item));
  };
  const remove = async (id: string) => {
    if (locked(id)) throw new Error('Wait for this conversation’s task to finish before deleting it.');
    if (sessions.length <= 1) throw new Error('Create another chat before deleting your last conversation.');
    await api.deleteSession(id);
    setSessions(previous => previous.filter(item => item.id !== id));
    setVisited(previous => previous.filter(item => item !== id));
    if (activeId === id) selectSession(sessions.find(item => item.id !== id)!.id);
  };
  const toggleNavigation = () => {
    if (isMobile) { setMobileSidebarOpen(open => !open); return; }
    setSidebarCollapsed(value => { localStorage.setItem(SIDEBAR_KEY, String(!value)); return !value; });
  };
  return <div className={`app-shell ${navigationCollapsed ? 'sidebar-collapsed' : ''}`}>
    <SessionSidebar sessions={sessions} activeId={activeId} statuses={statuses} collapsed={navigationCollapsed}
      mobileOpen={isMobile && mobileSidebarOpen} disabled={loading} creating={creating} onToggle={toggleNavigation}
      onMobileClose={() => setMobileSidebarOpen(false)} onSelect={selectSession} onNew={newChat}
      onRename={(id, title) => update(id, { title })} onPin={(id, pinned) => update(id, { pinned })} onDelete={remove} />
    {error && <div className="error-banner" role="alert">{error} <button onClick={() => window.location.reload()}>Retry</button></div>}
    {loading && <main className="main-column"><div className="loading-state">Loading workspace…</div></main>}
    {visited.map(id => <ConversationPane key={id} sessionId={id} active={id === activeId} config={config}
      onStatus={updateStatus} onMessage={messageAdded} onOpenNavigation={() => setMobileSidebarOpen(true)} />)}
  </div>;
}
