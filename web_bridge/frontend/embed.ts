import { createPageObserver } from './observer';
export type WebsiteAdapter = Record<string, (arguments_: Record<string, unknown>, request?: Record<string, unknown>) => unknown | Promise<unknown>> & {
  getPageContext?: () => unknown | Promise<unknown>;
};

export interface AssistantDrawerOptions {
  target?: HTMLElement;
  src?: string;
  siteId?: string;
  getToken?: () => Promise<string>;
  getAuthorization?: () => Promise<{ code: string }>;
  adapter?: WebsiteAdapter;
  context?: Record<string, unknown>;
  title?: string;
  launcherLabel?: string;
  open?: boolean;
  defaultWidth?: number;
  minWidth?: number;
  resizable?: boolean;
  allowFullscreen?: boolean;
  fullscreen?: boolean;
  customCss?: string;
  onEvent?: (event: Record<string, unknown>) => void;
}

export interface AssistantDrawerHandle {
  open(): void;
  close(): void;
  setWidth(width: number): void;
  setFullscreen(fullscreen: boolean): void;
  setCustomCss(css: string): void;
  refreshFiles(): void;
  updateContext(context?: Record<string, unknown>, options?: { waitForSync?: boolean }): Promise<Record<string, unknown>>;
  readonly binding: { binding_id: string } | null;
  destroy(): void;
}

const PROTOCOL = 1;
const CSS = `
    :host { all: initial; }
    .agent-launcher { position: fixed; right: 22px; bottom: 22px; z-index: 2147483000; display: inline-flex; align-items: center; gap: 8px; border: 1px solid #0d655e; border-radius: 999px; padding: 11px 16px; color: #fff; background: linear-gradient(145deg, #159487, #115e59); box-shadow: 0 10px 26px #17343835; font: 700 13px/1.2 Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; cursor: pointer; transition: transform .18s ease, box-shadow .18s ease; }
    .agent-icon { display: grid; width: 30px; height: 30px; place-items: center; color: #fff; }
    .agent-icon svg { width: 100%; height: 100%; display: block; }
    .agent-launcher:hover { transform: translateY(-2px); box-shadow: 0 14px 30px #17343845; }
    .agent-panel { position: fixed; z-index: 2147483001; inset: 0 0 0 auto; display: grid; grid-template-rows: auto minmax(0,1fr); width: min(var(--agent-panel-width, 460px), 100vw); overflow: hidden; border-left: 1px solid #d9e5e4; background: #f4f8f8; box-shadow: -16px 0 40px #17343826; transition: transform .22s ease, box-shadow .22s ease, width .18s ease; }
    .agent-panel.is-resizing { transition: none; user-select: none; }
    .agent-panel.is-resizing .agent-frame { pointer-events: none; }
    .agent-panel.is-fullscreen { width: 100vw; border-left: 0; box-shadow: none; }
    .agent-panel[hidden] { display: grid; transform: translateX(102%); pointer-events: none; box-shadow: none; }
    .agent-resizer { position: absolute; top: 0; bottom: 0; left: 0; width: 8px; z-index: 2; cursor: ew-resize; touch-action: none; background: transparent; }
    .agent-resizer::after { content: ''; position: absolute; top: 0; bottom: 0; left: 2px; width: 3px; border-radius: 999px; background: transparent; transition: background-color .15s ease; }
    .agent-resizer:hover::after, .agent-resizer:focus-visible::after, .agent-panel.is-resizing .agent-resizer::after { background: #159487; }
    .agent-resizer:focus-visible { outline: none; }
    .agent-panel.is-fullscreen .agent-resizer { display: none; }
    .agent-panel-header { display: flex; align-items: center; gap: 10px; min-height: 58px; padding: 11px 16px; border-bottom: 1px solid #d9e5e4; color: #173438; background: #ffffffed; backdrop-filter: blur(12px); font: 700 14px/1.2 Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }
    .agent-panel-header .agent-icon { width: 42px; height: 42px; border-radius: 9px; background: transparent; }
    .agent-panel-title { margin-right: auto; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .agent-panel-actions { display: inline-flex; align-items: center; gap: 6px; flex: 0 0 auto; }
    .agent-header-btn { display: grid; width: 30px; height: 30px; padding: 0; place-items: center; border: 1px solid #d9e5e4; border-radius: 8px; color: #62777b; background: #f4f8f8; font-size: 20px; line-height: 1; cursor: pointer; transition: color .15s ease, background-color .15s ease, border-color .15s ease; }
    .agent-header-btn:hover { color: #115e59; background: #e7f4f1; border-color: #b7d7d3; }
    .agent-header-btn:focus-visible { outline: 2px solid #159487; outline-offset: 2px; }
    .agent-expand svg { width: 15px; height: 15px; display: block; }
    .agent-frame { display: block; width: 100%; height: 100%; border: 0; }
    @media (max-width: 480px) { .agent-launcher { right: 12px; bottom: 12px; padding: 10px 13px; } .agent-panel { width: 100vw; } .agent-resizer, .agent-expand { display: none; } }
  `;

