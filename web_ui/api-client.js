function apiError(payload, status, fallback) {
  if (payload && typeof payload === "object" && payload.error) {
    return new Error(String(payload.error));
  }
  return new Error(fallback || `HTTP ${status}`);
}

async function readJson(response) {
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw apiError(payload, response.status);
  return payload;
}

export function createApiClient({ fetchImpl = window.fetch.bind(window) } = {}) {
  const requestJson = async (url, options = {}) => readJson(await fetchImpl(url, options));

  return {
    async loadConfig() {
      return requestJson("/config");
    },

    async listSessions() {
      return requestJson("/sessions");
    },

    async loadMessages(sessionId) {
      return requestJson(`/sessions/${encodeURIComponent(sessionId)}/messages`);
    },

    async getRun(runId) {
      return requestJson(`/runs/${encodeURIComponent(runId)}`);
    },

    async getRunEvents(runId, after = -1) {
      return requestJson(`/runs/${encodeURIComponent(runId)}/events?after=${encodeURIComponent(after)}`);
    },

    async listRuns(sessionId) {
      return requestJson(`/runs?session_id=${encodeURIComponent(sessionId || "")}`);
    },

    async deleteSession(sessionId) {
      return requestJson(`/sessions/${encodeURIComponent(sessionId)}`, { method: "DELETE" });
    },

    async updateSession(sessionId, changes) {
      return requestJson(`/sessions/${encodeURIComponent(sessionId)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(changes),
      });
    },

    async loadWorkspace(sessionId) {
      return requestJson(`/workspace?session_id=${encodeURIComponent(sessionId)}`);
    },

    async uploadFiles(sessionId, files) {
      const formData = new FormData();
      formData.append("session_id", sessionId);
      for (const file of files) formData.append("files", file, file.name);
      return requestJson("/workspace/files", { method: "POST", body: formData });
    },

    async deleteWorkspaceFile(sessionId, workspacePath) {
      return requestJson(
        `/workspace/files/${encodeURIComponent(workspacePath)}?session_id=${encodeURIComponent(sessionId)}`,
        { method: "DELETE" },
      );
    },

    async run(request, { sessionId, modelKey, maxTurns, signal, onFrame } = {}) {
      const response = await fetchImpl("/run_stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          request,
          session_id: sessionId,
          model_key: modelKey,
          max_turns: maxTurns,
        }),
        signal,
      });
      if (!response.ok) {
        const text = await response.text();
        throw new Error(text || `HTTP ${response.status}`);
      }
      if (!response.body) throw new Error("Streaming response body is not available in this browser.");

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      try {
        while (true) {
          const { value, done } = await reader.read();
          buffer += done ? decoder.decode() : decoder.decode(value, { stream: true });
          const frames = buffer.split(/\r?\n\r?\n/);
          buffer = frames.pop() || "";
          for (const frame of frames) {
            const result = onFrame(frame);
            if (result?.done) return result.result;
          }
          if (done) break;
        }
        if (buffer.trim()) {
          const result = onFrame(buffer);
          if (result?.done) return result.result;
        }
      } finally {
        await reader.cancel().catch(() => {});
        reader.releaseLock();
      }
      throw new Error("Agent stream ended before returning a result.");
    },
  };
}
