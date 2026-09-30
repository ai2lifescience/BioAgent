import type { ProgressEntry } from '../../types';
import { visibleProgress } from './progress';
import './progress.css';

export function RunProgress({ entries, running = false }: { entries: ProgressEntry[]; running?: boolean }) {
  const visible = visibleProgress(entries);
  const latestText = visible.filter(entry => entry.kind === 'text').at(-1);
  const activeTool = visible.filter(entry => entry.kind === 'tool' && entry.active).at(-1);
  const latest = visible.at(-1);
  const label = activeTool?.text || (latest?.kind === 'tool' ? 'Continuing…' : 'Working…');
  if (!running && !visible.length) return null;
  return <aside className={`run-progress ${running ? 'is-running' : 'is-finished'}`} aria-live="off" aria-label={running ? 'Live progress' : 'Run activity'}>
    {running && <>
      <div className="run-progress-status" role="status"><span className="run-progress-dot" aria-hidden="true" />{label}</div>
      {latestText && <p className="run-progress-preview">{latestText.text}</p>}
    </>}
    {visible.length > 0 && <details className="run-progress-details">
      <summary>{running ? 'Activity' : 'View activity'} <span>· {visible.length} {visible.length === 1 ? 'update' : 'updates'}</span></summary>
      <ol>{visible.map(entry => <li key={entry.id} className={`progress-${entry.kind}`}><span className="run-progress-marker" aria-hidden="true">{entry.kind === 'tool' ? (entry.active ? '·' : '✓') : '–'}</span><span>{entry.text}</span></li>)}</ol>
    </details>}
  </aside>;
}
