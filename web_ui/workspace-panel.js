import {
  escapeHtml,
  fileNameFromPath,
  formatBytes,
} from "/static/ui-utils.js";

/** Own the session workspace inventory, rendering, upload, and removal flows. */
export function createWorkspacePanel({
  elements,
  api,
  getSessionId,
  isBusy = () => false,
  onError = () => {},
} = {}) {
  const {
    count,
    summary,
    list,
    search,
    filter,
    uploadButton,
    uploadInput,
    composerFileHint,
  } = elements;
  let files = [];

  function category(file) {
    const path = String(file?.workspace_path || file?.path || "");
    return path.startsWith("uploads/")
      ? { key: "uploads", label: "Inputs" }
      : { key: "outputs", label: "Outputs" };
  }

  function fileUrl(path, options = {}) {
    const file = files.find((item) => item.path === path || item.workspace_path === path);
    const params = new URLSearchParams({ path: String(file?.workspace_path || path || "") });
    const sessionId = getSessionId();
    if (sessionId) params.set("session_id", sessionId);
    if (options.viewer) params.set("viewer", options.viewer);
    return `/workspace/file?${params.toString()}`;
  }

  function render() {
    count.textContent = String(files.length);
    if (composerFileHint) {
      composerFileHint.textContent = files.length
        ? `${files.length} file${files.length === 1 ? "" : "s"} attached`
        : "Add files";
    }
    list.classList.toggle("single-file", files.length === 1);
    list.replaceChildren();
    if (!files.length) {
      summary.textContent = "Files are shared with this chat and its tools.";
      list.innerHTML = `<div class="workspace-empty">No files in this workspace yet.</div>`;
      return;
    }
    const totalBytes = files.reduce((sum, file) => sum + Number(file.size || 0), 0);
    summary.textContent = `${formatBytes(totalBytes)} · available to this chat and its tools`;
    const query = search.value.trim().toLowerCase();
    const selectedFilter = filter.value;
    const visibleFiles = files.filter((file) => {
      const path = String(file.workspace_path || file.path || "");
      if (query && !path.toLowerCase().includes(query)) return false;
      const kind = category(file).key;
      if (selectedFilter === "uploads") return kind === "uploads";
      if (selectedFilter === "outputs") return kind === "outputs";
      return true;
    });
    if (!visibleFiles.length) {
      list.innerHTML = `<div class="workspace-empty">No matching files.</div>`;
      return;
    }
    const groups = new Map();
    for (const file of visibleFiles) {
      const kind = category(file);
      if (!groups.has(kind.key)) groups.set(kind.key, { ...kind, files: [] });
      groups.get(kind.key).files.push(file);
    }
    for (const group of ["uploads", "outputs"].map((key) => groups.get(key)).filter(Boolean)) {
      const section = document.createElement("section");
      section.className = "workspace-group";
      const heading = document.createElement("div");
      heading.className = "workspace-group-heading";
      heading.innerHTML = `<span>${escapeHtml(group.label)}</span><span>${group.files.length}</span>`;
      const contents = document.createElement("div");
      contents.className = "workspace-group-files";
      for (const file of group.files) {
        const item = document.createElement("div");
        item.className = "workspace-file";
        const workspacePath = file.workspace_path || file.path || "";
        item.dataset.workspacePath = workspacePath;
        const name = file.name || fileNameFromPath(workspacePath);
        item.innerHTML = `
          <div class="workspace-file-main">
            <div class="workspace-file-name" title="${escapeHtml(name)}">${escapeHtml(name)}</div>
            <div class="workspace-file-meta">${escapeHtml(formatBytes(file.size))} · <span class="workspace-file-kind">${escapeHtml(file.kind || "file")}</span></div>
            <div class="workspace-file-path" title="${escapeHtml(workspacePath)}">${escapeHtml(workspacePath)}</div>
          </div>
          <div class="workspace-file-actions">
            <a class="workspace-download" href="${escapeHtml(fileUrl(workspacePath))}" download>Download</a>
            <button class="workspace-remove" type="button" data-workspace-delete aria-label="Remove ${escapeHtml(name)}">Remove</button>
          </div>
        `;
        contents.appendChild(item);
      }
      section.append(heading, contents);
      list.appendChild(section);
    }
  }

  function setFiles(value) {
    files = Array.isArray(value) ? [...value] : [];
    files.sort((left, right) => String(left.workspace_path || left.path || "")
      .localeCompare(String(right.workspace_path || right.path || "")));
    render();
  }

  async function load() {
    const sessionId = getSessionId();
    if (!sessionId) {
      setFiles([]);
      return files;
    }
    const payload = await api.loadWorkspace(sessionId);
    if (sessionId !== getSessionId()) return files;
    setFiles(payload.workspace?.files);
    return files;
  }

  async function uploadSelectedFiles(selectedFiles) {
    const selected = Array.from(selectedFiles || []);
    if (!selected.length || isBusy()) return;
    const sessionId = getSessionId();
    uploadButton.disabled = true;
    uploadButton.textContent = "Uploading";
    try {
      await api.uploadFiles(sessionId, selected);
      if (sessionId === getSessionId()) await load();
    } catch (error) {
      if (sessionId === getSessionId()) onError(`Upload failed: ${error.message}`);
    } finally {
      uploadInput.value = "";
      uploadButton.disabled = isBusy();
      uploadButton.textContent = "Upload";
    }
  }

  async function deleteFile(workspacePath) {
    if (!workspacePath || isBusy()) return;
    const payload = await api.deleteWorkspaceFile(getSessionId(), workspacePath);
    if (!payload.deleted) throw new Error(payload.error || "File was not deleted.");
    await load();
  }

  return {
    fileUrl,
    getFiles: () => files,
    setFiles,
    render,
    load,
    uploadSelectedFiles,
    deleteFile,
  };
}
