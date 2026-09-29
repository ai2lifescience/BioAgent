export type WebsiteAdapter = Record<string, (arguments_: Record<string, unknown>, request?: Record<string, unknown>) => unknown | Promise<unknown>> & {
  getPageContext?: () => unknown | Promise<unknown>;
};

export interface AssistantDrawerOptions {
  target?: HTMLElement;
  src?: string;
  siteId?: string;
  getToken?: () => Promise<string>;
  adapter?: WebsiteAdapter;
  context?: Record<string, unknown>;
  title?: string;
  launcherLabel?: string;
  open?: boolean;
  onEvent?: (event: Record<string, unknown>) => void;
}

export interface AssistantDrawerHandle {
  open(): void;
  close(): void;
  updateContext(context?: Record<string, unknown>, options?: { waitForSync?: boolean }): Promise<Record<string, unknown>>;
  readonly binding: { binding_id: string } | null;
  destroy(): void;
}

const PROTOCOL = 1;
const CSS = `
:host{all:initial}.agent-launcher{position:fixed;right:22px;bottom:22px;z-index:2147483000;display:inline-flex;align-items:center;gap:9px;border:1px solid #0d655e;border-radius:999px;padding:10px 15px;color:#fff;background:linear-gradient(145deg,#159487,#115e59);box-shadow:0 10px 26px #17343835;font:700 13px/1.2 Inter,ui-sans-serif,system-ui,sans-serif;cursor:pointer;transition:transform .18s ease,box-shadow .18s ease}.agent-launcher:hover{transform:translateY(-2px);box-shadow:0 14px 30px #17343845}.agent-icon{display:inline-grid;width:28px;height:28px;place-items:center;flex:0 0 auto;line-height:0}.agent-icon svg{display:block;width:100%;height:100%}.agent-panel{position:fixed;z-index:2147483001;inset:0 0 0 auto;display:grid;grid-template-rows:auto minmax(0,1fr);width:min(460px,100vw);overflow:hidden;border-left:1px solid #d9e5e4;background:#f4f8f8;box-shadow:-16px 0 40px #17343826;transition:transform .22s ease}.agent-panel[hidden]{display:grid;transform:translateX(102%);pointer-events:none;box-shadow:none}.agent-panel-header{display:flex;align-items:center;gap:10px;min-height:58px;padding:11px 16px;border-bottom:1px solid #d9e5e4;color:#173438;background:#ffffffed;backdrop-filter:blur(12px);font:700 14px/1.2 Inter,ui-sans-serif,system-ui,sans-serif}.agent-panel-header .agent-panel-title{margin-right:auto}.agent-panel-header>.agent-icon{width:30px;height:30px}.agent-close{display:grid;width:30px;height:30px;place-items:center;border:1px solid #d9e5e4;border-radius:8px;color:#62777b;background:#f4f8f8;font-size:20px;line-height:1;cursor:pointer}.agent-close:hover{color:#115e59;background:#e7f4f1}.agent-frame{display:block;width:100%;height:100%;border:0}@media(max-width:480px){.agent-launcher{right:12px;bottom:12px}.agent-panel{width:100vw}}
`;

function randomId(prefix: string) {
  const uuid = globalThis.crypto?.randomUUID?.();
  return `${prefix}_${uuid || `${Date.now()}_${Math.random().toString(36).slice(2)}`}`;
}

function createAgentIcon(size: number) {
  const icon = document.createElement('span');
  icon.className = 'agent-icon';
  icon.setAttribute('aria-hidden', 'true');
  const gradientId = randomId('agent-gradient');
  icon.innerHTML = `<svg width="${size}" height="${size}" viewBox="0 0 64 64" fill="none" aria-hidden="true"><defs><linearGradient id="${gradientId}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#159BEA"/><stop offset="1" stop-color="#1486D8"/></linearGradient></defs><rect x="9" y="18" width="46" height="32" rx="11" fill="url(#${gradientId})" stroke="#25283A" stroke-width="3"/><path d="M32 18V9" stroke="#25283A" stroke-width="3" stroke-linecap="round"/><circle cx="32" cy="7" r="3" fill="#159BEA" stroke="#25283A" stroke-width="2"/><circle cx="24" cy="32" r="3" fill="#202332"/><circle cx="40" cy="32" r="3" fill="#202332"/><path d="M28 40c2 2 6 2 8 0" stroke="#63D2F5" stroke-width="2.5" stroke-linecap="round"/><rect x="23" y="48" width="18" height="11" rx="4" fill="#F1F0ED" stroke="#25283A" stroke-width="3"/></svg>`;
  return icon;
}

