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
    const originalFetch = window.fetch.bind(window);
    window.fetch = async (input, init) => {
      const url = new URL(input instanceof Request ? input.url : String(input), window.location.href);
      if (credential.current && url.origin === window.location.origin) {
        const headers = new Headers(init?.headers || (input instanceof Request ? input.headers : undefined));
        headers.set('Authorization', 'Bearer ' + credential.current);
        const token = credential.current;
        const response = await originalFetch(input, { ...init, headers });
        if (response.status === 401 && credential.current === token) window.dispatchEvent(new Event('bioagent-auth-expired'));
        return response;
      }
      return originalFetch(input, init);
    };
    const request = () => window.parent.postMessage({ type: 'agent-auth-required', site_id: site }, origin);
    const receive = async (event: MessageEvent) => {
      if (event.source !== window.parent || event.origin !== origin) return;
      if (event.data?.type === 'agent-auth-error') { setError(String(event.data.message || 'Website sign-in failed.')); return; }
      if (event.data?.type !== 'agent-authenticate' || exchanging) return;
      exchanging = true;
      try {
        const response = await fetch('/auth/website/exchange', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ code: event.data.code, site_id: site, origin, credential_mode: 'bearer' }) });
        const body = await response.json();
        if (!response.ok) throw new Error(body.error || 'Website sign-in failed.');
        if (alive) { credential.current = body.access_token; setSession(body.session_id); setError(''); }
      } catch (caught) { if (alive) setError((caught as Error).message); }
      finally { exchanging = false; }
    };
    const expired = () => { if (!credential.current) return; credential.current = ''; setSession(null); request(); };
    const download = async (event: MouseEvent) => {
      const anchor = (event.target as Element)?.closest?.('a');
      if (!anchor) return;
      const url = new URL(anchor.href, location.href);
      if (url.origin !== location.origin || url.pathname !== '/workspace/file') return;
      event.preventDefault();
      try {
        const response = await fetch('/website/artifact-ticket', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ site_id: site, session_id: url.searchParams.get('session_id'), path: url.searchParams.get('path') }) });
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || 'Download failed.');
        const link = document.createElement('a'); link.href = '/website/download/' + encodeURIComponent(payload.token); link.download = ''; link.referrerPolicy = 'no-referrer'; link.click();
      } catch (caught) { setError((caught as Error).message); }
    };
    window.addEventListener('message', receive); window.addEventListener('bioagent-auth-expired', expired);
    document.addEventListener('click', download, true);
    request();
    return () => { alive = false; credential.current = ''; window.fetch = originalFetch; document.removeEventListener('click', download, true); window.removeEventListener('message', receive); window.removeEventListener('bioagent-auth-expired', expired); };
  }, [origin, site]);
  if (!session) return <main className="auth-screen"><p role="status">{error || 'Connecting your website account…'}</p>{error && <button onClick={() => window.location.reload()}>Retry</button>}</main>;
  return <WebsiteSession.Provider value={session}>{error && <p role="alert">{error}</p>}{children}</WebsiteSession.Provider>;
}
