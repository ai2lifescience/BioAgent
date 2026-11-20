import { createContext, useEffect, useRef, useState, type ReactNode } from 'react';

export const WebsiteSession = createContext<string | null>(null);

/** The host supplies a one-time code; the iframe keeps its bearer credential in memory. */
export function WebsiteProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<string | null>(null);
  const [error, setError] = useState('');
  const credential = useRef('');
  const query = new URLSearchParams(window.location.search);
  const origin = query.get('parent_origin') || '';
  const site = query.get('website_site') || '';
  useEffect(() => {
    let alive = true, exchanging = false;
    let refreshTimer: number | undefined;
    let lastRefreshedAt = 0;
    let refreshIntervalMs = 30_000;
    let pendingRefresh: { promise: Promise<string | null>; resolve: (token: string | null) => void; timer: number } | null = null;
    const agentUrl = (path: string) => new URL(path, window.location.href);
    const originalFetch = window.fetch.bind(window);
    const settlePending = (token: string | null) => {
      if (!pendingRefresh) return;
      const current = pendingRefresh;
      pendingRefresh = null;
      window.clearTimeout(current.timer);
      current.resolve(token);
    };
    const scheduleRefresh = (delayMs: number) => {
      window.clearTimeout(refreshTimer);
      if (!alive) return;
      refreshTimer = window.setTimeout(() => { void requestAuth(true); }, delayMs);
    };
    const requestAuth = (isRefresh: boolean): Promise<string | null> => {
      if (!alive) return Promise.resolve(null);
      if (pendingRefresh) return pendingRefresh.promise;
      let resolvePromise!: (token: string | null) => void;
      const promise = new Promise<string | null>(resolve => { resolvePromise = resolve; });
      const timer = window.setTimeout(() => {
        settlePending(null);
        if (alive && credential.current) scheduleRefresh(5000);
      }, 15_000);
      pendingRefresh = { promise, resolve: resolvePromise, timer };
      window.parent.postMessage({ type: 'agent-auth-required', site_id: site, refresh: isRefresh }, origin);
      return promise;
    };
    const canRetryBody = (input: RequestInfo | URL, init?: RequestInit) => {
      if (input instanceof Request) return ['GET', 'HEAD'].includes(input.method.toUpperCase());
      const body = init?.body;
      return body == null || typeof body === 'string' || body instanceof URLSearchParams || body instanceof ArrayBuffer || ArrayBuffer.isView(body) || body instanceof Blob;
    };
    const withBearer = (input: RequestInfo | URL, init: RequestInit | undefined, token: string) => {
      const headers = new Headers(init?.headers || (input instanceof Request ? input.headers : undefined));
      headers.set('Authorization', 'Bearer ' + token);
      return { ...init, headers };
    };
    window.fetch = async (input, init) => {
      const url = new URL(input instanceof Request ? input.url : String(input), window.location.href);
      if (credential.current && url.origin === window.location.origin && !url.pathname.includes('/auth/')) {
        const token = credential.current;
        const response = await originalFetch(input, withBearer(input, init, token));
        if (response.status !== 401) return response;
        if (canRetryBody(input, init)) {
          const fresh = (credential.current && credential.current !== token)
            ? credential.current
            : await requestAuth(true);
          if (fresh && alive) {
            const retried = await originalFetch(input, withBearer(input, init, fresh));
            if (retried.status !== 401) return retried;
            if (credential.current === fresh) { credential.current = ''; setSession(null); }
            return retried;
          }
        }
        if (credential.current === token) { credential.current = ''; setSession(null); void requestAuth(false); }
        return response;
      }
      return originalFetch(input, init);
    };
    const receive = async (event: MessageEvent) => {
      if (event.source !== window.parent || event.origin !== origin) return;
      if (event.data?.type === 'agent-auth-error') {
        credential.current = '';
        setSession(null);
        setError(String(event.data.message || 'Website sign-in failed.'));
        window.clearTimeout(refreshTimer);
        settlePending(null);
        return;
      }
      if (event.data?.type !== 'agent-authenticate' || exchanging) return;
      exchanging = true;
      try {
        const response = await originalFetch(agentUrl('auth/website/exchange'), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ code: event.data.code, site_id: site, origin, credential_mode: 'bearer' }) });
        const body = await response.json();
        if (!response.ok) throw new Error(body.error || 'Website sign-in failed.');
        if (alive) {
          credential.current = body.access_token;
          lastRefreshedAt = Date.now();
          refreshIntervalMs = Math.max(10, Math.min(600, Number(body.expires_in || 3600) * 0.5)) * 1000;
          setSession(body.session_id);
          setError('');
          scheduleRefresh(refreshIntervalMs);
          settlePending(body.access_token);
        }
      } catch (caught) {
        settlePending(null);
        if (alive) {
          if (credential.current) scheduleRefresh(5000);
          else setError((caught as Error).message);
        }
      } finally { exchanging = false; }
    };
    const maybeRefreshOnResume = () => {
      if (document.visibilityState === 'hidden' || !credential.current) return;
      if (Date.now() - lastRefreshedAt >= refreshIntervalMs) void requestAuth(true);
    };
    const download = async (event: MouseEvent) => {
      const anchor = (event.target as Element)?.closest?.('a');
      if (!anchor) return;
      const url = new URL(anchor.href, location.href);
      if (url.origin !== location.origin || url.pathname !== agentUrl('workspace/file').pathname) return;
      event.preventDefault();
      try {
        const response = await fetch(agentUrl('website/artifact-ticket'), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ site_id: site, session_id: url.searchParams.get('session_id'), path: url.searchParams.get('path') }) });
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || 'Download failed.');
        const link = document.createElement('a'); link.href = agentUrl('website/download/' + encodeURIComponent(payload.token)).href; link.download = ''; link.referrerPolicy = 'no-referrer'; link.click();
      } catch (caught) { setError((caught as Error).message); }
    };
    window.addEventListener('message', receive);
    window.addEventListener('focus', maybeRefreshOnResume);
    document.addEventListener('visibilitychange', maybeRefreshOnResume);
    document.addEventListener('click', download, true);
    void requestAuth(false);
    return () => {
      alive = false;
      window.clearTimeout(refreshTimer);
      settlePending(null);
      credential.current = '';
      window.fetch = originalFetch;
      document.removeEventListener('click', download, true);
      document.removeEventListener('visibilitychange', maybeRefreshOnResume);
      window.removeEventListener('focus', maybeRefreshOnResume);
      window.removeEventListener('message', receive);
    };
  }, [origin, site]);
  if (!session) return <main className="auth-screen"><p role="status">{error || 'Connecting your website account…'}</p>{error && <button onClick={() => window.location.reload()}>Retry</button>}</main>;
  return <WebsiteSession.Provider value={session}>{error && <p role="alert">{error}</p>}{children}</WebsiteSession.Provider>;
}
