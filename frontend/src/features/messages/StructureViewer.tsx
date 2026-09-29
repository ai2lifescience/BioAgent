import { useEffect, useRef, useState } from 'react';
import type { AtomSpec, AtomStyleSpec, GLViewer } from '3dmol';
import './StructureViewer.css';

type Structure = { path: string; label: string; pdbId: string; format: 'pdb' | 'cif' };
type Representation = 'ribbons' | 'sticks' | 'spheres' | 'lines';
type Chain = { id: string; color: string; polymer: boolean };
type Scene = { chains: Chain[]; ligands: string[]; hasPolymer: boolean };

// Use the reference's restrained palette, consistently for both model and legend.
const chainColors = ['#22b8cf', '#bfc5cc', '#e83e8c', '#7950f2', '#e5a142', '#51a781', '#467ac6', '#b77565'];
const waterNames = new Set(['HOH', 'WAT', 'H2O', 'DOD']);
const isWater = (atom: AtomSpec) => waterNames.has((atom.resn || '').toUpperCase());
const isLigand = (atom: AtomSpec) => Boolean(atom.hetflag) && !isWater(atom);

function describeScene(atoms: AtomSpec[]): Scene {
  const visible = atoms.filter(atom => !isWater(atom));
  const ids = [...new Set(visible.map(atom => atom.chain || ''))].sort();
  return {
    chains: ids.map((id, index) => ({
      id, color: chainColors[index % chainColors.length],
      polymer: visible.some(atom => (atom.chain || '') === id && !atom.hetflag),
    })),
    ligands: [...new Set(visible.filter(isLigand).map(atom => atom.resn || 'Ligand'))].sort(),
    hasPolymer: visible.some(atom => !atom.hetflag),
  };
}

function styleScene(viewer: GLViewer, scene: Scene, representation: Representation, ligands: boolean) {
  viewer.setStyle({}, {});
  for (const chain of scene.chains) {
    const selection = { predicate: (atom: AtomSpec) => (atom.chain || '') === chain.id && !isWater(atom) && !atom.hetflag };
    const color = chain.color;
    const style: AtomStyleSpec = representation === 'ribbons' ? { cartoon: { color } }
      : representation === 'sticks' ? { stick: { color, radius: .16 } }
      : representation === 'spheres' ? { sphere: { color, scale: .3 } }
      : { line: { color } };
    viewer.setStyle(selection, style);
    // Restrict the optional atom overlay to non-water ligands only.
    if (ligands || !scene.hasPolymer) {
      viewer.setStyle({ predicate: atom => (atom.chain || '') === chain.id && isLigand(atom) }, {
        stick: { color, radius: .16 }, sphere: { color, scale: .2 },
      });
    }
  }
  viewer.render();
}

