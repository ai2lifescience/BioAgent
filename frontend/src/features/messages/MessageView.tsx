import { useEffect, useRef, useState } from 'react';
import type { AppConfig, Message, RunResult, TraceEvent, WorkspaceFile } from '../../types';
import { workspacePathOf } from '../../types';
import renderMarkdown from './markdown';
import { ArtifactViews, fileUrl } from './ArtifactView';
import ApprovalControls, { type ApprovalMeta } from './ApprovalControls';
import { AgentIcon } from '../../components/icons';
import './messages.css';
import { RunProgress } from './RunProgress';

export interface MessageViewProps { message: Message; config: AppConfig; sessionId: string; busy: boolean; onApproval: (result: RunResult, meta?: ApprovalMeta) => void; onBusy: (busy: boolean) => void }
const text = (value: unknown): string => value == null ? '' : typeof value === 'string' ? value : String(value);
const record = (value: unknown): Record<string, unknown> => value && typeof value === 'object' ? value as Record<string, unknown> : {};
const toolLabel = (tool: unknown): string => ({ database_lookup: 'Database lookup', genome_read_features: 'Read genome features', alphafold_download: 'Download AlphaFold structure', document_read: 'Read document', file_inspection: 'Inspect file', genome_render_map: 'Open genome browser', ncbi_retrieval: 'Retrieve NCBI records', pdb_download: 'Download PDB structure', pipeline_shell: 'Run pipeline command', pipeline_specialist: 'Pipeline specialist', structure_inspect: 'Inspect protein structure', sequence_stats: 'Measure sequence', sequence_find_orfs: 'Find sequence ORFs', report_review: 'Review evidence', report_synthesize: 'Draft cited report', report_write: 'Save cited report', blast_search: 'BLAST search' } as Record<string, string>)[text(tool)] || text(tool).replaceAll('_', ' ') || 'Agent operation';
const elapsed = (value: unknown): string => { const seconds = Number(value || 0); return seconds < 60 ? `${seconds.toFixed(seconds < 10 ? 1 : 0)}s` : `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`; };
const statusInfo = (result: RunResult) => { const value = text(result.runtime?.status || result.status || 'ok'); const labels: Record<string, string> = { ok: 'Completed', pending_approval: 'Waiting for approval', blocked: 'Blocked by guardrail', error: 'Failed', stopped: 'Stopped' }; return { value, label: labels[value] || value, tone: value === 'ok' ? 'ok' : value === 'pending_approval' || value === 'stopped' ? 'warning' : 'error' }; };

function traceTitle(event: TraceEvent): string { const data = record(event.data); switch (event.event || event.type) { case 'run_started': return 'Request accepted'; case 'agent_started': return `Agent started${data.agent ? ` · ${text(data.agent)}` : ''}`; case 'agent_finished': return `Agent finished${data.agent ? ` · ${text(data.agent)}` : ''}`; case 'model_requested': return 'Agent selected the next step'; case 'model_responded': return 'Agent decision received'; case 'handoff': return `Delegated to ${text(data.to_agent) || 'specialist'}`; case 'tool_started': case 'sdk_tool_started': return `Started · ${toolLabel(data.tool)}`; case 'tool_finished': case 'sdk_tool_finished': return `Finished · ${toolLabel(data.tool)}`; case 'tool_failed': return `Tool failed · ${toolLabel(data.tool)}`; case 'pipeline_command_finished': return 'Pipeline command finished'; case 'guardrail_completed': return 'Output safety check completed'; case 'guardrail_blocked': return 'Safety guardrail blocked the request'; case 'approval_decision': return data.approved ? 'Tool approval granted' : 'Tool approval rejected'; case 'run_paused': return 'Run paused for approval'; case 'run_finished': return 'Run completed'; case 'run_failed': return 'Run failed'; default: return text(event.event || event.type || 'Activity').replaceAll('_', ' '); } }
function traceDetail(event: TraceEvent): string { const data = record(event.data); const tool = data.tool; if (tool) return event.event === 'tool_finished' || event.event === 'sdk_tool_finished' ? text(data.summary || data.answer || data.status || 'Result returned.') : `Registered operation: ${text(tool)}`; if (event.event === 'model_responded') return Number(data.input_tokens || data.output_tokens) ? `Tokens: ${Number(data.input_tokens || 0).toLocaleString()} in · ${Number(data.output_tokens || 0).toLocaleString()} out` : 'Decision received.'; if (event.event === 'handoff') return `${text(data.from_agent) || 'Agent'} → ${text(data.to_agent) || 'specialist'}`; return text(data.message || data.error || data.reason || ''); }

