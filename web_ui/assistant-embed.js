(() => {
  "use strict";

  const EMBED_STYLE = `
    :host { all: initial; }
    .bioagent-launcher { position: fixed; right: 22px; bottom: 22px; z-index: 2147483000; display: inline-flex; align-items: center; gap: 8px; border: 1px solid #0d655e; border-radius: 999px; padding: 11px 16px; color: #fff; background: linear-gradient(145deg, #159487, #115e59); box-shadow: 0 10px 26px #17343835; font: 700 13px/1.2 system-ui,sans-serif; cursor: pointer; transition: transform .18s ease, box-shadow .18s ease; }
    .bioagent-launcher::before { display: grid; width: 20px; height: 20px; place-items: center; border: 1px solid #ffffff70; border-radius: 7px; content: "BA"; font-size: 8px; font-weight: 800; }
    .bioagent-launcher:hover { transform: translateY(-2px); box-shadow: 0 14px 30px #17343845; }
    .bioagent-panel { position: fixed; z-index: 2147483001; inset: 0 0 0 auto; display: grid; grid-template-rows: auto minmax(0,1fr); width: min(460px,100vw); overflow: hidden; border-left: 1px solid #d9e5e4; background: #f4f8f8; box-shadow: -16px 0 40px #17343826; transition: transform .22s ease, box-shadow .22s ease; }
    .bioagent-panel[hidden] { display: grid; transform: translateX(102%); pointer-events: none; box-shadow: none; }
    .bioagent-panel-header { display: flex; align-items: center; gap: 10px; min-height: 58px; padding: 11px 16px; border-bottom: 1px solid #d9e5e4; color: #173438; background: #ffffffed; backdrop-filter: blur(12px); font: 700 14px/1.2 system-ui,sans-serif; }
    .bioagent-panel-header::before { display: grid; width: 28px; height: 28px; place-items: center; border-radius: 9px; color: #fff; background: linear-gradient(145deg, #159487, #115e59); content: "BA"; font-size: 9px; }
    .bioagent-panel-header span { margin-right: auto; }
    .bioagent-close { display: grid; width: 30px; height: 30px; place-items: center; border: 1px solid #d9e5e4; border-radius: 8px; color: #62777b; background: #f4f8f8; font-size: 20px; line-height: 1; cursor: pointer; }
    .bioagent-close:hover { color: #115e59; background: #e7f4f1; }
    .bioagent-frame { display: block; width: 100%; height: 100%; border: 0; }
    @media (max-width: 480px) { .bioagent-launcher { right: 12px; bottom: 12px; padding: 10px 13px; } .bioagent-panel { width: 100vw; } }
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