export function StructureViewer({ item, src }: { item: Structure; src: string }) {
  const host = useRef<HTMLDivElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const viewer = useRef<GLViewer | null>(null);
  const initialView = useRef<number[] | null>(null);
  const [open, setOpen] = useState(true);
  const [scene, setScene] = useState<Scene | null>(null);
  const [representation, setRepresentation] = useState<Representation>('ribbons');
  const [showLigands, setShowLigands] = useState(true);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  const [fullscreen, setFullscreen] = useState(false);
  const [viewNotice, setViewNotice] = useState('');
  const title = item.pdbId ? `PDB ${item.pdbId}` : item.label;

  useEffect(() => {
    const element = host.current;
    if (!element) return;
    let disposed = false;
    let instance: GLViewer | null = null;
    const controller = new AbortController();
    setLoading(true); setError(''); setScene(null); initialView.current = null;
    (async () => {
      try {
        const [{ createViewer }, response] = await Promise.all([
          import('3dmol/build/3Dmol.es6-min.js'), fetch(src, { signal: controller.signal }),
        ]);
        if (!response.ok) throw new Error(`Structure request failed (${response.status}).`);
        const text = await response.text();
        if (disposed) return;
        instance = createViewer(element, { backgroundColor: 'white', antialias: true, disableFog: true, orthographic: true });
        const model = instance.addModel(text, item.format);
        const atoms = model.selectedAtoms({});
        if (!atoms.some(atom => !isWater(atom))) throw new Error('No displayable atoms were found in this structure.');
        const next = describeScene(atoms);
        instance.zoomTo({ predicate: atom => !isWater(atom) });
        instance.zoom(1.3);
        initialView.current = instance.getView();
        viewer.current = instance;
        setScene(next);
        setLoading(false);
      } catch (cause) {
        if (disposed) return;
        instance?.clear(); element.replaceChildren(); viewer.current = null;
        setError(cause instanceof Error ? cause.message : String(cause));
        setLoading(false);
      }
    })();
    return () => {
      disposed = true; controller.abort();
      instance?.clear(); element.replaceChildren(); viewer.current = null;
    };
  }, [src, item.format, retry]);

  useEffect(() => {
    if (viewer.current && scene) styleScene(viewer.current, scene, representation, showLigands);
  }, [scene, representation, showLigands]);

  useEffect(() => {
    const update = () => setFullscreen(document.fullscreenElement === panel.current);
    document.addEventListener('fullscreenchange', update);
    return () => document.removeEventListener('fullscreenchange', update);
  }, []);

  const resetView = () => {
    if (!viewer.current || !initialView.current) return;
    viewer.current.setView(initialView.current);
    viewer.current.render();
  };
  const toggleFullscreen = async () => {
    setViewNotice('');
    try {
      if (document.fullscreenElement === panel.current) await document.exitFullscreen();
      else await panel.current?.requestFullscreen();
    } catch { setViewNotice('Fullscreen is unavailable in this browser.'); }
  };

  return <details className="structure-viewer-details" open={open} onToggle={event => setOpen(event.currentTarget.open)}>
    <summary>3D structure <span>{open ? 'Hide viewer' : 'Open viewer'}</span></summary>
    <div ref={panel} className="structure-viewer">
      <div className="structure-visual" aria-busy={loading}>
        <div ref={host} className="structure-canvas" role="img" aria-label={`Interactive molecular structure viewer: ${title}`} />
        {loading && <div className="structure-overlay structure-loading" role="status">Loading structure…</div>}
        {error && <div className="structure-overlay structure-error" role="alert"><strong>Could not display the structure</strong><span>{error}</span><button type="button" onClick={() => setRetry(value => value + 1)}>Try again</button><a href={src} download>Download structure</a></div>}
        {scene && !error && <aside className="structure-legend" aria-label="Structure chain legend">
          <strong>{title}</strong>
          <span className="structure-legend-subtitle">{scene.chains.length} {scene.chains.length === 1 ? 'chain' : 'chains'} · {item.format === 'cif' ? 'mmCIF' : 'PDB'}</span>
          <ul>{scene.chains.map(chain => <li key={chain.id}><span className="structure-swatch" style={{ backgroundColor: chain.color }} aria-hidden="true" /><span>Chain {chain.id || '(unnamed)'}{!chain.polymer && ' · ligands'}</span></li>)}</ul>
          {scene.ligands.length > 0 && <small>Ligands{showLigands ? '' : ' (hidden)'}: {scene.ligands.join(', ')}</small>}
        </aside>}
        <span className="structure-note">Drag to rotate · scroll to zoom</span>
      </div>
      <div className="structure-toolbar">
        <div className="structure-representations" role="group" aria-label="Structure representation">{(['ribbons', 'sticks', 'spheres', 'lines'] as const).map(value => <button key={value} type="button" aria-pressed={representation === value} disabled={!scene || !scene.hasPolymer} onClick={() => setRepresentation(value)}>{value[0].toUpperCase() + value.slice(1)}</button>)}</div>
        {scene?.hasPolymer && scene.ligands.length > 0 && <label className="structure-ligand-toggle"><input type="checkbox" checked={showLigands} onChange={event => setShowLigands(event.target.checked)} />Ligands</label>}
        <div className="structure-view-actions"><button type="button" onClick={resetView} disabled={!scene}>Reset view</button>{document.fullscreenEnabled && <button type="button" onClick={() => void toggleFullscreen()}>{fullscreen ? 'Exit fullscreen' : 'Fullscreen'}</button>}<a href={src} download title={item.path}>Download {item.format === 'cif' ? 'mmCIF' : 'PDB'}</a></div>
      </div>
      {viewNotice && <div className="structure-view-notice" role="status">{viewNotice}</div>}
    </div>
  </details>;
}
