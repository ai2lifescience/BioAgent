(() => {
  "use strict";

  const AGENT_ICON = `
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

  const EMBED_STYLE = `
    :host { all: initial; }
    .agent-launcher { position: fixed; right: 22px; bottom: 22px; z-index: 2147483000; display: inline-flex; align-items: center; gap: 8px; border: 1px solid #0d655e; border-radius: 999px; padding: 11px 16px; color: #fff; background: linear-gradient(145deg, #159487, #115e59); box-shadow: 0 10px 26px #17343835; font: 700 13px/1.2 Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; cursor: pointer; transition: transform .18s ease, box-shadow .18s ease; }
    .agent-icon { display: grid; width: 30px; height: 30px; place-items: center; color: #fff; }
    .agent-icon svg { width: 100%; height: 100%; display: block; }
    .agent-launcher:hover { transform: translateY(-2px); box-shadow: 0 14px 30px #17343845; }
    .agent-panel { position: fixed; z-index: 2147483001; inset: 0 0 0 auto; display: grid; grid-template-rows: auto minmax(0,1fr); width: min(460px,100vw); overflow: hidden; border-left: 1px solid #d9e5e4; background: #f4f8f8; box-shadow: -16px 0 40px #17343826; transition: transform .22s ease, box-shadow .22s ease; }
    .agent-panel[hidden] { display: grid; transform: translateX(102%); pointer-events: none; box-shadow: none; }
    .agent-panel-header { display: flex; align-items: center; gap: 10px; min-height: 58px; padding: 11px 16px; border-bottom: 1px solid #d9e5e4; color: #173438; background: #ffffffed; backdrop-filter: blur(12px); font: 700 14px/1.2 Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }
    .agent-panel-header .agent-icon { width: 42px; height: 42px; border-radius: 9px; background: transparent; }
    .agent-panel-header span { margin-right: auto; }
    .agent-close { display: grid; width: 30px; height: 30px; place-items: center; border: 1px solid #d9e5e4; border-radius: 8px; color: #62777b; background: #f4f8f8; font-size: 20px; line-height: 1; cursor: pointer; }
    .agent-close:hover { color: #115e59; background: #e7f4f1; }
    .agent-frame { display: block; width: 100%; height: 100%; border: 0; }
    @media (max-width: 480px) { .agent-launcher { right: 12px; bottom: 12px; padding: 10px 13px; } .agent-panel { width: 100vw; } }
  `;

  function mount(options = {}) {
    const host = options.target || document.body;
    const src = new URL(options.src || "/assistant", window.location.href);
    const parentOrigin = window.location.origin;
    src.searchParams.set("parent_origin", parentOrigin);
    src.searchParams.set("embedded", "1");
    const shadow = host.attachShadow ? host.attachShadow({ mode: "open" }) : host;
    const style = document.createElement("style");
    style.textContent = EMBED_STYLE;
    const launcher = document.createElement("button");
    launcher.className = "agent-launcher";
    launcher.type = "button";
    const launcherIcon = document.createElement("span");
    launcherIcon.className = "agent-icon";
    launcherIcon.innerHTML = AGENT_ICON;
    launcher.append(launcherIcon, document.createTextNode(options.launcherLabel || "Ask assistant"));
    launcher.setAttribute("aria-expanded", "false");
    const panel = document.createElement("aside");
    panel.className = "agent-panel";
    panel.hidden = true;
    panel.setAttribute("aria-label", options.title || "Assistant");
    const panelHeader = document.createElement("div");
    panelHeader.className = "agent-panel-header";
    const headerIcon = document.createElement("span");
    headerIcon.className = "agent-icon";
    headerIcon.innerHTML = AGENT_ICON;
    const panelTitle = document.createElement("span");
    panelTitle.textContent = options.title || "Assistant";
    const close = document.createElement("button");
    close.className = "agent-close";
    close.type = "button";
    close.textContent = "×";
    close.setAttribute("aria-label", "Close assistant");
    const frame = document.createElement("iframe");
    frame.className = "agent-frame";
    frame.title = options.title || "Assistant";
    frame.src = src.toString();
    panelHeader.append(headerIcon, panelTitle, close);
    panel.append(panelHeader, frame);
    shadow.append(style, launcher, panel);
    let lastFocus = null;
    let context = { ...(options.context || {}) };
    const adapter = options.adapter || {};
    const instanceId = (window.crypto && window.crypto.randomUUID) ? window.crypto.randomUUID() : `instance_${Date.now()}_${Math.random()}`;
    let binding = null;
    let connecting = false;
    let destroyed = false;

    function postContext() {
      frame.contentWindow?.postMessage({ type: "agent-context", context }, src.origin);
    }
    async function connectWebsite() {
      if (!options.siteId || typeof options.getToken !== "function" || connecting || binding) return;
      connecting = true;
      try {
        const token = await options.getToken();
        if (destroyed || !token) return;
        frame.contentWindow?.postMessage({ type: "agent-connect", protocol: 1, site_id: options.siteId,
          instance_id: instanceId, ticket: token, capabilities: Object.keys(adapter), context }, src.origin);
      } catch (error) {
        options.onEvent?.({ type: "website-error", error: String(error?.message || error) });
      } finally { connecting = false; }
    }
    async function dispatchWebsiteRequest(message) {
      const method = String(message.method || "");
      const callback = adapter[method];
      if (typeof callback !== "function") {
        frame.contentWindow?.postMessage({ type: "agent-website-response", call_id: message.call_id,
          run_id: message.run_id, revision: message.revision, error: { code: "unsupported", message: `Website callback is not registered: ${method}` } }, src.origin);
        return;
      }
      try {
        const result = await callback(message.arguments || {}, message);
        frame.contentWindow?.postMessage({ type: "agent-website-response", call_id: message.call_id,
          run_id: message.run_id, revision: message.revision, result: result || {} }, src.origin);
      } catch (error) {
        frame.contentWindow?.postMessage({ type: "agent-website-response", call_id: message.call_id,
          run_id: message.run_id, revision: message.revision,
          error: { code: "host_callback_failed", message: String(error?.message || error) } }, src.origin);
      }
    }
    function open() {
      lastFocus = document.activeElement;
      panel.hidden = false;
      launcher.hidden = true;
      launcher.setAttribute("aria-expanded", "true");
      postContext();
    }
    function closePanel() {
      panel.hidden = true;
      launcher.hidden = false;
      launcher.setAttribute("aria-expanded", "false");
      (lastFocus || launcher).focus();
    }
    async function updateContext(nextContext = {}) {
      const value = nextContext && Object.keys(nextContext).length ? nextContext : (adapter.getPageContext ? await adapter.getPageContext() : {});
      context = { ...(value || {}) };
      postContext();
      return context;
    }
    function onMessage(event) {
      if (event.source !== frame.contentWindow || event.origin !== src.origin) return;
      if (event.data?.type === "agent-close") closePanel();
      if (event.data?.type === "agent-ready") { postContext(); connectWebsite(); }
      if (event.data?.type === "agent-website-request") dispatchWebsiteRequest(event.data);
      if (event.data?.type === "agent-website-connected") binding = { binding_id: event.data.binding_id };
    }
    launcher.addEventListener("click", open);
    close.addEventListener("click", closePanel);
    frame.addEventListener("load", () => { postContext(); connectWebsite(); });
    window.addEventListener("message", onMessage);
    if (options.open) open();
    return {
      open,
      close: closePanel,
      updateContext,
      get binding() { return binding; },
      destroy() {
        destroyed = true;
        if (binding) frame.contentWindow?.postMessage({ type: "agent-disconnect" }, src.origin);
        window.removeEventListener("message", onMessage);
        launcher.remove();
        panel.remove();
        style.remove();
      },
    };
  }

  const AssistantDrawer = { mount };
  window.AssistantDrawer = AssistantDrawer;
})();
