import { escapeHtml, fileNameFromPath } from "/static/ui-utils.js";

let igvModulePromise;
function loadIgv() {
  igvModulePromise ||= import("https://cdn.jsdelivr.net/npm/igv@3.0.0/dist/igv.esm.min.js")
    .then((module) => module.default)
    .catch((error) => { igvModulePromise = null; throw error; });
  return igvModulePromise;
}

// Keep every request tied to the session that rendered this card, including
// requests made after a slow CDN import or a conversation switch.
function referenceUrl(mapUrl, path) {
  if (typeof path !== "string" || !path || path.startsWith("/") || path.split("/").includes("..")) {
    throw new Error("Invalid genome reference path.");
  }
  const url = new URL(mapUrl, window.location.href);
  url.searchParams.set("path", path);
  return url.href;
}

function validateMap(map) {
  if (map.schema_version !== 1 || map.coordinates !== "0-based-half-open" ||
      !/^[A-Za-z0-9_.|+-]+$/.test(map.sequence_id || "") ||
      !Number.isSafeInteger(map.genome_length) || map.genome_length < 1 ||
      !["fasta", "chromsizes"].includes(map.reference_format) || !Array.isArray(map.features)) {
    throw new Error("Invalid genome browser artifact. Regenerate it with genome_render_map.");
  }
  for (const feature of map.features) {
    if (typeof feature.name !== "string" || typeof feature.feature_type !== "string" ||
        feature.chr !== map.sequence_id || !Number.isSafeInteger(feature.start) ||
        !Number.isSafeInteger(feature.end) || feature.start < 0 || feature.end <= feature.start ||
        feature.end > map.genome_length || !["+", "-", "."].includes(feature.strand) ||
        !/^#[0-9a-f]{6}$/i.test(feature.color)) {
      throw new Error("Genome feature coordinates or colors are invalid.");
    }
  }
  return map;
}

