import { useState } from 'react';
import type { Approval, RunResult } from '../../types';
import { createApiClient } from '../../api';

export interface ApprovalMeta { approved?: boolean; intermediate?: boolean; item?: Approval }
interface Props { result: RunResult; busy: boolean; onResult: (result: RunResult, meta?: ApprovalMeta) => void; onBusy: (busy: boolean) => void }

export default function ApprovalControls({ result, busy, onResult, onBusy }: Props) {
  const [status, setStatus] = useState<Record<string, string>>({}); const api = createApiClient();
  if (!result.approval_required || !Array.isArray(result.approvals) || !result.approvals.length) return null;
  const decide = async (item: Approval, approved: boolean) => {
    if (busy) return; const key = item.approval_id; onBusy(true); setStatus(prev => ({ ...prev, [key]: approved ? 'Approval submitted. Execution is in progress…' : 'Rejection submitted. Finishing the request…' }));
    const controller = new AbortController();
    try {
      const next = await api.approve({ session_id: result.session_id, approval_id: key, approved }, controller.signal, frame => { if (frame.event === 'status' || frame.event === 'log') setStatus(prev => ({ ...prev, [key]: String(frame.payload.message || 'Resuming the run…') })); });
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
  return <div className="tool-approvals">{result.approvals.map(item => { const plan = (item as Approval & { plan?: unknown }).plan; const itemStatus = status[item.approval_id]; return <section className="approval-item" key={item.approval_id}><strong>Review {item.tool_name || 'requested operation'}</strong><details className="approval-plan" open><summary>{plan ? 'Pipeline plan' : 'Requested operation'}</summary><pre>{JSON.stringify(plan ? { action: item.arguments, plan } : item.arguments, null, 2)}</pre></details><div className="approval-actions"><button type="button" disabled={busy || Boolean(itemStatus)} onClick={() => decide(item, true)}>Approve</button><button type="button" disabled={busy || Boolean(itemStatus)} onClick={() => decide(item, false)}>Reject</button></div>{itemStatus && <p className="approval-status" role="status">{itemStatus}</p>}</section>; })}</div>;
}