function Evidence({ result, sessionId }: { result: RunResult; sessionId: string }) {
  const evidence = record(result.evidence); const list = (value: unknown): unknown[] => Array.isArray(value) ? value : []; const links = list(evidence.citations).map((item, i) => { const value = record(item); const label = typeof item === 'string' ? item : `${text(value.title || value.name || value.id) || 'Citation'}${value.source || value.pmid || value.year ? ` · ${text(value.source || value.pmid || value.year)}` : ''}`; return value.url ? <a key={i} href={text(value.url)} target="_blank" rel="noopener noreferrer">{label}</a> : <span key={i}>{label}</span>; }); const paths = list(evidence.files).map(item => typeof item === 'string' ? item : workspacePathOf(record(item) as WorkspaceFile)).filter(Boolean).map(path => <a key={path} href={fileUrl(sessionId, path)} title={path}>{path.split('/').pop()}</a>); const Group = ({ title, values }: { title: string; values: React.ReactNode[] }) => values.length ? <section className="evidence-group"><h4>{title}</h4><ul>{values.map((value, i) => <li key={i}>{value}</li>)}</ul></section> : null; return <div className="evidence-panel"><Group title="Tools used" values={list(evidence.tools).map(value => <span key={text(value)}>{toolLabel(value)}</span>)} /><Group title="Databases" values={list(evidence.databases).map(value => <span key={text(value)}>{text(value)}</span>)} /><Group title="Queries" values={list(evidence.query_terms).map(value => <span key={text(value)}>{text(value)}</span>)} /><Group title="Records" values={list(evidence.record_ids).map(value => <span key={text(value)}>{text(value)}</span>)} /><Group title="Files" values={paths} /><Group title="Sources" values={links} /><Group title="Links" values={list(evidence.urls).map(value => <a key={text(value)} href={text(value)} target="_blank" rel="noopener noreferrer">{text(value)}</a>)} /> <Group title="Errors" values={list(evidence.tool_errors).map((value, i) => <span key={i}>{text(record(value).error || record(value).tool || value)}</span>)} />{list(evidence.outputs).length ? <Group title="Tool results" values={list(evidence.outputs).map((value, i) => <span key={i}><strong>{toolLabel(record(value).tool)}</strong> {text(record(value).summary || record(value).status || 'Result returned.')}</span>)} /> : null}</div>;
}