export function mountAssistantDrawer(options: AssistantDrawerOptions = {}): AssistantDrawerHandle {
  const host = options.target || document.body;
  const src = new URL(options.src || '/assistant', window.location.href);
  if (!['http:', 'https:'].includes(src.protocol)) throw new Error('Assistant source must use HTTP or HTTPS.');
  const sourceOrigin = src.origin;
  const parentOrigin = window.location.origin;
  src.searchParams.set('parent_origin', parentOrigin);
  src.searchParams.set('embedded', '1');
  if (options.siteId) src.searchParams.set('website_site', options.siteId);
  const shadow = host.attachShadow ? host.attachShadow({ mode: 'open' }) : host;
  const style = document.createElement('style'); style.textContent = CSS;
  const launcher = document.createElement('button'); launcher.className = 'agent-launcher'; launcher.type = 'button'; launcher.setAttribute('aria-expanded', 'false'); launcher.setAttribute('aria-label', options.title || 'Assistant');
  const icon = createAgentIcon(28);
  launcher.append(icon, document.createTextNode(options.launcherLabel || 'Ask assistant'));
  const panel = document.createElement('aside'); panel.className = 'agent-panel'; panel.hidden = true; panel.setAttribute('aria-label', options.title || 'Assistant');
  const header = document.createElement('div'); header.className = 'agent-panel-header';
  const panelIcon = createAgentIcon(30);
  const title = document.createElement('span'); title.className = 'agent-panel-title'; title.textContent = options.title || 'Assistant';
  const close = document.createElement('button'); close.className = 'agent-close'; close.type = 'button'; close.textContent = '×'; close.setAttribute('aria-label', 'Close assistant');
  const frame = document.createElement('iframe'); frame.className = 'agent-frame'; frame.title = options.title || 'Assistant'; frame.src = src.toString();
  header.append(panelIcon, title, close); panel.append(header, frame); shadow.append(style, launcher, panel);

  let destroyed = false;
  let connectionAttempt = 0;
  let connecting = false;
  let sessionId: string | null = null;
  let binding: { binding_id: string; token?: string; session_id?: string; site_id?: string } | null = null;
  let lastFocus: Element | null = null;
  let context: Record<string, unknown> = { ...(options.context || {}) };
  let connectionTimer: number | null = null;
  let updateSequence = 0;
  const calls = new Map<string, Promise<{ result?: unknown; error?: unknown }>>();
  const syncWaiters = new Map<string, { resolve: () => void; reject: (error: Error) => void; timer: number }>();
  const adapter = options.adapter || {};

  const post = (message: Record<string, unknown>) => frame.contentWindow?.postMessage({ protocol: PROTOCOL, ...message }, sourceOrigin);
  const clearTimer = () => { if (connectionTimer !== null) window.clearTimeout(connectionTimer); connectionTimer = null; };
  const emitError = (message: string) => { connecting = false; clearTimer(); post({ type: 'agent-website-error', session_id: sessionId || undefined, message }); options.onEvent?.({ type: 'website-error', message }); };
  const contextSnapshot = async () => {
    const next = typeof adapter.getPageContext === 'function' ? await adapter.getPageContext() : context;
    context = { ...((next && typeof next === 'object') ? next : {}) };
    return context;
  };
  const sendContextAndWait = () => {
    const id = `${randomId('context')}_${++updateSequence}`;
    const wait = new Promise<void>((resolve, reject) => {
      const timer = window.setTimeout(() => { syncWaiters.delete(id); reject(new Error('Website context update timed out.')); }, 5000);
      syncWaiters.set(id, { resolve, reject, timer });
    });
    post({ type: 'agent-context', context, context_update_id: id });
    return wait;
  };
  const updateContext = async (next?: Record<string, unknown>, updateOptions: { waitForSync?: boolean } = {}) => {
    context = next ? { ...next } : await contextSnapshot();
    if (updateOptions.waitForSync && binding) await sendContextAndWait(); else post({ type: 'agent-context', context });
    return context;
  };
  const connect = async () => {
    if (!options.siteId || typeof options.getToken !== 'function' || connecting || binding || destroyed) return;
    connecting = true; const attempt = ++connectionAttempt; const expectedSession = sessionId;
    connectionTimer = window.setTimeout(() => { if (attempt === connectionAttempt) { connectionAttempt++; emitError('Website connection timed out. Retry the connection.'); } }, 15000);
    try {
      if (typeof adapter.getPageContext !== 'function') throw new Error('getPageContext is required for a website connection.');
      await updateContext(); const ticket = await options.getToken();
      if (destroyed || attempt !== connectionAttempt) return;
      if (!ticket) throw new Error('The website token endpoint returned no ticket.');
      post({ type: 'agent-connect', site_id: options.siteId, session_id: expectedSession, instance_id: randomId('instance'), ticket, capabilities: Object.keys(adapter), context });
    } catch (error) { if (attempt === connectionAttempt && !destroyed) emitError(error instanceof Error ? error.message : String(error)); }
  };
  const dispatchRequest = (message: Record<string, unknown>) => {
    if (!binding || message.session_id !== sessionId || !message.call_id) return;
    const callId = String(message.call_id); if (calls.has(callId)) return;
    calls.set(callId, (async () => {
      try {
        if (typeof message.deadline === 'number' && Date.now() / 1000 >= message.deadline) throw new Error('Website request expired.');
        const method = String(message.method || ''); const callback = (adapter as Record<string, unknown>)[method];
        if (typeof callback !== 'function') throw new Error(`Website callback is not registered: ${method}`);
        const current = typeof adapter.getPageContext === 'function' ? await adapter.getPageContext() : context;
        if (method !== 'getPageContext' && message.revision && (current as Record<string, unknown>)?.revision !== message.revision) throw new Error('Page changed; read website_context again.');
        const result = await (callback as (args: Record<string, unknown>, request: Record<string, unknown>) => unknown)(message.arguments as Record<string, unknown> || {}, message);
        await updateContext(undefined, { waitForSync: true });
        return { result: result || {} };
      } catch (error) { return { error: { code: 'host_callback_failed', message: error instanceof Error ? error.message : String(error) } }; }
    })());
    void calls.get(callId)?.then(response => { if (!destroyed && message.session_id === sessionId) post({ type: 'agent-website-response', session_id: sessionId, call_id: callId, run_id: message.run_id, revision: message.revision, ...response }); }).finally(() => calls.delete(callId));
  };
  const onMessage = (event: MessageEvent) => {
    if (event.source !== frame.contentWindow || event.origin !== sourceOrigin) return;
    const message = event.data as Record<string, unknown> | null; if (!message) return;
    if (message.type === 'agent-close') closePanel();
    if (message.type === 'agent-ready' || message.type === 'agent-website-retry') {
      const nextSession = String(message.session_id || '');
      if (sessionId !== nextSession || message.type === 'agent-website-retry') {
        sessionId = nextSession; binding = null; connecting = false; connectionAttempt++; clearTimer(); calls.clear();
        for (const waiter of syncWaiters.values()) { window.clearTimeout(waiter.timer); waiter.reject(new Error('Website connection was reset.')); }
        syncWaiters.clear();
      }
      post({ type: 'agent-context', context }); void connect();
    }
    if (message.type === 'agent-website-request') dispatchRequest(message);
    if (message.type === 'agent-website-connected' && message.session_id === sessionId) { binding = { binding_id: String(message.binding_id || '') }; connecting = false; clearTimer(); options.onEvent?.({ type: 'website-connected' }); }
    if (message.type === 'agent-context-updated' && message.session_id === sessionId) {
      const key = String(message.context_update_id || ''); const waiter = syncWaiters.get(key); if (!waiter) return;
      window.clearTimeout(waiter.timer); syncWaiters.delete(key); message.ok === false ? waiter.reject(new Error(String(message.error || 'Website context update failed.'))) : waiter.resolve();
    }
    if (message.type === 'agent-event') options.onEvent?.((message.event || {}) as Record<string, unknown>);
  };
  const open = () => { lastFocus = document.activeElement; panel.hidden = false; launcher.hidden = true; launcher.setAttribute('aria-expanded', 'true'); post({ type: 'agent-context', context }); };
  const closePanel = () => { panel.hidden = true; launcher.hidden = false; launcher.setAttribute('aria-expanded', 'false'); (lastFocus as HTMLElement || launcher).focus?.(); };
  launcher.addEventListener('click', open); close.addEventListener('click', closePanel); window.addEventListener('message', onMessage);
  if (options.open) open();
  return {
    open, close: closePanel,
    updateContext,
    get binding() { return binding ? { binding_id: binding.binding_id } : null; },
    destroy() { destroyed = true; connectionAttempt++; clearTimer(); for (const waiter of syncWaiters.values()) { window.clearTimeout(waiter.timer); waiter.reject(new Error('Assistant drawer was destroyed.')); } syncWaiters.clear(); if (binding) post({ type: 'agent-disconnect' }); window.removeEventListener('message', onMessage); launcher.remove(); panel.remove(); style.remove(); },
  };
}

export const AssistantDrawer = { mount: mountAssistantDrawer };

export function installAssistantDrawerGlobal() {
  (window as Window & { AssistantDrawer?: typeof AssistantDrawer }).AssistantDrawer = AssistantDrawer;
  return AssistantDrawer;
}

if (typeof window !== 'undefined') installAssistantDrawerGlobal();
