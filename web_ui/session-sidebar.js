import { escapeHtml } from "/static/ui-utils.js";

const PIN_ICON = `
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <path d="m9 4 6 0 1 5 3 3v1H5v-1l3-3 1-5Z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>
    <path d="M12 13v7" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
  </svg>`;
const EDIT_ICON = `
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <path d="m4 16.5-.8 4.3 4.3-.8L19 8.5 15.5 5 4 16.5Z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>
    <path d="m13.8 6.7 3.5 3.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
  </svg>`;
const MORE_ICON = `
  <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
    <circle cx="5" cy="12" r="1.7"/><circle cx="12" cy="12" r="1.7"/><circle cx="19" cy="12" r="1.7"/>
  </svg>`;

function formatSessionTime(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function formatSessionMeta(session) {
  const time = formatSessionTime(session.updated_at) || "No activity";
  const count = Number(session.message_count || 0);
  return `${time} · ${count === 1 ? "1 message" : `${count} messages`}`;
}

export function createSessionSidebar({ sessionList, sessionCount, sessionStore } = {}) {
  function sortedSessions() {
    return [...sessionStore.sessions].sort((left, right) => {
      if (left.pinned !== right.pinned) return left.pinned ? -1 : 1;
      return new Date(right.updated_at).getTime() - new Date(left.updated_at).getTime();
    });
  }

  function closeMenus() {
    sessionList.querySelectorAll(".session-menu:not([hidden])").forEach((menu) => {
      menu.hidden = true;
      menu.parentElement?.querySelector("[data-session-menu]")?.setAttribute("aria-expanded", "false");
    });
  }

  function openMenu(item, button) {
    const menu = item.querySelector(".session-menu");
    if (!menu) return;
    const wasOpen = !menu.hidden;
    closeMenus();
    if (wasOpen) return;
    menu.hidden = false;
    const buttonRect = button.getBoundingClientRect();
    const menuRect = menu.getBoundingClientRect();
    menu.style.left = `${Math.max(8, Math.min(buttonRect.right - menuRect.width, window.innerWidth - menuRect.width - 8))}px`;
    menu.style.top = `${Math.max(8, Math.min(buttonRect.bottom + 4, window.innerHeight - menuRect.height - 8))}px`;
    button.setAttribute("aria-expanded", "true");
    menu.querySelector("[role=menuitem]")?.focus();
  }

  function render() {
    sessionCount.textContent = String(sessionStore.sessions.length);
    sessionList.replaceChildren();
    if (!sessionStore.sessions.length) {
      sessionList.innerHTML = `<div class="session-empty">No saved chats.</div>`;
      return;
    }
    for (const session of sortedSessions()) {
      const item = document.createElement("div");
      item.className = `session-item ${session.id === sessionStore.activeSessionId ? "active" : ""} ${session.pinned ? "pinned" : ""}`;
      item.dataset.sessionId = session.id;
      item.innerHTML = `
        <button class="session-select" type="button">
          <span class="session-title-row">
            <span class="session-title">${escapeHtml(session.title || "New chat")}</span>
            ${session.pinned ? `<span class="session-pinned-badge" aria-label="Pinned">${PIN_ICON}</span>` : ""}
          </span>
          <span class="session-meta">${escapeHtml(formatSessionMeta(session))}</span>
        </button>
        <div class="session-actions">
          <button class="session-more" type="button" data-session-menu aria-haspopup="menu" aria-expanded="false" aria-label="Actions for ${escapeHtml(session.title || "session")}" title="Session actions">${MORE_ICON}</button>
          <div class="session-menu" role="menu" hidden>
            <button class="session-menu-item" type="button" role="menuitem" data-session-pin aria-pressed="${session.pinned ? "true" : "false"}">${PIN_ICON}<span>${session.pinned ? "Unpin chat" : "Pin chat"}</span></button>
            <button class="session-menu-item" type="button" role="menuitem" data-session-rename>${EDIT_ICON}<span>Rename chat</span></button>
            <button class="session-menu-item session-menu-delete" type="button" role="menuitem" data-session-delete><span class="session-menu-x" aria-hidden="true">&times;</span><span>Delete chat</span></button>
          </div>
        </div>`;
      sessionList.appendChild(item);
    }
  }

  return { render, closeMenus, openMenu };
}