function RunDetails({ result, config, sessionId, busy, onApproval, onBusy }: { result: RunResult; config: AppConfig; sessionId: string; busy: boolean; onApproval: MessageViewProps['onApproval']; onBusy: (busy: boolean) => void }) {
  const [tab, setTab] = useState<string | null>(null);
  const tabRef = useRef<string | null>(null);
  const [approvalResult, setApprovalResult] = useState(result);
  useEffect(() => setApprovalResult(result), [result]);
  const runtime = result.runtime || {};
  const info = statusInfo(result);
  const trace = Array.isArray(result.trace) ? result.trace : [];
  const evidence = record(result.evidence);
  const tools = Array.isArray(runtime.tools) ? runtime.tools : Array.isArray(evidence.tools) ? evidence.tools as unknown[] : [];
  const tabs: Array<[string, string]> = [
    ['runtime', `${info.label} · ${elapsed(runtime.elapsed_seconds)}`],
    ['plan', `${trace.length} events`],
    ['evidence', `${Array.isArray(evidence.citations) ? evidence.citations.length : 0} sources`],
    ['trace', 'technical'],
  ];
  const setSelectedTab = (event: React.MouseEvent<HTMLButtonElement>, key: string) => {
    const root = event.currentTarget.closest<HTMLElement>('.run-debug');
    // Keep a synchronous ref so two clicks in the same task (as used by
    // keyboard/browser probes) still toggle the panel before React commits.
    const next = tabRef.current === key ? null : key;
    tabRef.current = next;
    root?.querySelectorAll<HTMLElement>('[data-runtime-panel]').forEach(panel => { panel.hidden = panel.dataset.runtimePanel !== next; });
    root?.querySelectorAll<HTMLButtonElement>('[data-runtime-tab]').forEach(button => {
      const selected = button.dataset.runtimeTab === next;
      button.setAttribute('aria-selected', String(selected));
      button.classList.toggle('is-active', selected);
    });
    setTab(next);
  };
  const handleApproval = (next: RunResult, meta?: ApprovalMeta) => { if (meta?.intermediate) setApprovalResult(next); onApproval(next, meta); };
  const filteredTrace = trace.filter(event => !['sdk_span_finished', 'sdk_trace_started', 'sdk_trace_finished'].includes(text(event.event)));
  const decision = record(result.approval_decision);
  const reviewedPlan = decision.plan ? { action: decision.arguments, plan: decision.plan } : decision.arguments;
  return <div className="run-debug" aria-label="Runtime details">
    {decision.approved !== undefined && reviewedPlan != null && <details className="run-plan-record" open={false}><summary>{decision.approved ? 'Approved pipeline plan' : 'Rejected operation plan'} <span>{text(decision.tool_name) || 'Tool request'}</span></summary><pre>{JSON.stringify(reviewedPlan, null, 2)}</pre></details>}
    <div className="run-tabs" role="tablist">
      {tabs.map(([key, label]) => <button key={key} data-runtime-tab={key} type="button" role="tab" aria-selected={tab === key} className={tab === key ? 'is-active' : ''} onClick={event => setSelectedTab(event, key)}><span>{key === 'runtime' ? 'Runtime' : key === 'plan' ? 'Plan & execution' : key[0].toUpperCase() + key.slice(1)}</span><small>{label}</small></button>)}
    </div>
    <section className="run-panel" data-runtime-panel="runtime" hidden={tab !== 'runtime'}>
      <div className="run-metrics"><div className={`run-status-chip ${info.tone}`}>{info.label}</div><div><span>Model</span><strong>{text(config.models.find(item => item.key === runtime.model_key)?.label || runtime.model_key || result.model_key || 'Unknown model')}</strong></div><div><span>Elapsed</span><strong>{elapsed(runtime.elapsed_seconds)}</strong></div><div><span>Tools</span><strong>{runtime.tool_count ?? tools.length}</strong></div><div><span>Files</span><strong>{runtime.file_count ?? (Array.isArray(evidence.files) ? evidence.files.length : 0)}</strong></div><div><span>Max turns</span><strong>{runtime.max_turns ?? '—'}</strong></div></div>
    </section>
    <section className="run-panel" data-runtime-panel="plan" hidden={tab !== 'plan'}>
      <p className="run-debug-note">This shows registered operations and runtime events, without exposing private model reasoning.</p>
      <ol className="run-timeline">{filteredTrace.length ? filteredTrace.map((event, index) => <li key={index} className={`run-step ${event.event === 'run_failed' || event.event === 'guardrail_blocked' ? 'error' : ['run_finished', 'agent_finished'].includes(text(event.event)) ? 'done' : ''}`}><span className="run-step-index">{index + 1}</span><div className="run-step-body"><strong>{traceTitle(event)}</strong><span>{traceDetail(event)}</span></div></li>) : <li className="run-empty">No execution events were returned by the runtime.</li>}</ol>
    </section>
    <section className="run-panel" data-runtime-panel="evidence" hidden={tab !== 'evidence'}><Evidence result={result} sessionId={sessionId} /></section>
    <section className="run-panel" data-runtime-panel="trace" hidden={tab !== 'trace'}><div className="trace-log">{trace.length ? trace.map((event, i) => <div className="trace-row" key={i}><time>{text(event.timestamp || '—')}</time><code>{text(event.event || event.type || 'event')}</code><span>{Object.entries(record(event.data)).filter(([key, value]) => value !== null && value !== '' && key !== 'timestamp').slice(0, 6).map(([key, value]) => `${key}=${typeof value === 'object' ? JSON.stringify(value) : text(value)}`).join(' · ') || 'No event details'}</span></div>) : <div className="run-empty">No trace events were returned.</div>}</div></section>
    <ApprovalControls result={approvalResult} busy={busy} onResult={handleApproval} onBusy={onBusy} />
  </div>;
}
export function MessageView({ message, config, sessionId, busy, onApproval, onBusy }: MessageViewProps) {
  const result = message.result || null;
  const assistant = message.role === 'assistant';
  return <article className={`message ${message.role}`} aria-label={assistant ? 'Assistant message' : 'Your message'}>
    <div className="message-avatar" aria-hidden="true">{assistant ? <AgentIcon size={34} /> : <span className="message-avatar-label">You</span>}</div>
    <div className="message-content">{assistant && message.progress && <RunProgress entries={message.progress} />}<div className="message-body">{renderMarkdown(message.text)}{result && assistant && <><ArtifactViews result={result} sessionId={sessionId} imageSuffixes={config.files?.image_suffixes || ['.gif', '.jpeg', '.jpg', '.png', '.svg', '.webp']} />{(result.runtime || result.trace || result.evidence || result.approval_required) && <RunDetails result={result} config={config} sessionId={sessionId} busy={busy} onApproval={onApproval} onBusy={onBusy} />}</>}</div></div>
  </article>;
}

export default MessageView;
