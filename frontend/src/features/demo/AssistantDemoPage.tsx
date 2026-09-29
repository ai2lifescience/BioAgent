import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AssistantDrawer, type AssistantDrawerHandle } from '../assistant/assistantEmbed';
import './demo.css';

type Row = { sample: string; group: 'control' | 'treated'; score: number };
type Point = { value: number; group: 'control' | 'treated' };
const rows: Row[] = [
  { sample: 'S1', group: 'control', score: .42 }, { sample: 'S2', group: 'treated', score: .81 },
  { sample: 'S3', group: 'treated', score: .67 }, { sample: 'S4', group: 'control', score: .31 },
];
const abundance: Point[] = [
  { value: .12, group: 'control' }, { value: .31, group: 'treated' }, { value: .24, group: 'control' },
  { value: .55, group: 'treated' }, { value: .43, group: 'control' }, { value: .72, group: 'treated' },
];

export function AssistantDemoPage() {
  const [group, setGroup] = useState<'all' | 'control' | 'treated'>('all');
  const [revision, setRevision] = useState(1);
  const [workflowRoute, setWorkflowRoute] = useState('review');
  const [methodsOpen, setMethodsOpen] = useState(false);
  const [connection, setConnection] = useState('Connecting website…');
  const assistantRoot = useRef<HTMLDivElement>(null);
  const drawerRef = useRef<AssistantDrawerHandle | null>(null);
  const visibleRows = useMemo(() => rows.filter(row => group === 'all' || row.group === group), [group]);
  const visiblePoints = useMemo(() => abundance.filter(point => group === 'all' || point.group === group), [group]);
  const label = group === 'all' ? 'All samples' : `${group[0].toUpperCase()}${group.slice(1)} cohort`;
  const stateRef = useRef({ group, revision, workflowRoute, visibleRows, visiblePoints, label });
  stateRef.current = { group, revision, workflowRoute, visibleRows, visiblePoints, label };
  const mean = visibleRows.length ? visibleRows.reduce((sum, row) => sum + row.score, 0) / visibleRows.length : 0;
  const spread = visibleRows.length ? Math.max(...visibleRows.map(row => row.score)) - Math.min(...visibleRows.map(row => row.score)) : 0;
  const pageContext = useCallback(() => ({
    revision: `comparison-${revision}`, title: 'Sample comparison', url: window.location.href,
    selection: { group }, filters: { group }, workflow: { step: workflowRoute, steps: ['select', 'review', 'export'] },
    resources: [{ id: 'measurements', kind: 'table', title: 'Measurements', exportable: true }, { id: 'abundance', kind: 'figure', title: 'Relative abundance' }],
    elements: [{ id: 'measurements', label: 'Measurements table' }, { id: 'filter', label: 'Group filter' }],
    routes: [{ id: 'methods', label: 'Methods' }], actions: [{ id: 'set_group_filter', description: 'Filter samples by group', parameters: { group: ['all', 'treated', 'control'] } }], manual: { version: '2026-09', title: 'Sample comparison methods' },
  }), [group, revision, workflowRoute]);
  const updatePage = useCallback((nextGroup: 'all' | 'control' | 'treated') => { setGroup(nextGroup); setRevision(value => value + 1); setWorkflowRoute('review'); }, []);
  useEffect(() => {
    if (!assistantRoot.current) return;
    const adapter = {
      getPageContext: () => { const current = stateRef.current; return { revision: `comparison-${current.revision}`, title: 'Sample comparison', url: window.location.href, selection: { group: current.group }, filters: { group: current.group }, workflow: { step: current.workflowRoute, steps: ['select', 'review', 'export'] }, resources: [{ id: 'measurements', kind: 'table', title: 'Measurements', exportable: true }, { id: 'abundance', kind: 'figure', title: 'Relative abundance' }], elements: [{ id: 'measurements', label: 'Measurements table' }, { id: 'filter', label: 'Group filter' }], routes: [{ id: 'methods', label: 'Methods' }], actions: [{ id: 'set_group_filter', description: 'Filter samples by group', parameters: { group: ['all', 'treated', 'control'] } }], manual: { version: '2026-09', title: 'Sample comparison methods' } }; },
      readTable: ({ resource_id, offset = 0, limit = 50 }: Record<string, any>) => {
        const current = stateRef.current; if (resource_id !== 'measurements') throw new Error(`Unknown table: ${resource_id}`);
        return { resource_id, title: 'Measurements', columns: [{ name: 'sample', type: 'string' }, { name: 'group', type: 'string' }, { name: 'score', type: 'number' }], rows: current.visibleRows.slice(Number(offset) || 0, (Number(offset) || 0) + (Number(limit) || 50)), offset: Number(offset) || 0, total_rows: current.visibleRows.length, revision: `comparison-${current.revision}`, filters: { group: current.group } };
      },
      readFigure: ({ resource_id }: Record<string, any>) => {
        const current = stateRef.current; if (resource_id !== 'abundance') throw new Error(`Unknown figure: ${resource_id}`);
        return { resource_id, title: 'Relative abundance', description: `${current.visiblePoints.length} ordered observations for ${current.label.toLowerCase()}.`, x_axis: { label: 'Observation' }, y_axis: { label: 'Relative abundance', unit: 'fraction' }, series: [{ name: 'Observed', values: current.visiblePoints.map(point => point.value) }], filters: { group: current.group }, revision: `comparison-${current.revision}` };
      },
      searchManual: ({ query }: Record<string, any>) => ({ version: '2026-09', sections: [{ id: 'methods', title: 'Methods', excerpt: `Use the group filter to change cohort, then inspect Measurements (${query || 'methods'}).` }] }),
      readManual: () => ({ section_id: 'methods', title: 'Methods', version: '2026-09', text: 'Use the group filter to change cohort, then inspect Measurements. Export data when an analysis needs the complete table.' }),
      exportData: () => ({ filename: 'measurements.csv', content: `sample,group,score\n${stateRef.current.visibleRows.map(row => `${row.sample},${row.group},${row.score}`).join('\n')}`, content_type: 'text/csv' }),
      highlight: ({ element_id, message }: Record<string, any>) => { document.getElementById(String(element_id))?.scrollIntoView({ behavior: 'smooth', block: 'center' }); return { message: message || `Highlighted ${element_id}`, revision: `comparison-${stateRef.current.revision}` }; },
      navigate: ({ route_id }: Record<string, any>) => { if (route_id !== 'methods') throw new Error(`Unknown route: ${route_id}`); setMethodsOpen(true); window.location.hash = 'methods'; return { message: 'Opened Methods', revision: `comparison-${stateRef.current.revision}` }; },
      invokeAction: ({ action_id, arguments: args }: Record<string, any>) => { if (action_id !== 'set_group_filter') throw new Error(`Unknown action: ${action_id}`); const next = args?.group; if (!['all', 'treated', 'control'].includes(next)) throw new Error('group must be all, treated, or control'); updatePage(next); return { action_id, message: `Group set to ${next}`, revision: `comparison-${stateRef.current.revision + 1}`, filters: { group: next } }; },
    };
    const handle = AssistantDrawer.mount({ target: assistantRoot.current, src: '/assistant', siteId: 'assistant-demo', title: 'Website assistant', launcherLabel: 'Ask assistant', open: true, context: pageContext(), getToken: async () => { const response = await fetch('/website/demo-token', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ site_id: 'assistant-demo' }) }); const payload = await response.json(); if (!response.ok) throw new Error(payload.error || 'Demo ticket request failed'); return String(payload.token || ''); }, onEvent: event => { if (event.type === 'website-connected') setConnection('Trusted website connected'); if (event.type === 'website-error') setConnection('Website connection needs attention'); }, adapter });
    drawerRef.current = handle;
    return () => { handle.destroy(); drawerRef.current = null; };
  }, []); // Adapter callbacks close over the initial state only through refs below.

  // Keep the adapter context current without remounting the drawer.
  useEffect(() => { drawerRef.current?.updateContext(pageContext()).catch(() => undefined); }, [pageContext]);
  const chartPoints = visiblePoints.map((point, index) => { const left = 48; const width = 620 - left - 20; const top = 20; const height = 275 - top - 39; const x = visiblePoints.length === 1 ? left + width / 2 : left + width * index / (visiblePoints.length - 1); const y = top + height - point.value / .8 * height; return { ...point, x, y }; });
  const chartLine = chartPoints.map(point => `${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(' ');
  const chartArea = chartPoints.length ? `M 48 236 L ${chartPoints.map(point => `${point.x.toFixed(1)} ${point.y.toFixed(1)}`).join(' L ')} L ${chartPoints.at(-1)?.x.toFixed(1)} 236 Z` : '';
  const renderRevision = () => { setRevision(value => value + 1); setWorkflowRoute('review'); };
  return <main className="demo-page"><header className="demo-topbar"><div className="demo-brand"><div><p className="demo-eyebrow">Website bridge fixture</p><strong>Analysis workspace</strong></div></div><div id="connectionStatus" className="demo-connection"><span className="demo-connection-dot" /><span id="connectionText">{connection}</span></div></header><section className="demo-hero"><div><p className="demo-eyebrow">Review workflow · Step 2 of 3</p><h1 id="page-title">Sample comparison</h1><p>Compare treatment response across the current cohort. The embedded assistant can inspect this table, interpret the figure, and apply the registered group filter.</p></div><div className="demo-hero-actions"><span>Active cohort: <strong id="activeGroup">{label}</strong></span><button id="filter" className="demo-pill" type="button" aria-pressed={group !== 'all'} onClick={() => updatePage(group === 'all' ? 'treated' : 'all')}>{group === 'all' ? 'Show treated cohort' : 'Show all samples'}</button></div></section><section className="demo-metrics" aria-label="Comparison summary"><Metric id="sampleCount" label="Samples shown" value={String(visibleRows.length)} note={group === 'all' ? '2 control · 2 treated' : `${visibleRows.length} ${group} samples`} /><Metric id="meanScore" label="Mean score" value={mean.toFixed(2)} note="Across visible samples" /><Metric id="scoreSpread" label="Score spread" value={spread.toFixed(2)} note="Maximum minus minimum" /><Metric id="revisionValue" label="Revision" value={String(revision)} note="Updates after every action" /></section><section className="demo-content-grid"><article className="demo-panel" aria-labelledby="figure-title"><div className="demo-panel-heading"><div><h2 id="figure-title">Relative abundance</h2><p id="figureSubtitle">{visiblePoints.length} ordered observations · {group === 'all' ? 'all cohorts' : `${label.toLowerCase()}`}</p></div><span className="demo-panel-tag">Live figure</span></div><div className="demo-chart-box"><svg id="chart" className="demo-chart" viewBox="0 0 620 275" role="img" aria-label="Relative abundance chart"><defs><linearGradient id="demo-area-fill" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stopColor="#159487" stopOpacity=".25" /><stop offset="1" stopColor="#159487" stopOpacity="0" /></linearGradient></defs>{[0, .2, .4, .6, .8].map(value => <g key={value}><line className="demo-grid-line" x1="48" x2="600" y1={20 + 216 - value / .8 * 216} y2={20 + 216 - value / .8 * 216} /><text className="demo-axis-label" x="10" y={24 + 216 - value / .8 * 216}>{value.toFixed(1)}</text></g>)}<path className="demo-series-area" d={chartArea} /><polyline className="demo-series-line" points={chartLine} />{chartPoints.map((point, index) => <g key={`${point.value}-${index}`}><circle className="demo-series-dot" cx={point.x} cy={point.y} r="5" /><text className="demo-axis-label" textAnchor="middle" x={point.x} y="262">{index + 1}</text></g>)}</svg></div></article><article id="measurements" className="demo-panel" aria-labelledby="table-title"><div className="demo-panel-heading"><div><h2 id="table-title">Measurements</h2><p id="tableSubtitle">{group === 'all' ? 'Showing every sample' : `Showing ${visibleRows.length} ${group} samples`}</p></div><span className="demo-panel-tag">Structured table</span></div><div className="demo-table-wrap"><table id="measurements"><thead><tr><th>Sample</th><th>Group</th><th>Score</th></tr></thead><tbody>{visibleRows.map(row => <tr key={row.sample}><td>{row.sample}</td><td>{row.group}</td><td className="score">{row.score.toFixed(2)}</td></tr>)}</tbody></table></div></article></section><section id="methods" className="demo-panel demo-workflow-panel"><div className="demo-workflow-content"><div><div className="demo-panel-heading"><div><h2>Workflow and methods</h2><p id="workflow">{methodsOpen ? 'Methods opened. Use the group filter to change cohort, then inspect Measurements.' : 'Review the comparison, then export the selected cohort for downstream analysis.'}</p></div></div><div className="demo-steps"><span><b>1</b>Select</span><span><b>2</b>Review</span><span><b className="inactive">3</b>Export</span></div></div><div><div className="demo-manual-card"><strong>Methods · v2026-09</strong><span>Use the group filter to change cohort, then inspect Measurements.</span></div><button id="methods" className="demo-pill demo-methods-button" type="button" onClick={() => { setMethodsOpen(true); setWorkflowRoute('review'); renderRevision(); window.location.hash = 'methods'; }}>Open methods</button></div></div></section><div id="assistant-root" ref={assistantRoot} /></main>;
}

function Metric({ id, label, value, note }: { id?: string; label: string; value: string; note: string }) { return <article className="demo-metric" id={id}><div className="demo-metric-label">{label}</div><div className="demo-metric-value">{value}</div><div className="demo-metric-note">{note}</div></article>; }
export default AssistantDemoPage;
