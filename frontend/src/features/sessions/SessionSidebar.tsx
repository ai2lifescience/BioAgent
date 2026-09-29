import { useEffect, useMemo, useRef, useState } from 'react';
import type { KeyboardEvent as ReactKeyboardEvent } from 'react';
import type { SessionSummary } from '../../types';
import { AgentIcon, LineIcon } from '../../components/icons';

export interface SessionSidebarProps {
  sessions: SessionSummary[];
  activeId: string;
  collapsed?: boolean;
  mobileOpen?: boolean;
  disabled?: boolean;
  onToggle: () => void;
  onMobileClose?: () => void;
  onSelect: (id: string) => void | Promise<void>;
  onNew: () => void | Promise<void>;
  onRename: (id: string, title: string) => void | Promise<void>;
  onPin: (id: string, pinned: boolean) => void | Promise<void>;
  onDelete: (id: string) => void | Promise<void>;
}

function Icon({ name }: { name: 'plus' | 'chevron' | 'more' | 'pin' | 'edit' | 'trash' }) {
  return <LineIcon name={name} />;
}

function formatTime(value: string | undefined) {
  if (!value) return 'No activity';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? 'No activity' : date.toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

export function SessionSidebar({
  sessions, activeId, collapsed = false, mobileOpen = false, disabled = false,
  onToggle, onMobileClose, onSelect, onNew, onRename, onPin, onDelete,
}: SessionSidebarProps) {
  const [menuId, setMenuId] = useState<string | null>(null);
  const [renameId, setRenameId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState('');
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState('');
  const renameRef = useRef<HTMLInputElement>(null);

  const ordered = useMemo(() => [...sessions].sort((left, right) => {
    if (Boolean(left.pinned) !== Boolean(right.pinned)) return left.pinned ? -1 : 1;
    return new Date(right.updated_at || right.created_at).getTime() - new Date(left.updated_at || left.created_at).getTime();
  }), [sessions]);
  const session = (id: string | null) => sessions.find(item => item.id === id);
  // Keep desktop navigation state independent from the mobile drawer.  The
  // parent passes `onMobileClose` for both layouts so it can close the drawer
  // after a mobile selection; calling it unconditionally used to collapse the
  // desktop sidebar whenever a conversation was selected.
  const closeMobile = () => { if (mobileOpen) onMobileClose?.(); };

  const closeActions = () => { setMenuId(null); setRenameId(null); setDeleteId(null); };

  useEffect(() => { if (renameId) renameRef.current?.focus(); }, [renameId]);
  useEffect(() => {
    // Session changes and a new run invalidate any open conversation actions.
    setMenuId(null); setRenameId(null); setDeleteId(null);
  }, [activeId, disabled, collapsed, mobileOpen]);
  useEffect(() => {
    if (!menuId) return;
    const closeOutsideMenu = (event: PointerEvent) => {
      if (!(event.target instanceof Element) || !event.target.closest('.session-menu, .session-more')) setMenuId(null);
    };
    document.addEventListener('pointerdown', closeOutsideMenu);
    return () => document.removeEventListener('pointerdown', closeOutsideMenu);
  }, [menuId]);
  useEffect(() => {
    const close = (event: globalThis.KeyboardEvent) => { if (event.key === 'Escape') { setMenuId(null); setRenameId(null); setDeleteId(null); } };
    window.addEventListener('keydown', close); return () => window.removeEventListener('keydown', close);
  }, []);

  const run = async (id: string, action: () => void | Promise<void>) => {
    setError(''); setBusyId(id);
    try { await action(); setMenuId(null); setRenameId(null); setDeleteId(null); }
    catch (caught) { setError(caught instanceof Error ? caught.message : 'Could not update this chat.'); }
    finally { setBusyId(null); }
  };
  const beginRename = (item: SessionSummary) => { setError(''); setMenuId(null); setDeleteId(null); setRenameId(item.id); setRenameValue(item.title || 'New chat'); };
  const submitRename = (event?: ReactKeyboardEvent<HTMLInputElement>) => {
    if (event?.key === 'Escape') { setRenameId(null); return; }
    if (event?.key === 'Enter') event.preventDefault(); else if (event) return;
    const value = renameValue.replace(/\s+/g, ' ').trim().slice(0, 80);
    const item = session(renameId);
    if (!item || !value || value === item.title) { setRenameId(null); return; }
    void run(item.id, () => onRename(item.id, value));
  };

  return <aside className={`left-sidebar ${collapsed ? 'sidebar-collapsed' : ''} ${mobileOpen ? 'mobile-open' : ''}`} aria-label="Conversation navigation">
    <div className="brand">
      <div className="robot-mark" aria-hidden="true"><AgentIcon size={43} /></div>
      <div className="brand-copy"><strong>Pipeline2Agent</strong><span>Bioinformatics workspace</span></div>
      <button className="collapse-button" type="button" onClick={() => { closeActions(); onToggle(); }} aria-expanded={!collapsed} aria-label={collapsed ? 'Expand conversations' : 'Collapse conversations'}><Icon name="chevron" /></button>
    </div>
    {mobileOpen && onMobileClose && <button className="sidebar-scrim" type="button" aria-label="Close navigation" onClick={onMobileClose} />}
    <div className="side-content">
      <button className="new-chat" type="button" disabled={disabled} onClick={() => { closeActions(); setError(''); void Promise.resolve(onNew()).then(closeMobile).catch(caught => setError(caught instanceof Error ? caught.message : 'Could not create a new chat.')); }}><Icon name="plus" /><span>New chat</span></button>
      <section className="panel sessions-panel" aria-labelledby="sessions-heading">
        <div className="panel-heading"><div><span id="sessions-heading" className="eyebrow">Conversations</span><span className="panel-subtitle">{sessions.length} saved</span></div></div>
        {error && <div className="session-action-error" role="status">{error}</div>}
        <div className="session-list" role="list">
          {ordered.length ? ordered.map(item => {
            const selected = activeId === item.id; const actionBusy = busyId === item.id;
            return <div key={item.id} className={`session-row ${selected ? 'active' : ''}`} role="listitem">
              {renameId === item.id ? <form className="session-rename" onSubmit={event => { event.preventDefault(); submitRename(); }}>
                <input ref={renameRef} value={renameValue} maxLength={80} aria-label="Chat name" onChange={event => setRenameValue(event.target.value)} onKeyDown={submitRename} disabled={actionBusy} />
                <button type="submit" disabled={actionBusy || !renameValue.trim()}>Save</button><button type="button" onClick={() => setRenameId(null)}>Cancel</button>
              </form> : <>
                <button className="session-button" type="button" disabled={disabled || actionBusy} onClick={() => { closeActions(); setError(''); void Promise.resolve(onSelect(item.id)).catch(caught => setError(caught instanceof Error ? caught.message : 'Could not open this chat.')); closeMobile(); }}>
                  <strong>{item.title || 'New chat'}</strong><span>{formatTime(item.updated_at)} · {item.message_count || item.messages?.length || 0} {Number(item.message_count || item.messages?.length || 0) === 1 ? 'message' : 'messages'}</span>
                </button>
                {item.pinned && <span className="pinned" title="Pinned"><Icon name="pin" /></span>}
                <button className="session-more" type="button" disabled={disabled || actionBusy} aria-haspopup="menu" aria-expanded={menuId === item.id} aria-label={`Actions for ${item.title || 'chat'}`} onClick={() => setMenuId(menuId === item.id ? null : item.id)}><Icon name="more" /></button>
                {menuId === item.id && <div className="session-menu" role="menu">
                  <button type="button" role="menuitem" onClick={() => void run(item.id, () => onPin(item.id, !item.pinned))}><Icon name="pin" />{item.pinned ? 'Unpin chat' : 'Pin chat'}</button>
                  <button type="button" role="menuitem" onClick={() => beginRename(item)}><Icon name="edit" />Rename chat</button>
                  <button type="button" role="menuitem" className="danger" onClick={() => { setMenuId(null); setDeleteId(item.id); }}><Icon name="trash" />Delete chat</button>
                </div>}
                {deleteId === item.id && <div className="session-delete-confirm" role="alertdialog" aria-label="Delete chat confirmation"><span>Delete this chat?</span><button type="button" onClick={() => void run(item.id, () => onDelete(item.id))} disabled={actionBusy}>Delete</button><button type="button" onClick={() => setDeleteId(null)}>Cancel</button></div>}
              </>}
            </div>;
          }) : <div className="session-empty">Your conversations will appear here.</div>}
        </div>
      </section>
    </div>
  </aside>;
}

export { SessionSidebar as Sidebar };
