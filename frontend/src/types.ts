export type Role = 'user' | 'assistant';

export interface ModelOption { key: string; label?: string; cost_tier?: string; deployment?: string; model?: string }
export interface Pipeline { name: string; display_name?: string; parameters?: Record<string, { required?: boolean; choices?: string[] }> }
export interface AppConfig {
  default_model_key: string;
  default_max_turns: number;
  models: ModelOption[];
  files?: { structure_suffixes?: string[]; image_suffixes?: string[] };
  pipelines?: Pipeline[];
}
export interface WorkspaceFile { path?: string; workspace_path?: string; name?: string; size?: number; kind?: string }
export interface SessionSummary {
  id: string; title: string; message_count: number; last_run_id?: string; created_at: string; updated_at: string; pinned?: boolean;
  messages?: Message[];
}
export interface Message { role: Role; text: string; result?: RunResult | null; created_at?: string | null }
export interface RuntimeInfo { status?: string; elapsed_seconds?: number; model_key?: string; max_turns?: number; tools?: string[]; tool_count?: number; file_count?: number; logs?: string[] }
export interface TraceEvent { event?: string; type?: string; data?: Record<string, unknown>; [key: string]: unknown }
export interface Evidence { tools?: string[]; files?: Array<WorkspaceFile | string>; citations?: unknown[]; sources?: unknown[]; outputs?: WorkspaceFile[]; [key: string]: unknown }
export interface RunResult {
  answer?: string; status?: string; run_status?: string; session_id?: string; job_id?: string; runtime?: RuntimeInfo;
  trace?: TraceEvent[]; evidence?: Evidence; artifacts?: WorkspaceFile[]; files?: WorkspaceFile[]; workspace_files?: WorkspaceFile[];
  approval_required?: boolean; approvals?: Approval[]; pending_approval?: boolean; [key: string]: unknown;
}
export interface Approval { approval_id: string; tool_name?: string; arguments?: Record<string, unknown>; description?: string }
export interface StreamFrame { event: string; payload: Record<string, any> }

export function sessionIdOf(value: any): string { return String(value?.session_id ?? value?.id ?? '') }
export function workspacePathOf(file: WorkspaceFile | null | undefined): string {
  if (!file || typeof file !== 'object') return '';
  return String(file.workspace_path ?? file.path ?? '')
}
