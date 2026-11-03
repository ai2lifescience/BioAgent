import type { AppConfig, Message, RunResult, StreamFrame, WorkspaceFile } from './types';
import { restoreHistory, type SavedRun } from './features/messages/history';

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
  createSession(): Promise<{ session_id: string }>;
  loadConfig(): Promise<AppConfig>;
  listSessions(): Promise<{ sessions: any[] }>;
  loadMessages(id: string, requireRunState?: boolean): Promise<{ messages?: Message[]; pending_approval?: RunResult; active_run?: SavedRun }>;
  listRuns(): Promise<{ runs: SavedRun[] }>;
  watchRun(id: string, signal: AbortSignal, onFrame: (frame: StreamFrame) => void): Promise<RunResult>;
  cancelRun(id: string): Promise<SavedRun>;
  loadWorkspace(id: string): Promise<{ workspace?: { files?: WorkspaceFile[]; file_count?: number } }>;
  uploadFiles(id: string, files: File[]): Promise<any>;
  deleteWorkspaceFile(id: string, path: string): Promise<any>;
  deleteSession(id: string): Promise<any>;
  updateSession(id: string, changes: Record<string, unknown>): Promise<any>;
  run(request: string, opts: { sessionId: string; modelKey: string; maxTurns: number; signal: AbortSignal; onFrame: (frame: StreamFrame) => void; website?: { binding_id: string; token: string } }): Promise<RunResult>;
  approve(payload: Record<string, unknown>, signal: AbortSignal, onFrame: (frame: StreamFrame) => void): Promise<RunResult>;
}

