import type { Message, ProgressEntry, RunResult, StreamFrame } from '../../types';
import { advanceProgress, completedProgress } from './progress';

export interface SavedRun { run_id?: string; session_id?: string; request?: string; created_at?: string; result?: RunResult; status?: string }

function savedRequest(run: SavedRun): string | undefined {
  // Public run metadata omits the original prompt. Completed result envelopes
  // carry the public request/answer pair instead; older envelopes may not.
  if (typeof run.request === 'string') return run.request;
  const messages = run.result?.messages;
  if (!Array.isArray(messages)) return undefined;
  const user = messages.find(item => item?.role === 'user');
  return typeof user?.content === 'string' ? user.content : undefined;
}

/** Rebuild the same activity/answer split from server-owned history and events. */
export async function restoreHistory(
  rawMessages: Message[], runs: SavedRun[], readEvents: (runId: string) => Promise<StreamFrame[]>,
): Promise<Message[]> {
  const messages: Message[] = [];
  const answers: { message: Message; request: string }[] = [];
  let request = '';
  let pending: Message[] = [];
  const flush = () => {
    if (!pending.length) return;
    const final = pending[pending.length - 1];
    const narration: ProgressEntry[] = pending.slice(0, -1).map((message, index) => ({
      id: `history:${messages.length}:${index}`, kind: 'text', text: message.text, active: false, scope: 'history',
    }));
    const message = { ...final, progress: completedProgress([...(final.progress || []), ...narration], final.text) };
    messages.push(message);
    answers.push({ message, request });
    pending = [];
  };
  for (const raw of rawMessages) {
    if (!raw || !['user', 'assistant'].includes(raw.role)) continue;
    const message = { ...raw, text: String(raw.text || '') };
    if (message.role === 'user') {
      flush();
      request = message.text;
      messages.push(message);
    } else {
      pending.push(message);
      // An attached result is an explicit answer boundary. Keep distinct
      // approved results/artifacts even if several share one user request.
      if (message.result) flush();
    }
  }
  flush();

  // Match from newest to oldest: /runs may retain only the newest 100 jobs,
  // and users can submit identical prompts with identical final answers.
  const remaining = [...runs].sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || '')));
  const restore: (() => Promise<void>)[] = [];
  for (const { message, request } of [...answers].reverse()) {
    const index = remaining.findIndex(run => {
      const saved = savedRequest(run);
      return run.run_id && (saved === undefined || saved.trim() === request.trim())
        && String(run.result?.answer || '').trim() === message.text.trim();
    });
    if (index < 0) continue;
    const [run] = remaining.splice(index, 1);
    restore.push(async () => {
      try {
        const events = await readEvents(run.run_id!);
        let activity: ProgressEntry[] = [];
        for (const frame of events) {
          if (!frame || !frame.payload || typeof frame.payload !== 'object') continue;
          // Older workers lost delta scopes and mixed typed JSON into prose.
          // Restore their tool events, using SDK history for safe narration.
          if (frame.event === 'sdk_raw_response' && !frame.payload.content_kind) continue;
          activity = advanceProgress(activity, frame);
        }
        activity = completedProgress(activity, message.text);
        const missing = (message.progress || []).filter(entry => !activity.some(saved => saved.kind === entry.kind && saved.text.trim() === entry.text.trim()));
        message.progress = [...missing, ...activity];
      } catch {
        // A pruned/unavailable event log must not break conversation loading.
        // The saved intermediate messages still render as compact activity.
      }
    });
  }
  // Bound concurrent event reads for long conversations.
  for (let offset = 0; offset < restore.length; offset += 4) {
    await Promise.all(restore.slice(offset, offset + 4).map(read => read()));
  }
  return messages;
}
