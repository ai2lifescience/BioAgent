(() => {
  "use strict";

  const EMBED_STYLE = `
    :host { all: initial; }
    .bioagent-launcher { position: fixed; right: 20px; bottom: 20px; z-index: 2147483000; border: 0; border-radius: 999px; padding: 12px 16px; color: #fff; background: #0f766e; box-shadow: 0 8px 24px #172e3240; font: 650 14px/1.2 system-ui,sans-serif; cursor: pointer; }
    .bioagent-launcher:hover { background: #115e59; }
    .bioagent-panel { position: fixed; z-index: 2147483001; inset: 0 0 0 auto; display: grid; grid-template-rows: auto minmax(0,1fr); width: min(440px,100vw); background: #fff; box-shadow: -12px 0 32px #172e3226; transition: transform .2s ease; }
    .bioagent-panel[hidden] { display: grid; transform: translateX(102%); pointer-events: none; }
    .bioagent-panel-header { display: flex; align-items: center; gap: 10px; min-height: 52px; padding: 10px 14px; border-bottom: 1px solid #dce6e6; color: #172e32; background: #fff; font: 650 14px/1.2 system-ui,sans-serif; }
    .bioagent-panel-header span { margin-right: auto; }
    .bioagent-close { width: 30px; height: 30px; border: 0; border-radius: 7px; color: #62777b; background: #f5f8f8; font-size: 22px; line-height: 1; cursor: pointer; }
    .bioagent-frame { display: block; width: 100%; height: 100%; border: 0; }
    @media (max-width: 480px) { .bioagent-launcher { right: 12px; bottom: 12px; } .bioagent-panel { width: 100vw; } }
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
    launcher.className = "bioagent-launcher";
    launcher.type = "button";
    launcher.textContent = options.launcherLabel || "Ask BioAgent";
    launcher.setAttribute("aria-expanded", "false");
    const panel = document.createElement("aside");
    panel.className = "bioagent-panel";
    panel.hidden = true;
    panel.setAttribute("aria-label", options.title || "BioAgent assistant");
    const panelHeader = document.createElement("div");
    panelHeader.className = "bioagent-panel-header";
    const panelTitle = document.createElement("span");
    panelTitle.textContent = options.title || "BioAgent";
    const close = document.createElement("button");
    close.className = "bioagent-close";
    close.type = "button";
    close.textContent = "×";
    close.setAttribute("aria-label", "Close BioAgent");
    const frame = document.createElement("iframe");
    frame.className = "bioagent-frame";
    frame.title = options.title || "BioAgent assistant";
    frame.src = src.toString();
    panelHeader.append(panelTitle, close);
    panel.append(panelHeader, frame);
    shadow.append(style, launcher, panel);
    let lastFocus = null;
    let context = { ...(options.context || {}) };

    function postContext() {
      frame.contentWindow?.postMessage({ type: "bioagent-context", context }, parentOrigin);
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
    function updateContext(nextContext = {}) {
      context = { ...nextContext };
      postContext();
    }
    function onMessage(event) {
      if (event.source !== frame.contentWindow || event.origin !== src.origin) return;
      if (event.data?.type === "bioagent-close") closePanel();
      if (event.data?.type === "bioagent-ready") postContext();
    }
    launcher.addEventListener("click", open);
    close.addEventListener("click", closePanel);
    frame.addEventListener("load", postContext);
    window.addEventListener("message", onMessage);
    if (options.open) open();
    return {
      open,
      close: closePanel,
      updateContext,
      destroy() {
        window.removeEventListener("message", onMessage);
        launcher.remove();
        panel.remove();
        style.remove();
      },
    };
  }

  window.BioAgentDrawer = { mount };
})();
