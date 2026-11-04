import { useCallback, useEffect, useMemo, useRef, useState, type RefObject } from 'react';

type WebsiteBinding = { binding_id: string; token: string; session_id: string; site_id?: string };
type WebsiteRequest = { call_id: string; run_id?: string; method?: string; arguments?: Record<string, unknown>; revision?: string; deadline?: number; session_id?: string };
type AssistantContext = Record<string, unknown>;

function parentOriginFromQuery() {
  try {
    const raw = new URLSearchParams(window.location.search).get('parent_origin') || window.location.origin;
    const origin = new URL(raw, window.location.origin);
    return origin.protocol === 'http:' || origin.protocol === 'https:' ? origin.origin : window.location.origin;
  } catch { return window.location.origin; }
}

function apiUrl(path: string) { return new URL(path, window.location.href).toString(); }

interface HostUI {
  sessionRef: RefObject<string>;
  onLog: (message: unknown) => void;
  onStatus: (message: string) => void;
  onFilesChanged: () => Promise<void>;
}

/** Browser protocol lifecycle; the host UI supplies only rendering callbacks. */
export function useWebsiteBridge({ sessionRef, onLog: appendLog, onStatus: setStatus, onFilesChanged }: HostUI) {
  const parentOrigin = useMemo(parentOriginFromQuery, []);
  const websiteRequired = Boolean(new URLSearchParams(window.location.search).get('website_site'));
  const [context, setContext] = useState<AssistantContext>(() => {
    const query = new URLSearchParams(window.location.search);
    return Object.fromEntries(['project_id', 'sample_id', 'result_type'].flatMap(key => query.get(key) ? [[key, query.get(key)!]] : []));
  });
  const [website, setWebsite] = useState<WebsiteBinding | null>(null);
  const [websiteError, setWebsiteError] = useState('');
  const websiteRef = useRef<WebsiteBinding | null>(null);
  const contextRef = useRef(context);
  const parentRef = useRef(parentOrigin);
  const websitePollRef = useRef(false);
  const websiteQueueRef = useRef(Promise.resolve());
  useEffect(() => { websiteRef.current = website; }, [website]);
  useEffect(() => { contextRef.current = context; }, [context]);
  useEffect(() => () => { websiteRef.current = null; }, []);

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
      } else if (data.type === 'agent-files-changed' && data.session_id === sessionRef.current) {
        void onFilesChanged()
          .catch(error => appendLog(`Could not refresh files: ${(error as Error).message}`));
      }
    };
    window.addEventListener('message', onMessage);
    if (sessionRef.current) postParent({ type: 'agent-ready', session_id: sessionRef.current });
    return () => window.removeEventListener('message', onMessage);
  }, [onFilesChanged, appendLog, connectWebsite, postParent, queueContextUpdate, setSafeContext, websitePost]);

  const disconnect = useCallback(() => {
    const binding = websiteRef.current;
    websiteRef.current = null; setWebsite(null);
    if (binding) void websitePost('website/disconnect', binding).catch(() => undefined);
  }, [websitePost]);
  const newConversation = useCallback(async () => {
    const value = await websitePost<{ session_id: string }>('website/conversation', websiteRef.current);
    return value.session_id;
  }, [websitePost]);
  const notifyRunComplete = useCallback((result: { status?: string; answer?: string; artifacts?: unknown; files?: unknown }) => {
    postParent({ type: 'agent-event', event: { type: 'run-complete', session_id: sessionRef.current,
      status: result.status, answer: result.answer, artifacts: result.artifacts || result.files || [] } });
  }, [postParent, sessionRef]);
  return { context, websiteRef, websiteError, setWebsiteError, websiteRequired,
    postParent, newConversation, disconnect, notifyRunComplete };
}
