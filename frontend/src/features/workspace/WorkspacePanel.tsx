import { useMemo, useRef, useState } from 'react';
import type { DragEvent, KeyboardEvent } from 'react';
import type { WorkspaceFile } from '../../types';
import { workspacePathOf } from '../../types';
import { LineIcon } from '../../components/icons';

export interface WorkspacePanelProps {
  sessionId: string;
  files: WorkspaceFile[];
  search: string;
  filter: 'all' | 'uploads' | 'outputs' | string;
  busy?: boolean;
  uploading?: boolean;
  mobileOpen?: boolean;
  onClose?: () => void;
  onSearch: (value: string) => void;
  onFilter: (value: string) => void;
  onUpload: (files: File[]) => void | Promise<void>;
  onRefresh: () => void | Promise<void>;
  onDelete: (path: string) => void | Promise<void>;
}

function bytes(value: number | string | undefined) {
  const size = Number(value || 0);
  if (!size) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB']; const index = Math.min(Math.floor(Math.log(size) / Math.log(1024)), units.length - 1);
  return `${(size / (1024 ** index)).toFixed(index ? 1 : 0)} ${units[index]}`;
}
function nameOf(file: WorkspaceFile, path: string) { return file.name || path.split('/').pop() || path; }
function fileUrl(sessionId: string, path: string) { return `/workspace/file?session_id=${encodeURIComponent(sessionId)}&path=${encodeURIComponent(path)}`; }

export function WorkspacePanel({
  sessionId, files, search, filter, busy = false, uploading = false, mobileOpen = false, onClose,
  onSearch, onFilter, onUpload, onRefresh, onDelete,
}: WorkspacePanelProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState('');
  const [pendingDelete, setPendingDelete] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const totalBytes = useMemo(() => files.reduce((sum, file) => sum + Number(file.size || 0), 0), [files]);
  const visible = useMemo(() => files.filter(file => {
    const path = workspacePathOf(file); const category = path.startsWith('uploads/') ? 'uploads' : 'outputs';
    return (!search.trim() || path.toLowerCase().includes(search.trim().toLowerCase())) && (filter === 'all' || filter === category);
  }), [files, filter, search]);
  const groups = useMemo(() => ({ uploads: visible.filter(file => workspacePathOf(file).startsWith('uploads/')), outputs: visible.filter(file => !workspacePathOf(file).startsWith('uploads/')) }), [visible]);

  const selectFiles = (list: FileList | File[] | null | undefined) => {
    const chosen = Array.from(list || []); if (!chosen.length || busy || uploading) return;
    setError(''); void Promise.resolve(onUpload(chosen)).catch(caught => setError(caught instanceof Error ? caught.message : 'Upload failed.'));
  };
  const refresh = () => {
    if (busy || uploading || refreshing) return;
    setError('');
    setRefreshing(true);
    void Promise.resolve()
      .then(() => onRefresh())
      .catch(caught => setError(caught instanceof Error ? caught.message : 'Refresh failed.'))
      .finally(() => setRefreshing(false));
  };
  const drop = (event: DragEvent<HTMLDivElement>) => { event.preventDefault(); setDragging(false); selectFiles(event.dataTransfer.files); };
  const onDropKey = (event: KeyboardEvent<HTMLDivElement>) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); inputRef.current?.click(); } };
  const remove = (path: string) => { setError(''); setPendingDelete(path); };
  const confirmRemove = () => {
    if (!pendingDelete) return;
    const path = pendingDelete; setPendingDelete(null);
    void Promise.resolve(onDelete(path)).catch(caught => setError(caught instanceof Error ? caught.message : 'Remove failed.'));
  };

  return <aside className={`right-sidebar workspace-drawer ${mobileOpen ? 'mobile-open' : ''}`} aria-label="Workspace files">
    {mobileOpen && onClose && <button className="workspace-scrim" type="button" aria-label="Close workspace" onClick={onClose} />}
    <section className="panel workspace-panel">
      <div className="panel-heading workspace-heading"><div><span className="eyebrow">Workspace</span><span className="panel-subtitle">{files.length} in this workspace</span></div>{mobileOpen && onClose && <button className="icon-button workspace-close" type="button" onClick={onClose} aria-label="Close workspace"><LineIcon name="close" /></button>}</div>
      <div className="workspace-actions" aria-label="Workspace actions"><button className="workspace-refresh-button" type="button" onClick={refresh} disabled={busy || uploading || refreshing} aria-busy={refreshing} aria-label={refreshing ? 'Refreshing workspace' : 'Refresh workspace'} title={refreshing ? 'Refreshing workspace' : 'Refresh workspace'}><LineIcon name="refresh" size={16} /><span>{refreshing ? 'Refreshing…' : 'Refresh'}</span></button><button className="upload-button" type="button" onClick={() => inputRef.current?.click()} disabled={busy || uploading || refreshing}><LineIcon name="clip" size={16} /><span>{uploading ? 'Uploading…' : 'Upload files'}</span></button></div>
      <input ref={inputRef} hidden type="file" multiple onChange={event => { selectFiles(event.target.files); event.currentTarget.value = ''; }} />
      <div className={`dropzone ${dragging ? 'dragging' : ''}`} role="button" tabIndex={0} onClick={() => inputRef.current?.click()} onKeyDown={onDropKey} onDragEnter={event => { event.preventDefault(); setDragging(true); }} onDragOver={event => { event.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={drop}><strong>{uploading ? 'Uploading files…' : 'Drop files here'}</strong><span>or choose Upload</span></div>
      <div className="workspace-summary">{files.length ? `${bytes(totalBytes)} · available to this chat and its tools` : 'Files are shared with this chat and its tools.'}</div>
      {error && <div className="workspace-error" role="status">{error}</div>}
      <div className="workspace-filters"><input value={search} onChange={event => onSearch(event.target.value)} placeholder="Find a file" aria-label="Find a workspace file" /><select value={filter} onChange={event => onFilter(event.target.value)} aria-label="Filter workspace files"><option value="all">All files</option><option value="uploads">Inputs</option><option value="outputs">Outputs</option></select></div>
      <div className="workspace-list">
        {!visible.length ? <div className="workspace-empty">{files.length ? 'No matching files.' : 'No files in this workspace yet.'}</div> : (['uploads', 'outputs'] as const).map(group => groups[group].length ? <div className="file-group" key={group}><div className="file-group-title"><span>{group === 'uploads' ? 'Inputs' : 'Outputs'}</span><span>{groups[group].length}</span></div>{groups[group].map(file => { const path = workspacePathOf(file); const name = nameOf(file, path); return <div className="file-item" key={path}><div className="file-info"><strong title={name}>{name}</strong><span>{bytes(file.size)} · {file.kind || 'file'}</span><small title={path}>{path}</small></div><div className="file-actions"><a href={fileUrl(sessionId, path)} download>Download</a><button type="button" onClick={() => remove(path)} disabled={busy || uploading}>Remove</button></div></div>; })}</div> : null)}
      </div>
    </section>
    {pendingDelete && <div className="workspace-delete-confirm" role="alertdialog" aria-label="Remove file confirmation"><span>Remove this file?</span><button type="button" onClick={confirmRemove}>Remove</button><button type="button" onClick={() => setPendingDelete(null)}>Cancel</button></div>}
  </aside>;
}

export { WorkspacePanel as Workspace };
