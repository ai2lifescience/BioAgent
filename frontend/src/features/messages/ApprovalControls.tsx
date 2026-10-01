import { useState } from 'react';
import type { Approval, RunResult, StreamFrame } from '../../types';
import { createApiClient } from '../../api';

export interface ApprovalMeta { approved?: boolean; intermediate?: boolean; item?: Approval }
interface Props { result: RunResult; busy: boolean; onResult: (result: RunResult, meta?: ApprovalMeta) => void; onBusy: (busy: boolean) => void; onProgress?: (frame: StreamFrame) => void }

export default function ApprovalControls({ result, busy, onResult, onBusy, onProgress }: Props) {
  const [status, setStatus] = useState<Record<string, string>>({}); const api = createApiClient();
  const [planOpen, setPlanOpen] = useState<Record<string, boolean>>({});
  if (!Array.isArray(result.approvals) || !result.approvals.length) return null;
  const decide = async (item: Approval, approved: boolean) => {
    if (busy || !result.approval_required || item.approved !== undefined || status[item.approval_id]) return; const key = item.approval_id; onBusy(true); setStatus(prev => ({ ...prev, [key]: approved ? 'Approval submitted. Execution is in progress…' : 'Rejection submitted. Finishing the request…' }));
    setPlanOpen(prev => ({ ...prev, [key]: false }));
    const controller = new AbortController();
    try {
      const next = await api.approve({ session_id: result.session_id, approval_id: key, approved }, controller.signal, frame => {
        onProgress?.(frame);
        if (frame.event === 'pipeline_job_status') {
          const state = String(frame.payload.status || 'running');
          const message = ['queued', 'running'].includes(state)
            ? `Pipeline ${state}. Waiting for verified results…`
            : `Pipeline ${state}. Preparing the result summary…`;
          setStatus(prev => ({ ...prev, [key]: message }));
        } else if (frame.event === 'status') setStatus(prev => ({ ...prev, [key]: String(frame.payload.message || 'Resuming the run…') }));
      });
      const error = next.error ? String(next.error) : next.status === 'error' || next.runtime?.status === 'error' ? String(next.answer || 'Approval request failed.') : '';
      if (error) throw new Error(error);
      const decision = { approved, approval_id: key, tool_name: item.tool_name, arguments: item.arguments || null, plan: (item as Approval & { plan?: unknown }).plan || null };
      if (next.approval_required && Array.isArray(next.approvals) && next.approvals.length) {
        setStatus(prev => ({ ...prev, [key]: approved ? 'Approved. Reviewing the remaining requested operation…' : 'Rejected. Reviewing the remaining requested operation…' }));
        onResult(next, { approved, item, intermediate: true });
      } else {
        setStatus(prev => ({ ...prev, [key]: approved ? 'Approved. Execution details are shown in the next run panel.' : 'Rejected. No pipeline execution was started.' }));
        onResult({ ...next, approval_decision: decision }, { approved, item });
      }
    } catch (error) { setStatus(prev => ({ ...prev, [key]: error instanceof Error ? error.message : String(error) })); } finally { onBusy(false); }
  };
  return <div className="tool-approvals">{result.approvals.map(item => {
    const plan = item.plan;
    const itemStatus = status[item.approval_id] || (item.approved === true ? 'Approved.' : item.approved === false ? 'Rejected.' : '');
    const disabled = busy || Boolean(itemStatus) || !result.approval_required;
    const open = planOpen[item.approval_id] ?? (result.approval_required === true && !itemStatus);
    return <section className="approval-item" key={item.approval_id} data-approval-id={item.approval_id}>
      <strong>Review {item.tool_name || 'requested operation'}</strong>
      <details className="approval-plan" open={open} onToggle={event => {
        const expanded = event.currentTarget.open;
        setPlanOpen(prev => prev[item.approval_id] === expanded ? prev : { ...prev, [item.approval_id]: expanded });
      }}>
        <summary>{plan ? 'Pipeline plan' : 'Requested operation'}</summary>
        <pre>{JSON.stringify(plan ? { action: item.arguments, plan } : item.arguments, null, 2)}</pre>
      </details>
      <div className="approval-actions"><button type="button" disabled={disabled} onClick={() => decide(item, true)}>Approve</button><button type="button" disabled={disabled} onClick={() => decide(item, false)}>Reject</button></div>
      {itemStatus && <p className="approval-status" role="status">{itemStatus}</p>}
    </section>;
  })}</div>;
}
