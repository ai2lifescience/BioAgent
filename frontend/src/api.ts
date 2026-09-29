import type { AppConfig, RunResult, SessionSummary, StreamFrame, WorkspaceFile } from './types';

export class ApiError extends Error {
  status: number;
  payload: any;
  constructor(message: string, status = 0, payload: any = null) { super(message); this.name = 'ApiError'; this.status = status; this.payload = payload; }
}

async function readJson<T>(response: Response): Promise<T> {
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new ApiError(String(payload?.error || `HTTP ${response.status}`), response.status, payload);
  return payload as T;
}

export function parseSseFrame(frame: string): StreamFrame {
  let event = 'message'; const lines: string[] = [];
  for (const raw of frame.split(/\r?\n/)) {
    if (raw.startsWith('event:')) event = raw.slice(6).trim();
    if (raw.startsWith('data:')) lines.push(raw.slice(5).trimStart());
  }
  const text = lines.join('\n');
  return { event, payload: text ? JSON.parse(text) : {} };
}

export interface ApiClient {
  loadConfig(): Promise<AppConfig>;
  listSessions(): Promise<{ sessions: any[] }>;
  loadMessages(id: string): Promise<{ messages?: any[]; pending_approval?: RunResult }>;
  loadWorkspace(id: string): Promise<{ workspace?: { files?: WorkspaceFile[]; file_count?: number } }>;
  uploadFiles(id: string, files: File[]): Promise<any>;
  deleteWorkspaceFile(id: string, path: string): Promise<any>;
  deleteSession(id: string): Promise<any>;
  updateSession(id: string, changes: Record<string, unknown>): Promise<any>;
  run(request: string, opts: { sessionId: string; modelKey: string; maxTurns: number; signal: AbortSignal; onFrame: (frame: StreamFrame) => void; website?: { binding_id: string; token: string } }): Promise<RunResult>;
  approve(payload: Record<string, unknown>, signal: AbortSignal, onFrame: (frame: StreamFrame) => void): Promise<RunResult>;
}

export function createApiClient(fetchImpl: typeof fetch = window.fetch.bind(window), baseUrl = ''): ApiClient {
  const resolve = (path: string) => {
    if (!baseUrl) return path;
    return new URL(path.replace(/^\//, ''), baseUrl.endsWith('/') ? baseUrl : `${baseUrl}/`).toString();
  };
  const get = async <T>(path: string, init?: RequestInit) => readJson<T>(await fetchImpl(resolve(path), init));
  const stream = async (path: string, body: unknown, signal: AbortSignal, onFrame: (frame: StreamFrame) => void): Promise<RunResult> => {
    const response = await fetchImpl(resolve(path), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), signal });
    if (!response.ok) throw new ApiError(await response.text() || `HTTP ${response.status}`, response.status);
    if (!response.body) throw new Error('Streaming response is not available in this browser.');
    const reader = response.body.getReader(); const decoder = new TextDecoder(); let buffer = '';
    try {
      while (true) {
        const { value, done } = await reader.read();
        buffer += done ? decoder.decode() : decoder.decode(value, { stream: true });
        const frames = buffer.split(/\r?\n\r?\n/); buffer = frames.pop() || '';
        for (const raw of frames) {
          if (!raw.trim()) continue;
          const frame = parseSseFrame(raw); onFrame(frame);
          if (frame.event === 'result') return frame.payload as RunResult;
          if (frame.event === 'error') throw new ApiError(String(frame.payload.error || 'Agent stream failed.'), 500, frame.payload);
        }
        if (done) break;
      }
      if (buffer.trim()) { const frame = parseSseFrame(buffer); onFrame(frame); if (frame.event === 'result') return frame.payload as RunResult; }
    } finally { await reader.cancel().catch(() => undefined); reader.releaseLock(); }
    throw new Error('Agent stream ended before returning a result.');
  };
  return {
    loadConfig: () => get('/config'), listSessions: () => get('/sessions'), loadMessages: async id => {
      const payload = await get<{ messages?: any[]; pending_approval?: RunResult }>(`/sessions/${encodeURIComponent(id)}/messages`);
      if (payload.pending_approval?.approval_required && Array.isArray(payload.pending_approval.approvals) && payload.pending_approval.approvals.length) return payload;
      // A detached worker writes the durable run before the session history
      // projection. Recover a pending approval from that queue on reload so a
      // browser refresh cannot hide a review that is still actionable.
      try {
        const queued = await get<{ runs?: any[] }>(`/runs?session_id=${encodeURIComponent(id)}`);
        const pending = (queued.runs || []).find(item => item?.status === 'pending_approval' && Array.isArray(item?.result?.approvals) && item.result.approvals.length);
        if (pending) {
          return {
            ...payload,
            pending_approval: {
              ...(pending.result as RunResult),
              session_id: id,
              status: 'pending_approval',
              approval_required: true,
            },
          };
        }
      } catch {
        // Older deployments may not expose the run listing endpoint.
      }
      return payload;
    },
    loadWorkspace: id => get(`/workspace?session_id=${encodeURIComponent(id)}`),
    uploadFiles: async (id, files) => { const form = new FormData(); form.append('session_id', id); files.forEach(file => form.append('files', file, file.name)); return readJson(await fetchImpl(resolve('/workspace/files'), { method: 'POST', body: form })); },
    deleteWorkspaceFile: (id, path) => get(`/workspace/files/${encodeURIComponent(path)}?session_id=${encodeURIComponent(id)}`, { method: 'DELETE' }),
    deleteSession: id => get(`/sessions/${encodeURIComponent(id)}`, { method: 'DELETE' }),
    updateSession: (id, changes) => get(`/sessions/${encodeURIComponent(id)}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(changes) }),
    run: (request, opts) => stream('/run_stream', { request, session_id: opts.sessionId, model_key: opts.modelKey, max_turns: opts.maxTurns, ...(opts.website ? { website: opts.website } : {}) }, opts.signal, opts.onFrame),
    approve: (payload, signal, onFrame) => stream('/approve_stream', payload, signal, onFrame),
  };
}
