import { generateSessionId, nowIso } from "/static/ui-utils.js";

const DEFAULT_ACTIVE_SESSION_KEY = "agent.web.active_session_id.v1";

function createSession(title = "New chat") {
  const timestamp = nowIso();
  return {
    id: generateSessionId(),
    title,
    messages: [],
    message_count: 0,
    created_at: timestamp,
    updated_at: timestamp,
    pinned: false,
  };
}

function normalizeSession(raw) {
  const id = raw?.session_id;
  if (!id) return null;
  return {
    id: String(id),
    title: String(raw.title || "New chat"),
    messages: [],
    message_count: Number(raw.message_count || 0),
    created_at: raw.created_at || nowIso(),
    updated_at: raw.updated_at || raw.created_at || nowIso(),
    pinned: Boolean(raw.pinned),
  };
}

export function createSessionState({ api, storage = window.localStorage, activeKey = DEFAULT_ACTIVE_SESSION_KEY } = {}) {
  const state = { sessions: [], activeSessionId: "" };

  const store = {
    get sessions() { return state.sessions; },
    set sessions(value) { state.sessions = value; },
    get activeSessionId() { return state.activeSessionId; },
    set activeSessionId(value) { state.activeSessionId = String(value || ""); },

    createSession,

    rememberActiveSession() {
      storage.setItem(activeKey, state.activeSessionId);
    },

    async loadSessions() {
      const payload = await api.listSessions();
      state.sessions = (Array.isArray(payload.sessions) ? payload.sessions : [])
        .map(normalizeSession)
        .filter(Boolean);
      if (!state.sessions.length) state.sessions = [createSession()];

      state.activeSessionId = storage.getItem(activeKey) || state.sessions[0].id;
      if (!state.sessions.some((session) => session.id === state.activeSessionId)) {
        state.activeSessionId = state.sessions[0].id;
      }
      this.rememberActiveSession();
    },

    async loadConversation(sessionId) {
      if (!sessionId) return;
      const payload = await api.loadMessages(sessionId);
      if (sessionId !== state.activeSessionId) return;
      const session = state.sessions.find((item) => item.id === sessionId);
      if (!session) return;
      session.messages = (Array.isArray(payload.messages) ? payload.messages : [])
        .filter((message) => message && ["assistant", "user"].includes(message.role))
        .map((message) => ({
          role: message.role,
          text: String(message.text || ""),
          result: message.result || null,
          created_at: message.created_at || null,
        }));
      session.message_count = session.messages.length;
      if (payload.pending_approval) {
        session.messages.push({
          role: "assistant",
          text: payload.pending_approval.answer,
          result: payload.pending_approval,
        });
      }
    },

    currentSession() {
      let session = state.sessions.find((item) => item.id === state.activeSessionId);
      if (!session) {
        session = createSession();
        state.sessions.unshift(session);
        state.activeSessionId = session.id;
        this.rememberActiveSession();
      }
      return session;
    },

    updateCurrentSession(updater) {
      const session = this.currentSession();
      updater(session);
      session.message_count = session.messages.length;
      session.updated_at = nowIso();
      this.rememberActiveSession();
      return session;
    },
  };

  return store;
}
