import type { ProgressEntry, StreamFrame } from '../../types';

const toolLabels: Record<string, string> = {
  research_specialist: 'Researching sources',
  pubmed_search: 'Searching PubMed', web_search: 'Searching the web',
  web_fetch: 'Reading sources', pubmed_fetch: 'Reading PubMed records',
  evidence_index: 'Indexing evidence', evidence_retrieve: 'Retrieving evidence',
  report_review: 'Reviewing evidence', report_synthesize: 'Drafting the report',
  report_write: 'Saving the report', file_inspection: 'Inspecting files',
  knowledge_ingest: 'Ingesting knowledge', knowledge_status: 'Checking ingestion',
  knowledge_retrieve: 'Retrieving knowledge',
};
const scopeOf = (payload: StreamFrame['payload']) => JSON.stringify([payload.agent || '', payload.parent_call_id || '']);

// Only public output text and tool lifecycle events belong in the activity UI.
// Reasoning, arguments, log dumps, and typed sub-agent results are not narration.
export function advanceProgress(entries: ProgressEntry[], { event, payload }: StreamFrame): ProgressEntry[] {
  const scope = scopeOf(payload);
  if (event === 'pipeline_job_status' && payload.job_id) {
    const id = `pipeline:${payload.job_id}`;
    const status = String(payload.status || 'running');
    const name = String(payload.pipeline_name || 'Pipeline').replaceAll('_', ' ');
    const entry: ProgressEntry = { id, kind: 'tool', text: `${name} · ${status}`, scope,
      active: ['queued', 'running'].includes(status) };
    return entries.some(item => item.id === id) ? entries.map(item => item.id === id ? entry : item) : [...entries, entry];
  }
  if (event === 'sdk_run_item' && payload.name === 'tool_called' && payload.call_id) {
    const id = `tool:${payload.call_id}`;
    if (entries.some(entry => entry.id === id)) return entries;
    const name = String(payload.tool_name || 'tool');
    const text = toolLabels[name] || `Running ${name.replaceAll('_', ' ')}`;
    return [...entries, { id, kind: 'tool', text, active: true, scope }];
  }
  if (event === 'sdk_run_item' && payload.name === 'tool_output') {
    return entries.map(entry => entry.id === `tool:${payload.call_id}` ? { ...entry, active: false } : entry);
  }
  if (event !== 'sdk_raw_response' || payload.content_kind === 'structured') return entries;
  if (payload.data_type === 'response.output_text.delta' && payload.delta) {
    const stream = JSON.stringify([scope, payload.item_id || '', payload.content_index ?? 0]);
    const index = entries.findIndex(entry => entry.kind === 'text' && entry.stream === stream && entry.active);
    if (index >= 0) return entries.map((entry, i) => i === index ? { ...entry, text: entry.text + String(payload.delta) } : entry);
    return [...entries, { id: `text:${entries.length}`, kind: 'text', text: String(payload.delta), active: true, scope, stream }];
  }
  if (['response.output_text.done', 'response.completed', 'response.failed', 'response.incomplete'].includes(payload.data_type)) {
    return entries.map(entry => entry.kind === 'text' && entry.scope === scope ? { ...entry, active: false } : entry);
  }
  return entries;
}

// Also protect older workers without content_kind. Hold JSON-looking text out
// of the activity view; it can still be returned as an intentional final answer.
export function visibleProgress(entries: ProgressEntry[]): ProgressEntry[] {
  return entries.filter(entry => entry.text.trim() && (entry.kind === 'tool' || !/^(?:```(?:json)?\s*)?[{[]/.test(entry.text.trim())));
}

export function completedProgress(entries: ProgressEntry[], answer = ''): ProgressEntry[] {
  return visibleProgress(entries)
    .filter(entry => entry.kind !== 'text' || entry.text.trim() !== answer.trim())
    .map(entry => entry.kind === 'text' ? { ...entry, active: false } : entry);
}