export function createApiClient(fetchImpl: typeof fetch = (...args) => window.fetch(...args), baseUrl = '', transport: 'stream' | 'poll' = 'stream'): ApiClient {
  const resolve = (path: string) => {
    if (!baseUrl) return path;
    return new URL(path.replace(/^\//, ''), baseUrl.endsWith('/') ? baseUrl : `${baseUrl}/`).toString();
  };
  const get = async <T>(path: string, init?: RequestInit) => readJson<T>(await fetchImpl(resolve(path), init));
  const wait = (signal: AbortSignal) => new Promise<void>((resolve, reject) => {
    const abort = () => { clearTimeout(timer); reject(new DOMException('Stopped waiting', 'AbortError')); };
    const timer = setTimeout(() => { signal.removeEventListener('abort', abort); resolve(); }, 750);
    signal.addEventListener('abort', abort, { once: true });
    if (signal.aborted) abort();
  });
  // Short requests release browser connections between updates. Queued jobs must
  // not occupy every HTTP/1 connection and starve navigation, uploads or login.
  const watchRun = async (id: string, signal: AbortSignal, onFrame: (frame: StreamFrame) => void): Promise<RunResult> => {
    let after = -1;
    let status = '';
    while (!signal.aborted) {
      let saved: { run: SavedRun & { error?: string }; events: (StreamFrame & { sequence: number })[] };
      try {
        saved = await get(`/runs/${encodeURIComponent(id)}/events?after=${after}`, { signal });
      } catch (error) {
        if (signal.aborted || (error instanceof ApiError && error.status < 500)) throw error;
        onFrame({ event: 'connection', payload: { message: 'Connection interrupted. Reconnecting; the server task may still be running.' } });
        await wait(signal);
        continue;
      }
      const job = saved.run;
      onFrame({ event: 'connection', payload: { message: '' } });
      const nextStatus = job.cancel_requested && job.status === 'running' ? 'cancelling' : job.status || '';
      if (nextStatus !== status) {
        status = nextStatus;
        onFrame({ event: 'run_status', payload: { run_id: id, status } });
      }
      for (const event of saved.events) {
        if (event.sequence <= after) continue;
        after = event.sequence;
        // A resumed approval reuses its run ID and event log. Its old result
        // is not the result of this execution; the durable row is authoritative.
        if (!['result', 'error'].includes(event.event)) onFrame(event);
      }
      if (!['queued', 'running', 'cancelling'].includes(status)) {
        if (!job.result) job.result = { answer: job.error || 'Agent run failed.', status: 'error', session_id: job.session_id };
        const result = { ...job.result, job_id: id, run_status: status,
          runtime: { ...job.result.runtime, status, job_id: id } };
        onFrame({ event: 'result', payload: result });
        return result;
      }
      await wait(signal);
    }
    throw new DOMException('Stopped waiting', 'AbortError');
  };
  const enqueue = async (path: string, body: unknown, signal: AbortSignal, onFrame: (frame: StreamFrame) => void) => {
    // Never retry a POST: a lost response may still have created the job.
    const job = await get<SavedRun>(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), signal });
    if (!job.run_id) throw new Error('The server did not return a run ID.');
    onFrame({ event: 'run_status', payload: { run_id: job.run_id, status: job.status || 'queued' } });
    return watchRun(job.run_id, signal, onFrame);
  };
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
    cancelRun: id => get(`/runs/${encodeURIComponent(id)}/cancel`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}',
    }),
    watchRun,
    listRuns: () => get('/runs'),
    createSession: () => get('/sessions', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' }),
    loadConfig: () => get('/config'), listSessions: () => get('/sessions'), loadMessages: async (id, requireRunState = false) => {
      const payload = await get<{ messages?: Message[]; pending_approval?: RunResult }>(`/sessions/${encodeURIComponent(id)}/messages`);
      let runs: SavedRun[] = [];
      // A detached worker writes the durable run before the session history
      // projection. Recover a pending approval from that queue on reload so a
      // browser refresh cannot hide a review that is still actionable.
      try {
        const queued = await get<{ runs?: SavedRun[] }>(`/runs?session_id=${encodeURIComponent(id)}`);
        runs = (Array.isArray(queued.runs) ? queued.runs : []).filter(run => run && (!run.session_id || run.session_id === id));
        const pending = runs.find(item => item.status === 'pending_approval' && item.result?.approvals?.length);
        if (pending && !payload.pending_approval?.approvals?.length) {
          payload.pending_approval = {
            ...pending.result,
            session_id: id,
            status: 'pending_approval',
            approval_required: true,
          };
        }
      } catch (error) {
        if (requireRunState) throw error;
        // Older deployments may not expose the run listing endpoint.
      }
      const messages = await restoreHistory(Array.isArray(payload.messages) ? payload.messages : [], runs, async runId => {
        const saved = await get<{ events?: StreamFrame[] }>(`/runs/${encodeURIComponent(runId)}/events`);
        return Array.isArray(saved.events) ? saved.events : [];
      });
      return { ...payload, messages, active_run: runs.find(run => ['queued', 'running'].includes(run.status || '')) };
    },
    loadWorkspace: id => get(`/workspace?session_id=${encodeURIComponent(id)}`),
    uploadFiles: async (id, files) => {
      const config = await get<AppConfig>('/config');
      const limits = config.storage_limits;
      if (!limits) throw new Error('Restart the server to enable resumable uploads.');
      for (const file of files) {
        if (!file.size || file.size > limits.file_bytes) throw new Error(`${file.name}: file must be between 1 byte and ${(limits.file_bytes / 1024 ** 3).toFixed(1)} GiB.`);
      }
      const uploaded = [];
      for (const file of files) {
        const key = `agent.upload.${id}.${file.name}.${file.size}.${file.lastModified}`;
        let row: any = null;
        const saved = localStorage.getItem(key);
        if (saved) {
          try { row = await get(`/workspace/uploads/${saved}`); } catch { localStorage.removeItem(key); }
        }
        if (!row) {
          row = await get('/workspace/uploads', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ session_id: id, filename: file.name, size: file.size }) });
          localStorage.setItem(key, row.upload_id);
        }
        let retries = 0;
        while (row.offset < file.size) {
          try {
            row = await readJson(await fetchImpl(resolve(`/workspace/uploads/${row.upload_id}`), {
              method: 'PATCH', headers: { 'Content-Type': 'application/octet-stream', 'Upload-Offset': String(row.offset) },
              body: file.slice(row.offset, row.offset + limits.upload_chunk_bytes),
            }));
            retries = 0;
          } catch (error) {
            if (++retries > 2) throw error;
            row = await get(`/workspace/uploads/${row.upload_id}`);
          }
        }
        const result = await get<{ files: WorkspaceFile[] }>(`/workspace/uploads/${row.upload_id}/complete`, { method: 'POST' });
        uploaded.push(...result.files); localStorage.removeItem(key);
      }
      return { session_id: id, files: uploaded };
    },
    deleteWorkspaceFile: (id, path) => get(`/workspace/files/${encodeURIComponent(path)}?session_id=${encodeURIComponent(id)}`, { method: 'DELETE' }),
    deleteSession: id => get(`/sessions/${encodeURIComponent(id)}`, { method: 'DELETE' }),
    updateSession: (id, changes) => get(`/sessions/${encodeURIComponent(id)}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(changes) }),
    run: (request, opts) => (transport === 'poll' ? enqueue : stream)(transport === 'poll' ? '/run' : '/run_stream', { request, session_id: opts.sessionId, model_key: opts.modelKey, max_turns: opts.maxTurns, ...(opts.website ? { website: opts.website } : {}) }, opts.signal, opts.onFrame),
    approve: (payload, signal, onFrame) => (transport === 'poll' ? enqueue : stream)(transport === 'poll' ? '/approve_async' : '/approve_stream', payload, signal, onFrame),
  };
}