const EXPAND_ICON = `<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9.5 2.5h4v4"/><path d="M13.5 2.5L8.75 7.25"/><path d="M6.5 13.5h-4v-4"/><path d="M2.5 13.5l4.75-4.75"/></svg>`;
const RESTORE_ICON = `<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9.5 3.5v3h3"/><path d="M13.5 2.5L9.5 6.5"/><path d="M6.5 12.5v-3h-3"/><path d="M2.5 13.5l4-4"/></svg>`;

function randomId(prefix: string) {
  const uuid = globalThis.crypto?.randomUUID?.();
  return `${prefix}_${uuid || `${Date.now()}_${Math.random().toString(36).slice(2)}`}`;
}

function createAgentIcon(size: number) {
  const icon = document.createElement('span');
  icon.className = 'agent-icon';
  icon.setAttribute('aria-hidden', 'true');
  icon.innerHTML = `
    <svg viewBox="0 0 512 512" fill="none" aria-hidden="true">
      <defs><linearGradient id="bsod-screen-embed" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#159BEA"/><stop offset="1" stop-color="#1486D8"/></linearGradient></defs>
      <path d="M256 112c-4-38 10-58 34-67" stroke="#25283A" stroke-width="10" stroke-linecap="round"/>
      <circle cx="300" cy="40" r="18" fill="#159BEA" stroke="#25283A" stroke-width="8"/>
      <rect x="79" y="164" width="35" height="118" rx="17" fill="#D3D2D1" stroke="#25283A" stroke-width="9"/>
      <rect x="398" y="164" width="35" height="118" rx="17" fill="#D3D2D1" stroke="#25283A" stroke-width="9"/>
      <rect x="101" y="126" width="310" height="213" rx="48" fill="url(#bsod-screen-embed)" stroke="#25283A" stroke-width="10"/>
      <path d="M128 162c23-19 52-27 87-27h94c34 0 62 8 77 25" stroke="#63C6F3" stroke-width="9" stroke-linecap="round" opacity=".7"/>
      <rect x="181" y="204" width="13" height="52" rx="6.5" fill="#202332"/>
      <rect x="318" y="204" width="13" height="52" rx="6.5" fill="#202332"/>
      <ellipse cx="166" cy="275" rx="23" ry="12" fill="#F58FAE"/>
      <ellipse cx="346" cy="275" rx="23" ry="12" fill="#F58FAE"/>
      <path d="M241 275c7 9 23 9 30 0" stroke="#63D2F5" stroke-width="8" stroke-linecap="round"/>
      <path d="M104 319c-23 17-28 44-14 61 9 11 23 11 30 1l20-31" fill="#D3D2D1" stroke="#25283A" stroke-width="9" stroke-linecap="round" stroke-linejoin="round"/>
      <path d="M408 319c23 17 28 44 14 61-9 11-23 11-30 1l-20-31" fill="#D3D2D1" stroke="#25283A" stroke-width="9" stroke-linecap="round" stroke-linejoin="round"/>
      <rect x="171" y="331" width="170" height="105" rx="25" fill="#F1F0ED" stroke="#25283A" stroke-width="9"/>
      <rect x="224" y="352" width="64" height="53" rx="8" fill="#168EDC" stroke="#25283A" stroke-width="7"/>
      <rect x="244" y="368" width="24" height="18" rx="3" fill="#82D8F5"/>
      <path d="M190 433v39c0 9 7 16 16 16h31v-55" fill="#C9C8C6" stroke="#25283A" stroke-width="9" stroke-linejoin="round"/>
      <path d="M322 433v39c0 9-7 16-16 16h-31v-55" fill="#C9C8C6" stroke="#25283A" stroke-width="9" stroke-linejoin="round"/>
    </svg>`;
  return icon;
}

