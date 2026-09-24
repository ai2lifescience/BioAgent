import { escapeHtml, fileNameFromPath } from "/static/ui-utils.js";
import { createGenomeViewers } from "/static/genome-viewer.js";

const PUBLICATION_CHAIN_COLORS = Object.freeze({
  A: "#18a7b5",
  B: "#cfcfcf",
  H: "#d94f91",
  L: "#7768d8",
});
const PUBLICATION_PALETTE = Object.freeze([
  "#18a7b5",
  "#d28b37",
  "#7768d8",
  "#d94f91",
  "#4f8edb",
  "#4f9d79",
  "#c96854",
  "#64748b",
]);
export function createArtifactViewers({
  getStructureSuffixes,
  getImageSuffixes,
  workspaceFileUrl,
} = {}) {
  const isStructurePath = (path) => {
    const clean = String(path || "").toLowerCase().split(/[?#]/)[0];
    return (getStructureSuffixes?.() || [".cif", ".mmcif", ".pdb"])
      .some((suffix) => clean.endsWith(suffix));
  };

  const isImagePath = (path) => {
    const clean = String(path || "").toLowerCase().split(/[?#]/)[0];
    return (getImageSuffixes?.() || [".svg"]).some((suffix) => clean.endsWith(suffix));
  };

  const structureFormat = (path) => String(path || "").toLowerCase().endsWith(".pdb") ? "pdb" : "cif";

  function chainIdsFromModel(model) {
    if (!model || typeof model.selectedAtoms !== "function") return [];
    try {
      const atoms = model.selectedAtoms({}) || [];
      return [...new Set(atoms
        .map((atom) => String(atom?.chain || atom?.chainid || "").trim())
        .filter(Boolean))];
    } catch (_) {
      return [];
    }
  }

  function chainColor(chain, index) {
    return PUBLICATION_CHAIN_COLORS[chain] || PUBLICATION_PALETTE[index % PUBLICATION_PALETTE.length];
  }

  function chainLabel(chain) {
    return `Chain ${chain}`;
  }

  function pdbIdFromLabelOrPath(label, path) {
    const combined = `${label || ""} ${fileNameFromPath(path || "")}`;
    const match = combined.match(/\b([0-9][A-Za-z0-9]{3})\b/);
    return match ? match[1].toUpperCase() : "";
  }

  function addStructureArtifact(artifacts, seen, path, label = "") {
    const cleanPath = String(path || "").trim();
    if (!cleanPath || !isStructurePath(cleanPath) || seen.has(cleanPath)) return;
    seen.add(cleanPath);
    artifacts.push({
      path: cleanPath,
      label: label || fileNameFromPath(cleanPath),
      pdbId: pdbIdFromLabelOrPath(label, cleanPath),
      format: structureFormat(cleanPath),
    });
  }

  function collectStructureArtifacts(result) {
    const artifacts = [];
    const seen = new Set();
    for (const item of result?.files || []) {
      if (item?.kind === "structure") {
        addStructureArtifact(artifacts, seen, item?.path, item?.label || "structure");
      }
    }
    if (artifacts.length) return artifacts;

    const evidence = result?.evidence || {};
    for (const item of evidence.outputs || []) {
      if (item?.tool === "structure_inspect" || item?.tool === "pdb_download" || item?.tool === "alphafold_download") {
        addStructureArtifact(artifacts, seen, item?.structure_path, item?.pdb_id || item?.summary);
      }
    }
    for (const item of evidence.tool_outputs || []) {
      if (item?.tool === "structure_inspect" || item?.tool === "pdb_download" || item?.tool === "alphafold_download") {
        addStructureArtifact(artifacts, seen, item?.structure_path, item?.pdb_id || item?.summary);
      }
    }
    return artifacts;
  }

  function addFigureArtifact(artifacts, seen, path, label = "") {
    const cleanPath = String(path || "").trim();
    if (!cleanPath || !isImagePath(cleanPath) || seen.has(cleanPath)) return;
    seen.add(cleanPath);
    artifacts.push({ path: cleanPath, label: label || fileNameFromPath(cleanPath) });
  }

  function collectFigureArtifacts(result) {
    const artifacts = [];
    const seen = new Set();
    for (const item of result?.files || []) {
      if (item?.kind === "image") {
        addFigureArtifact(artifacts, seen, item?.path, item?.label || item?.source_skill);
      }
    }
    if (artifacts.length) return artifacts;

    const evidence = result?.evidence || {};
    for (const item of evidence.outputs || []) {
      addFigureArtifact(artifacts, seen, item?.image_path, item?.label || item?.summary || item?.tool);
    }
    for (const item of evidence.tool_outputs || []) {
      addFigureArtifact(artifacts, seen, item?.image_path, item?.label || item?.summary || item?.tool);
    }
    return artifacts;
  }

  function collectPipelineOutputRecords(result) {
    const records = [];
    const seen = new Set();
    const evidence = result?.evidence || {};
    const candidates = [
      ...(Array.isArray(evidence.outputs) ? evidence.outputs : []),
      ...(Array.isArray(evidence.tool_outputs) ? evidence.tool_outputs : []),
    ];

    for (const candidate of candidates) {
      const isPipeline = candidate?.tool === "pipeline_shell";
      if (!isPipeline || !Array.isArray(candidate.output_records)) continue;
      for (const record of candidate.output_records) {
        const path = String(record?.path || "").trim();
        if (!path || record?.exists === false || seen.has(path)) continue;
        seen.add(path);
        records.push({
          path,
          label: String(record?.label || record?.name || fileNameFromPath(path)),
          kind: String(record?.kind || "file"),
        });
      }
    }

    if (records.length) return records;
    const excludedKinds = new Set(["config", "directory", "input", "upload"]);
    for (const artifact of result?.files || []) {
      const path = String(artifact?.path || "").trim();
      if (
        artifact?.source_skill !== "pipeline_shell" ||
        !path ||
        excludedKinds.has(String(artifact?.kind || "")) ||
        seen.has(path)
      ) continue;
      seen.add(path);
      records.push({
        path,
        label: String(artifact?.label || fileNameFromPath(path)),
        kind: String(artifact?.kind || "file"),
      });
    }
    return records;
  }

  function pipelineNameFromResult(result) {
    const outputs = result?.evidence?.outputs;
    if (Array.isArray(outputs)) {
      for (let index = outputs.length - 1; index >= 0; index -= 1) {
        if (outputs[index]?.tool === "pipeline_shell" && outputs[index]?.pipeline_name) {
          return String(outputs[index].pipeline_name);
        }
      }
    }
    return "pipeline";
  }

  function pipelineDownloadsHtml(result, records = collectPipelineOutputRecords(result)) {
    if (!records.length) return "";
    const pipelineName = pipelineNameFromResult(result);
    const links = records.map((record) => {
      const filename = fileNameFromPath(record.path);
      const url = workspaceFileUrl(record.path);
      return `
        <a class="pipeline-download" href="${escapeHtml(url)}" download="${escapeHtml(filename)}"
          title="${escapeHtml(record.path)}">
          <span>${escapeHtml(record.label)}</span>
          <small>${escapeHtml(filename)} · ${escapeHtml(record.kind)}</small>
        </a>
      `;
    }).join("");
    return `
      <section class="pipeline-downloads" aria-label="Pipeline result downloads">
        <div class="pipeline-downloads-heading">
          <strong>Result downloads</strong>
          <span>${records.length} files</span>
        </div>
        <div class="pipeline-download-grid">${links}</div>
        <p class="pipeline-download-note">
          Result contents are not previewed automatically.
          To review them here, ask: <q>Collect and show all results from the ${escapeHtml(pipelineName)} pipeline run.</q>
        </p>
      </section>
    `;
  }

  function collectedBundleHtml(result) {
    const bundles = (result?.files || []).filter((artifact) => (
      artifact?.source_skill === "pipeline_shell" &&
      artifact?.kind === "compressed" &&
      String(artifact?.path || "").toLowerCase().endsWith(".zip")
    ));
    if (!bundles.length) return "";
    return bundles.map((artifact) => {
      const filename = fileNameFromPath(artifact.path);
      return `
        <section class="pipeline-downloads" aria-label="Collected result bundle">
          <div class="pipeline-downloads-heading"><strong>Collected result bundle</strong></div>
          <div class="pipeline-download-grid">
            <a class="pipeline-download" href="${escapeHtml(workspaceFileUrl(artifact.path))}"
              download="${escapeHtml(filename)}">
              <span>Download all collected results</span>
              <small>${escapeHtml(filename)} · ZIP archive</small>
            </a>
          </div>
        </section>
      `;
    }).join("");
  }

  function figureArtifactsHtml(result) {
    const artifacts = collectFigureArtifacts(result);
    if (!artifacts.length) return "";
    return artifacts.map((artifact) => {
      const title = artifact.label && artifact.label !== artifact.path
        ? artifact.label
        : fileNameFromPath(artifact.path);
      const url = workspaceFileUrl(artifact.path);
      return `
        <figure class="artifact-figure">
          <div class="artifact-figure-frame">
            <img src="${escapeHtml(url)}" alt="${escapeHtml(title)}" loading="lazy">
          </div>
          <figcaption>
            <span>${escapeHtml(title)}</span>
            <a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">Open figure</a>
          </figcaption>
        </figure>
      `;
    }).join("");
  }

  function structureViewerHtml(result) {
    const artifacts = collectStructureArtifacts(result);
    if (!artifacts.length) return "";
    return artifacts.map((artifact) => {
      const title = artifact.label && artifact.label !== artifact.path
        ? `${artifact.label} · ${fileNameFromPath(artifact.path)}`
        : fileNameFromPath(artifact.path);
      return `
        <details class="structure-viewer-details">
          <summary>3D structure: ${escapeHtml(title)} <span>Open viewer</span></summary>
          <div class="structure-viewer"
            data-structure-path="${escapeHtml(artifact.path)}"
            data-pdb-id="${escapeHtml(artifact.pdbId)}"
            data-structure-format="${escapeHtml(artifact.format)}">
            <div class="structure-toolbar" aria-label="Structure display controls">
              <button type="button" data-style="publication" class="active">Publication</button>
              <button type="button" data-style="cartoon">Cartoon</button>
              <button type="button" data-style="stick">Stick</button>
              <button type="button" data-style="sphere">Sphere</button>
              <button type="button" data-style="line">Line</button>
            </div>
            <div class="structure-visual">
              <div class="structure-canvas" role="img" aria-label="Interactive molecular structure viewer">
                <div class="structure-loading">Loading 3D viewer...</div>
              </div>
              <div class="structure-overlay-title" aria-hidden="true">
                <strong>${escapeHtml(artifact.pdbId ? `PDB ${artifact.pdbId}` : "Protein structure")}</strong>
                <span>${escapeHtml(`${artifact.format.toUpperCase()} · interactive molecular view`)}</span>
              </div>
              <div class="structure-legend" aria-label="Chain color legend" hidden></div>
              <div class="structure-note" aria-hidden="true">Drag to rotate · scroll to zoom</div>
            </div>
            <div class="structure-path">${escapeHtml(artifact.path)}</div>
          </div>
        </details>
      `;
    }).join("");
  }

  function browserSupportsWebGL() {
    try {
      const canvas = document.createElement("canvas");
      return Boolean(canvas.getContext("webgl2") || canvas.getContext("webgl") || canvas.getContext("experimental-webgl"));
    } catch (_) {
      return false;
    }
  }

  function ensureViewerContainerReady(container) {
    const rect = container.getBoundingClientRect();
    if (rect.width < 20 || rect.height < 20) {
      throw new Error(`3D viewer container is not ready yet (${Math.round(rect.width)}x${Math.round(rect.height)}).`);
    }
  }

  function errorMessage(error) {
    if (!error) return "unknown error";
    return error.message || String(error);
  }

  function structureLoadErrorHtml(path, error, fallbackError = null) {
    const localMessage = errorMessage(error);
    const fallbackMessage = fallbackError ? `<br>Fallback: ${escapeHtml(errorMessage(fallbackError))}` : "";
    return `
      <div class="structure-error">
        <div>
          Failed to load structure.<br>
          Local file: ${escapeHtml(path)}<br>
          Error: ${escapeHtml(localMessage)}
          ${fallbackMessage}
        </div>
      </div>
    `;
  }

  function activeStructureStyle(details) {
    return details.querySelector("[data-style].active")?.dataset?.style || "publication";
  }

  function updateChainLegend(details, chainIds) {
    const legend = details.querySelector(".structure-legend");
    if (!legend) return;
    if (!chainIds.length) {
      legend.hidden = true;
      legend.replaceChildren();
      return;
    }
    const visibleChainIds = chainIds.slice(0, 8);
    legend.innerHTML = visibleChainIds.map((chain, index) => `
      <div class="structure-legend-row">
        <span class="structure-swatch" style="background:${escapeHtml(chainColor(chain, index))}"></span>
        <span>${escapeHtml(chainLabel(chain))}</span>
      </div>
    `).join("") + (chainIds.length > visibleChainIds.length
      ? `<div class="structure-legend-more">+${chainIds.length - visibleChainIds.length} more chains</div>`
      : "");
    legend.hidden = false;
  }

  function frameStructureViewer(details) {
    const viewer = details._agentViewer;
    if (!viewer) return;
    const chainIds = details._chainIds || [];
    viewer.zoomTo(chainIds.length ? { chain: chainIds } : {});
    viewer.zoom(1.08);
    if (!details.dataset.oriented) {
      if (typeof viewer.rotate === "function") {
        viewer.rotate(12, "x");
        viewer.rotate(-8, "y");
        viewer.rotate(5, "z");
      }
      details.dataset.oriented = "true";
    }
    viewer.render();
    if (typeof viewer.resize === "function") {
      setTimeout(() => { viewer.resize(); viewer.render(); }, 0);
    }
  }

  function applyStructureStyle(details, style) {
    const viewer = details._agentViewer;
    details.querySelectorAll("[data-style]").forEach((button) => {
      button.classList.toggle("active", button.dataset.style === style);
    });
    if (!viewer) {
      if (details.open) loadStructureViewer(details);
      return;
    }
    viewer.setStyle({}, {});
    if (style === "publication") {
      const chainIds = details._chainIds || [];
      if (chainIds.length) {
        chainIds.forEach((chain, index) => {
          viewer.setStyle({ chain }, { cartoon: { color: chainColor(chain, index), opacity: 0.98 } });
        });
      } else {
        viewer.setStyle({ hetflag: false }, { cartoon: { color: "spectrum", opacity: 0.98 } });
      }
      viewer.setStyle({ hetflag: true }, { stick: { radius: 0.14, colorscheme: "whiteCarbon", opacity: 0.55 } });
      viewer.setStyle({ resn: "HOH" }, {});
    } else if (style === "stick") {
      viewer.setStyle({}, { stick: { radius: 0.16, colorscheme: "Jmol" } });
    } else if (style === "sphere") {
      viewer.setStyle({}, { sphere: { scale: 0.28, colorscheme: "Jmol" } });
    } else if (style === "line") {
      viewer.setStyle({}, { line: { colorscheme: "Jmol" } });
    } else {
      viewer.setStyle({ hetflag: false }, { cartoon: { color: "spectrum" } });
      viewer.setStyle({ hetflag: true }, { stick: { radius: 0.22, colorscheme: "greenCarbon" } });
      viewer.setStyle({ resn: "HOH" }, {});
    }
    frameStructureViewer(details);
  }

  function finalizeStructureViewer(details, viewer, model) {
    details._agentViewer = viewer;
    details._structureModel = model;
    details._chainIds = chainIdsFromModel(model);
    updateChainLegend(details, details._chainIds);
    if (typeof viewer.setProjection === "function") viewer.setProjection("orthographic");
    details.dataset.loaded = "true";
    applyStructureStyle(details, activeStructureStyle(details));
  }

  function renderStructureText(details, container, structureText, format) {
    ensureViewerContainerReady(container);
    const viewer = window.$3Dmol.createViewer(container, { backgroundColor: "white", antialias: true, fog: false });
    const model = viewer.addModel(structureText, format);
    if (!model) throw new Error(`3Dmol could not parse ${format} structure text.`);
    finalizeStructureViewer(details, viewer, model);
  }

  function renderStructureFromPdbId(details, container, pdbId) {
    return new Promise((resolve, reject) => {
      container.innerHTML = "";
      let viewer;
      try {
        ensureViewerContainerReady(container);
        viewer = window.$3Dmol.createViewer(container, { backgroundColor: "white", antialias: true, fog: false });
      } catch (error) {
        reject(error);
        return;
      }
      let settled = false;
      const timeout = window.setTimeout(() => {
        if (!settled) { settled = true; reject(new Error(`PDB fallback timed out for ${pdbId}.`)); }
      }, 15000);
      try {
        window.$3Dmol.download(`pdb:${pdbId}`, viewer, { format: "pdb" }, (model) => {
          if (settled) return;
          window.clearTimeout(timeout);
          if (!model) { settled = true; reject(new Error(`3Dmol PDB fallback returned no model for ${pdbId}.`)); return; }
          finalizeStructureViewer(details, viewer, model);
          settled = true;
          resolve();
        });
      } catch (error) {
        window.clearTimeout(timeout);
        settled = true;
        reject(error);
      }
    });
  }

  async function loadStructureViewer(details) {
    if (details.dataset.loaded === "true" || details.dataset.loading === "true") return;
    const container = details.querySelector(".structure-canvas");
    const viewerElement = details.querySelector(".structure-viewer");
    if (!container || !viewerElement) return;
    if (!window.$3Dmol) {
      container.innerHTML = `<div class="structure-error">3Dmol.js did not load. Check network access to the CDN.</div>`;
      return;
    }
    if (!browserSupportsWebGL()) {
      container.innerHTML = `<div class="structure-error"><div>WebGL is not available in this browser context, so the 3D viewer cannot start.<br>Try Chrome/Firefox with hardware acceleration enabled, or use the local structure file in PyMOL/ChimeraX.</div></div>`;
      return;
    }

    details.dataset.loading = "true";
    const path = viewerElement.dataset.structurePath || "";
    const pdbId = viewerElement.dataset.pdbId || "";
    try {
      container.innerHTML = "";
      const response = await fetch(workspaceFileUrl(path, { viewer: "pdb" }));
      if (!response.ok) {
        const text = await response.text();
        throw new Error(`Local artifact request failed: HTTP ${response.status} ${text.slice(0, 160)}`);
      }
      renderStructureText(details, container, await response.text(), viewerElement.dataset.structureFormat || "pdb");
    } catch (error) {
      if (pdbId) {
        try {
          await renderStructureFromPdbId(details, container, pdbId);
          return;
        } catch (fallbackError) {
          container.innerHTML = structureLoadErrorHtml(path, error, fallbackError);
        }
      } else {
        container.innerHTML = structureLoadErrorHtml(path, error);
      }
    } finally {
      details.dataset.loading = "false";
    }
  }

  function initializeStructureViewers(root = document) {
    root.querySelectorAll(".structure-viewer-details").forEach((details) => {
      if (details.dataset.bound === "true") return;
      details.dataset.bound = "true";
      details.addEventListener("toggle", () => { if (details.open) loadStructureViewer(details); });
      details.querySelectorAll("[data-style]").forEach((button) => {
        button.addEventListener("click", () => applyStructureStyle(details, button.dataset.style || "cartoon"));
      });
    });
  }

  return {
    ...createGenomeViewers({ workspaceFileUrl }),
    collectStructureArtifacts,
    collectFigureArtifacts,
    collectPipelineOutputRecords,
    pipelineDownloadsHtml,
    collectedBundleHtml,
    figureArtifactsHtml,
    structureViewerHtml,
    initializeStructureViewers,
  };
}