export function createGenomeViewers({ workspaceFileUrl }) {
  function collectGenomeMapArtifacts(result) {
    const artifacts = new Map();
    const evidence = result?.evidence || {};
    const add = (path) => {
      if (typeof path === "string" && fileNameFromPath(path).toLowerCase() === "genome_map.json") {
        artifacts.set(path, { path });
      }
    };
    for (const item of [...(evidence.outputs || []), ...(evidence.tool_outputs || [])]) add(item?.genome_map_path);
    if (!artifacts.size) {
      for (const item of result?.files || []) if (item?.kind === "genome_map") add(item.path);
    }
    return [...artifacts.values()];
  }

  function genomeViewerHtml(result) {
    return collectGenomeMapArtifacts(result).map(({ path }) => `
      <details class="genome-viewer-details" open>
        <summary>Genome browser <span>Explore annotations</span></summary>
        <section class="genome-viewer-card" data-genome-map-url="${escapeHtml(workspaceFileUrl(path))}">
          <div class="genome-viewer-heading">
            <div><span class="genome-eyebrow">SEQUENCE EXPLORER</span>
              <strong data-genome-title>Genome annotations</strong>
              <span data-genome-subtitle>Loading annotated sequence…</span></div>
            <button type="button" class="genome-reset" disabled>Full sequence</button>
          </div>
          <div class="genome-legend" aria-label="Feature types"></div>
          <div class="genome-viewport"><div class="genome-browser" role="region" aria-label="Interactive genome browser"></div></div>
          <p class="genome-status" role="status">Loading genome browser…</p>
          <button type="button" class="genome-retry" hidden>Retry genome browser</button>
          <div class="genome-viewer-footer"><span>Drag to pan · use + / − to zoom · click a feature for details</span>
            <a href="${escapeHtml(workspaceFileUrl(path))}" download="${escapeHtml(fileNameFromPath(path))}">Download data</a></div>
        </section>
      </details>
    `).join("");
  }

  function showError(card, error) {
    const status = card.querySelector(".genome-status");
    status.textContent = `Could not load the genome browser: ${error.message || error}. Check the connection and retry.`;
    status.hidden = false;
    card.querySelector(".genome-retry").hidden = false;
  }

  async function loadGenomeViewer(card) {
    const state = card._genomeState;
    if (state.disposed || state.loading || state.browser) return;
    state.loading = true;
    // IGV attaches a shadow root, so retries need a fresh host element.
    const oldHost = card.querySelector(".genome-browser");
    const host = oldHost.cloneNode(false);
    oldHost.replaceWith(host);
    const status = card.querySelector(".genome-status");
    status.textContent = "Loading genome browser…";
    status.hidden = false;
    card.querySelector(".genome-retry").hidden = true;
    try {
      const mapUrl = card.dataset.genomeMapUrl;
      const response = await fetch(mapUrl, { signal: state.abort.signal });
      if (!response.ok) throw new Error(`Genome data returned HTTP ${response.status}`);
      const map = validateMap(await response.json());
      const fastaURL = referenceUrl(mapUrl, map.reference_path);
      const igv = await loadIgv();
      if (state.disposed) return;
      state.igv = igv;
      card.querySelector("[data-genome-title]").textContent = map.title || map.sequence_id;
      card.querySelector("[data-genome-subtitle]").textContent =
        `${map.sequence_id} · ${map.genome_length.toLocaleString()} bp · ${map.features.length.toLocaleString()} feature segments`;
      const types = new Map(map.features.map((f) => [f.feature_type, f.color]));
      card.querySelector(".genome-legend").innerHTML = [...types].map(([type, color]) =>
        `<span><i style="background:${color}" aria-hidden="true"></i>${escapeHtml(type)}</span>`).join("");
      const locus = `${map.sequence_id}:1-${map.genome_length}`;
      const browser = await igv.createBrowser(host, {
        reference: {
          id: map.sequence_id, name: escapeHtml(map.title || map.sequence_id),
          fastaURL, format: map.reference_format, wholeGenomeView: false,
        },
        locus,
        tracks: [{
          name: "Annotations", type: "annotation", format: "bed",
          // IGV uses feature names in HTML popups as well as canvas labels.
          features: map.features.map((f) => ({
            chr: f.chr, start: f.start, end: f.end, strand: f.strand, color: f.color,
            name: escapeHtml(f.name), feature_type: escapeHtml(f.feature_type),
          })),
          displayMode: "EXPANDED", height: 160, expandedRowHeight: 30, maxRows: 1000,
          searchable: true, visibilityWindow: -1,
        }],
        showNavigation: true, showRuler: true, showIdeogram: false,
        showSVGButton: true, showCenterGuide: false, showCursorGuide: false,
        showTrackLabels: true, minimumBases: Math.min(10, map.genome_length),
      });
      if (state.disposed) { igv.removeBrowser(browser); return; }
      state.browser = browser;
      if (map.reference_format === "chromsizes") {
        for (const { track } of [...browser.trackViews]) if (track.type === "sequence") browser.removeTrack(track);
      }
      const notices = [];
      if (!map.features.length) notices.push("No annotated features were found.");
      if (map.truncated) notices.push("This view contains the first 50,000 feature segments.");
      if (map.reference_format === "chromsizes") notices.push("Annotations only; rerun feature extraction with sequence data to see bases.");
      status.textContent = notices.join(" ");
      status.hidden = !notices.length;
      const reset = card.querySelector(".genome-reset");
      reset.disabled = false;
      reset.onclick = () => browser.search(locus).catch((error) => showError(card, error));
      state.observer = new ResizeObserver(() => {
        const width = host.clientWidth;
        if (width > 0 && width !== state.width) {
          state.width = width;
          browser.visibilityChange().catch((error) => { if (!state.disposed) showError(card, error); });
        }
      });
      state.observer.observe(host);
    } catch (error) {
      if (!state.disposed) {
        state.observer?.disconnect();
        if (state.browser) state.igv.removeBrowser(state.browser);
        state.browser = null;
        host.replaceWith(host.cloneNode(false));
        card.querySelector(".genome-reset").disabled = true;
        showError(card, error);
      }
    } finally {
      state.loading = false;
    }
  }

  function initializeGenomeViewers(root = document) {
    root.querySelectorAll(".genome-viewer-card").forEach((card) => {
      if (card._genomeState) return;
      card._genomeState = { abort: new AbortController(), disposed: false };
      const details = card.closest("details");
      details.addEventListener("toggle", () => { if (details.open) loadGenomeViewer(card); });
      card.querySelector(".genome-retry").onclick = () => {
        const state = card._genomeState;
        state.observer?.disconnect();
        state.observer = null;
        if (state.browser && state.igv) state.igv.removeBrowser(state.browser);
        state.browser = null;
        loadGenomeViewer(card);
      };
      if (details.open) loadGenomeViewer(card);
    });
  }

  function disposeGenomeViewers(root = document) {
    root.querySelectorAll(".genome-viewer-card").forEach((card) => {
      const state = card._genomeState;
      if (!state || state.disposed) return;
      state.disposed = true;
      state.abort.abort();
      state.observer?.disconnect();
      if (state.browser) state.igv.removeBrowser(state.browser);
    });
  }

  return { collectGenomeMapArtifacts, genomeViewerHtml, initializeGenomeViewers, disposeGenomeViewers };
}
