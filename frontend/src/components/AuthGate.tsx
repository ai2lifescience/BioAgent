import { useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react';
import './auth.css';

type Status = { mode: 'local' | 'multiuser'; registration_enabled?: boolean; user: { id: string; name: string } | null };
const CHANGE_KEY = 'bioagent.auth.changed';
const endpoint = (path: string) => new URL(`/auth/${path}`, window.location.href).toString();

// Covers normal API requests, streaming handshakes, and iframe bridge calls.
// Credentials stay in an HttpOnly cookie and never enter model context.
export function installAuthEvents() {
  const original = window.fetch.bind(window);
  window.fetch = async (...args: Parameters<typeof fetch>) => {
    const response = await original(...args);
    if (response.status === 401 && !new URL(response.url).pathname.includes('/auth/')) {
      window.dispatchEvent(new Event('bioagent-auth-expired'));
    }
    return response;
  };
}

export function AuthGate({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<Status | null>(null);
  const [error, setError] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [registering, setRegistering] = useState(false);
  const [confirmPassword, setConfirmPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const generation = useRef(0);
  useEffect(() => {
    let alive = true;
    const refresh = async () => {
      const version = ++generation.current;
      try {
        const response = await fetch(endpoint('status'), { cache: 'no-store' });
        if (!response.ok) throw new Error('Could not check your login.');
        const next = await response.json() as Status;
        if (alive && version === generation.current) { setStatus(next); setError(''); }
      } catch (e) {
        if (alive && version === generation.current) { setStatus(null); setError((e as Error).message); }
      }
    };
    const expired = () => { ++generation.current; setStatus(previous => previous ? { ...previous, user: null } : null); setPassword(''); };
    const changed = (event: StorageEvent) => {
      if (event.key === CHANGE_KEY) { setStatus(null); void refresh(); }
    };
    const timer = window.setInterval(refresh, 30000);
    window.addEventListener('focus', refresh);
    window.addEventListener('storage', changed);
    window.addEventListener('bioagent-auth-expired', expired);
    void refresh();
    return () => {
      alive = false;
      window.clearInterval(timer);
      window.removeEventListener('focus', refresh);
      window.removeEventListener('storage', changed);
      window.removeEventListener('bioagent-auth-expired', expired);
    };
  }, []);
  const announce = () => {
    ++generation.current;
    localStorage.removeItem('agent.web.active_session_id.v1');
    // This is a notification marker, not a credential; randomUUID is absent on LAN HTTP.
    localStorage.setItem(CHANGE_KEY, `${Date.now()}-${Math.random()}`);
  };
  const login = async (event: FormEvent) => {
    event.preventDefault(); ++generation.current; setBusy(true); setError('');
    try {
      if (registering && password !== confirmPassword) throw new Error('Passwords do not match.');
      const response = await fetch(endpoint(registering ? 'register' : 'login'), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username, password }) });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || 'Sign-in failed.');
      setPassword(''); setConfirmPassword(''); setStatus(previous => ({ ...previous, mode: 'multiuser', user: payload.user })); announce();
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  };
  const logout = async () => {
    ++generation.current;
    setBusy(true);
    try {
      const response = await fetch(endpoint('logout'), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
      if (!response.ok && response.status !== 401) throw new Error('Sign-out failed. Please try again.');
      setStatus(previous => ({ ...previous, mode: 'multiuser', user: null })); setPassword(''); setConfirmPassword(''); setRegistering(false); announce();
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  };
  if (!status) return <main className="auth-screen"><p role="status">{error || 'Connecting…'}</p>{error && <button onClick={() => window.location.reload()}>Retry</button>}</main>;
  if (!status.user) return <main className="auth-screen"><form className="auth-card" onSubmit={login}>
    <h1>{registering ? 'Create your account' : 'Sign in to BioAgent'}</h1><p>Your conversations and files stay with your account.</p>
    <label>Username<input autoComplete="username" required maxLength={100} pattern={registering ? '[A-Za-z0-9_.@\\-]+' : undefined} value={username} onChange={event => setUsername(event.target.value)} /></label>
    <label>Password<input type="password" autoComplete={registering ? 'new-password' : 'current-password'} required minLength={registering ? 12 : undefined} maxLength={1024} value={password} onChange={event => setPassword(event.target.value)} /></label>
    {registering && <><p>Use at least 12 characters.</p><label>Confirm password<input type="password" autoComplete="new-password" required value={confirmPassword} onChange={event => setConfirmPassword(event.target.value)} /></label></>}
    {error && <p role="alert">{error}</p>}<button disabled={busy} type="submit">{busy ? 'Please wait…' : registering ? 'Create account' : 'Sign in'}</button>
    {status.registration_enabled && <button className="auth-switch" type="button" disabled={busy} onClick={() => { setRegistering(!registering); setError(''); setPassword(''); setConfirmPassword(''); }}>{registering ? 'Already registered? Sign in' : 'Create account'}</button>}
  </form></main>;
  return <div className="auth-shell" key={status.user.id}>
    {status.mode === 'multiuser' && <div className="auth-bar"><span>{status.user.name}</span>{error && <span role="alert">{error}</span>}<button disabled={busy} onClick={logout}>Sign out</button></div>}
    <div className="auth-content">{children}</div>
  </div>;
}