export function mountAssistantDrawer(options: AssistantDrawerOptions = {}): AssistantDrawerHandle {
  const ownedHost = !options.target;
  const host = options.target || document.createElement('div');
  if (ownedHost) document.body.appendChild(host);
  const src = new URL(options.src || '/assistant', window.location.href);
  if (!['http:', 'https:'].includes(src.protocol)) throw new Error('Assistant source must use HTTP or HTTPS.');
  const sourceOrigin = src.origin;
  const parentOrigin = window.location.origin;
  src.searchParams.set('parent_origin', parentOrigin);
  src.searchParams.set('embedded', '1');
  if (options.siteId) src.searchParams.set('website_site', options.siteId);
  if (options.getAuthorization) src.searchParams.set('website_auth', '1');
  const shadow = host.shadowRoot || (host.attachShadow ? host.attachShadow({ mode: 'open' }) : host);
  const style = document.createElement('style'); style.textContent = CSS;
  const launcher = document.createElement('button'); launcher.className = 'agent-launcher'; launcher.type = 'button'; launcher.setAttribute('aria-expanded', 'false');
  const icon = createAgentIcon(28);
  launcher.append(icon, document.createTextNode(options.launcherLabel || 'Ask assistant'));
  const panel = document.createElement('aside'); panel.className = 'agent-panel'; panel.hidden = true; panel.setAttribute('aria-label', options.title || 'Assistant');
  const defaultWidth = Math.max(280, Math.round(Number(options.defaultWidth) || 460));
  const minWidth = Math.max(280, Math.min(defaultWidth, Math.round(Number(options.minWidth) || 320)));
  const resizable = options.resizable !== false;
  const allowFullscreen = options.allowFullscreen !== false;
  const widthStorageKey = `bioagent-assistant-width:${options.siteId || 'default'}`;
  const clampWidth = (width: number) => {
    const viewport = window.innerWidth || defaultWidth;
    return Math.max(Math.min(minWidth, viewport), Math.min(Math.round(width), viewport));
  };
  const loadSavedWidth = () => {
    try {
      const raw = Number(window.localStorage?.getItem(widthStorageKey));
      return Number.isFinite(raw) && raw > 0 ? raw : null;
    } catch { return null; }
  };
  const saveWidth = (width: number) => {
    try { window.localStorage?.setItem(widthStorageKey, String(Math.round(width))); } catch { /* Ignore storage errors. */ }
  };
  let panelWidth = clampWidth(loadSavedWidth() ?? defaultWidth);
  let isFullscreen = Boolean(options.fullscreen && allowFullscreen);
  const resizer = resizable ? document.createElement('div') : null;
  if (resizer) {
    resizer.className = 'agent-resizer';
    resizer.setAttribute('role', 'separator');
    resizer.setAttribute('aria-orientation', 'vertical');
    resizer.setAttribute('aria-label', 'Resize assistant panel');
    resizer.setAttribute('title', 'Drag to resize (double-click to reset)');
    resizer.tabIndex = 0;
  }
  const header = document.createElement('div'); header.className = 'agent-panel-header';
  const panelIcon = createAgentIcon(30);
  const title = document.createElement('span'); title.className = 'agent-panel-title'; title.textContent = options.title || 'Assistant';
  const actions = document.createElement('div'); actions.className = 'agent-panel-actions';
  const expand = allowFullscreen ? document.createElement('button') : null;
  if (expand) { expand.className = 'agent-header-btn agent-expand'; expand.type = 'button'; }
  const close = document.createElement('button'); close.className = 'agent-header-btn agent-close'; close.type = 'button'; close.textContent = '×'; close.setAttribute('aria-label', 'Close assistant'); close.title = 'Close assistant';
  const frame = document.createElement('iframe'); frame.className = 'agent-frame'; frame.title = options.title || 'Assistant'; frame.src = src.toString();
  if (expand) actions.append(expand);
  actions.append(close);
  header.append(panelIcon, title, actions);
  if (resizer) panel.append(resizer);
  panel.append(header, frame); shadow.append(style, launcher, panel);

  const applyWidth = (width: number, persist = false) => {
    panelWidth = clampWidth(width);
    panel.style.setProperty('--agent-panel-width', `${panelWidth}px`);
    if (resizer) {
      resizer.setAttribute('aria-valuemin', String(minWidth));
      resizer.setAttribute('aria-valuemax', String(Math.max(minWidth, window.innerWidth || defaultWidth)));
      resizer.setAttribute('aria-valuenow', String(panelWidth));
    }
    if (persist) saveWidth(panelWidth);
  };
  const setFullscreen = (next: boolean) => {
    isFullscreen = allowFullscreen ? Boolean(next) : false;
    panel.classList.toggle('is-fullscreen', isFullscreen);
    if (expand) {
      expand.innerHTML = isFullscreen ? RESTORE_ICON : EXPAND_ICON;
      const label = isFullscreen ? 'Restore drawer width' : 'Expand to full page';
      expand.setAttribute('aria-label', label);
      expand.setAttribute('aria-pressed', String(isFullscreen));
      expand.title = label;
    }
  };
  const setWidth = (width: number) => {
    if (!Number.isFinite(width)) return;
    if (isFullscreen) setFullscreen(false);
    applyWidth(width, true);
  };
  applyWidth(panelWidth);
  setFullscreen(isFullscreen);

  let resizeState: { pointerId: number; startX: number; startWidth: number } | null = null;
  const onResizeMove = (event: PointerEvent) => {
    if (!resizeState || event.pointerId !== resizeState.pointerId) return;
    applyWidth(resizeState.startWidth + (resizeState.startX - event.clientX));
  };
  const finishResize = (event?: PointerEvent) => {
    if (!resizeState) return;
    if (event && event.pointerId !== resizeState.pointerId) return;
    const pointerId = resizeState.pointerId;
    resizeState = null;
    panel.classList.remove('is-resizing');
    try { if (resizer?.hasPointerCapture?.(pointerId)) resizer.releasePointerCapture(pointerId); } catch { /* Ignore capture release errors. */ }
    window.removeEventListener('pointermove', onResizeMove);
    window.removeEventListener('pointerup', finishResize);
    window.removeEventListener('pointercancel', finishResize);
    window.removeEventListener('blur', onWindowBlur);
    saveWidth(panelWidth);
  };
  const onWindowBlur = () => finishResize();
  if (resizer) {
    resizer.addEventListener('pointerdown', (event: PointerEvent) => {
      if (isFullscreen || (event.pointerType === 'mouse' && event.button !== 0)) return;
      event.preventDefault();
      resizeState = { pointerId: event.pointerId, startX: event.clientX, startWidth: panel.getBoundingClientRect().width || panelWidth };
      panel.classList.add('is-resizing');
      try { resizer.setPointerCapture?.(event.pointerId); } catch { /* Fallback to window listeners. */ }
      window.addEventListener('pointermove', onResizeMove);
      window.addEventListener('pointerup', finishResize);
      window.addEventListener('pointercancel', finishResize);
      window.addEventListener('blur', onWindowBlur);
    });
    resizer.addEventListener('dblclick', () => { if (!isFullscreen) applyWidth(defaultWidth, true); });
    resizer.addEventListener('keydown', (event: KeyboardEvent) => {
      if (isFullscreen) return;
      const step = event.shiftKey ? 80 : 32;
      if (event.key === 'ArrowLeft') { event.preventDefault(); applyWidth(panelWidth + step, true); }
      else if (event.key === 'ArrowRight') { event.preventDefault(); applyWidth(panelWidth - step, true); }
      else if (event.key === 'Home') { event.preventDefault(); applyWidth(window.innerWidth || defaultWidth, true); }
      else if (event.key === 'End' || event.key === 'Enter' || event.key === ' ') { event.preventDefault(); applyWidth(defaultWidth, true); }
    });
  }
  if (expand) expand.addEventListener('click', () => setFullscreen(!isFullscreen));
  const onWindowResize = () => { if (!isFullscreen) applyWidth(panelWidth); };
  window.addEventListener('resize', onWindowResize);

  let destroyed = false;
  let connectionAttempt = 0;
  let connecting = false;
  let sessionId: string | null = null;
  let binding: { binding_id: string; token?: string; session_id?: string; site_id?: string } | null = null;
  let lastFocus: Element | null = null;
  let context: Record<string, unknown> = { ...(options.context || {}) };
  let connectionTimer: number | null = null;
  let updateSequence = 0;
  let lastContextMessage = '';
  const calls = new Map<string, Promise<{ result?: unknown; error?: unknown }>>();
  const syncWaiters = new Map<string, { resolve: () => void; reject: (error: Error) => void; timer: number }>();
  const supplied = options.adapter || {};
  const observer = createPageObserver(host === document.body ? panel : host, () => { if (!destroyed) void updateContext().catch(() => {}); });
  const adapter: WebsiteAdapter = {
    ...supplied,
    observePage: () => observer.snapshot(),
    getPageContext: async () => {
      const observedUrl = location.href;
      let extra: unknown = options.context || {};
      if (supplied.getPageContext) {
        let timeout = 0;
        try { extra = await Promise.race([supplied.getPageContext(), new Promise((_, reject) => { timeout = window.setTimeout(() => reject(new Error('Structured context timed out')), 2000); })]); }
        catch { extra = { structured_context_status: 'unavailable' }; }
        finally { clearTimeout(timeout); }
      }
      if (location.href !== observedUrl) extra = {};
      const page = observer.snapshot();
      page.visible_text = page.visible_text.slice(0, 4000);
      page.controls = page.controls.slice(0, 20);
      const details = extra && typeof extra === 'object' ? extra as Record<string, unknown> : {};
      return { ...details, ...page, revision: page.revision + ':' + String(details.revision || '') };
    },
    readTable: (args, request) => String(args.resource_id).startsWith('dom:') ? observer.table(args) : supplied.readTable?.(args, request),
    exportData: (args, request) => String(args.resource_id).startsWith('dom:') ? observer.exportData(args) : supplied.exportData?.(args, request),
  };

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
    context = next ? { ...next, ...observer.snapshot() } : await contextSnapshot();
    const serialized = JSON.stringify(context);
    if (updateOptions.waitForSync && binding) await sendContextAndWait();
    else if (serialized !== lastContextMessage) post({ type: 'agent-context', context });
    lastContextMessage = serialized;
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
    const callId = String(message.call_id);
    if (!calls.has(callId)) calls.set(callId, (async () => {
      try {
        if (typeof message.deadline === 'number' && Date.now() / 1000 >= message.deadline) throw new Error('Website request expired.');
        const method = String(message.method || ''); const callback = (adapter as Record<string, unknown>)[method];
        if (!Object.hasOwn(adapter, method) || typeof callback !== 'function') throw new Error(`Website callback is not registered: ${method}`);
        const current = ['getPageContext', 'observePage'].includes(method) ? context : await contextSnapshot();
        if (!['getPageContext', 'observePage'].includes(method) && message.revision && (current as Record<string, unknown>)?.revision !== message.revision) throw new Error('Page changed; read website_context again.');
        const result = await (callback as (args: Record<string, unknown>, request: Record<string, unknown>) => unknown)(message.arguments as Record<string, unknown> || {}, message);
        await updateContext(undefined, { waitForSync: true });
        return { result: result || {} };
      } catch (error) { return { error: { code: 'host_callback_failed', message: error instanceof Error ? error.message : String(error) } }; }
    })());
    void calls.get(callId)?.then(response => { if (!destroyed && message.session_id === sessionId) post({ type: 'agent-website-response', session_id: sessionId, call_id: callId, run_id: message.run_id, revision: message.revision, ...response }); });
  };
  let customCss = typeof options.customCss === 'string' ? options.customCss : '';
  const setCustomCss = (css: string) => {
    customCss = typeof css === 'string' ? css : '';
    post({ type: 'agent-style', css: customCss });
  };
  const onFrameLoad = () => { if (customCss) post({ type: 'agent-style', css: customCss }); };
  const onMessage = (event: MessageEvent) => {
    if (event.source !== frame.contentWindow || event.origin !== sourceOrigin) return;
    const message = event.data as Record<string, unknown> | null; if (!message) return;
    if (message.type === 'agent-style-request' && customCss) {
      post({ type: 'agent-style', css: customCss });
      return;
    }
    if (message.type === 'agent-auth-required' && options.getAuthorization) {
      if (!message.refresh) {
        binding = null; connecting = false; connectionAttempt++; clearTimer();
      }
      void options.getAuthorization().then(value => { if (!destroyed) post({ type: 'agent-authenticate', code: value.code }); })
        .catch(error => {
          if (destroyed) return;
          binding = null; connecting = false; connectionAttempt++; clearTimer();
          post({ type: 'agent-auth-error', message: String(error.message || error) });
        });
    }
    if (message.type === 'agent-close') closePanel();
    if (message.type === 'agent-ready' || message.type === 'agent-website-retry') {
      const nextSession = String(message.session_id || '');
      if (sessionId !== nextSession || message.type === 'agent-website-retry') {
        sessionId = nextSession; binding = null; connecting = false; connectionAttempt++; clearTimer(); calls.clear();
        for (const waiter of syncWaiters.values()) { window.clearTimeout(waiter.timer); waiter.reject(new Error('Website connection was reset.')); }
        syncWaiters.clear();
      }
      if (customCss) post({ type: 'agent-style', css: customCss });
      post({ type: 'agent-context', context }); void connect();
    }
    if (message.type === 'agent-website-request') dispatchRequest(message);
    if (message.type === 'agent-website-connected' && message.session_id === sessionId) { binding = { binding_id: String(message.binding_id || '') }; connecting = false; clearTimer(); options.onEvent?.({ type: 'website-connected', session_id: sessionId }); }
    if (message.type === 'agent-context-updated' && message.session_id === sessionId) {
      const key = String(message.context_update_id || ''); const waiter = syncWaiters.get(key); if (!waiter) return;
      window.clearTimeout(waiter.timer); syncWaiters.delete(key); message.ok === false ? waiter.reject(new Error(String(message.error || 'Website context update failed.'))) : waiter.resolve();
    }
    if (message.type === 'agent-event') options.onEvent?.((message.event || {}) as Record<string, unknown>);
  };
  const open = () => { lastFocus = document.activeElement; panel.hidden = false; launcher.hidden = true; launcher.setAttribute('aria-expanded', 'true'); post({ type: 'agent-context', context }); };
  const closePanel = () => { panel.hidden = true; launcher.hidden = false; launcher.setAttribute('aria-expanded', 'false'); (lastFocus as HTMLElement || launcher).focus?.(); };
  launcher.addEventListener('click', open); close.addEventListener('click', closePanel); frame.addEventListener('load', onFrameLoad); window.addEventListener('message', onMessage);
  if (options.open) open();
  return {
    open, close: closePanel, setWidth, setFullscreen, setCustomCss,
    refreshFiles() { post({ type: 'agent-files-changed', session_id: sessionId }); },
    updateContext,
    get binding() { return binding ? { binding_id: binding.binding_id } : null; },
    destroy() { finishResize(); window.removeEventListener('resize', onWindowResize); frame.removeEventListener('load', onFrameLoad); observer.destroy(); destroyed = true; connectionAttempt++; clearTimer(); for (const waiter of syncWaiters.values()) { window.clearTimeout(waiter.timer); waiter.reject(new Error('Assistant drawer was destroyed.')); } syncWaiters.clear(); if (binding) post({ type: 'agent-disconnect' }); window.removeEventListener('message', onMessage); launcher.remove(); panel.remove(); style.remove(); if (ownedHost) host.remove(); },
  };
}

export const AssistantDrawer = { mount: mountAssistantDrawer };

export function installAssistantDrawerGlobal() {
  (window as Window & { AssistantDrawer?: typeof AssistantDrawer }).AssistantDrawer = AssistantDrawer;
  return AssistantDrawer;
}

if (typeof window !== 'undefined') installAssistantDrawerGlobal();
