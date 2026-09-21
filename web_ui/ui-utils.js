export function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

export function fileNameFromPath(path) {
  const clean = String(path || "").split(/[?#]/)[0];
  return clean.split(/[\\/]/).filter(Boolean).pop() || clean || "structure";
}

export function formatBytes(value) {
  const bytes = Number(value || 0);
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}

export function formatElapsed(seconds) {
  const value = Number(seconds || 0);
  if (value < 60) return `${value.toFixed(value < 10 ? 1 : 0)}s`;
  const minutes = Math.floor(value / 60);
  const remainder = Math.round(value % 60);
  return `${minutes}m ${remainder}s`;
}

export function compactList(values, emptyText = "none", limit = 3) {
  const items = (values || []).filter(Boolean).map(String);
  if (!items.length) return emptyText;
  const shown = items.slice(0, limit).join(", ");
  return items.length > limit ? `${shown} +${items.length - limit}` : shown;
}

export function nowIso() {
  return new Date().toISOString();
}

export function generateSessionId(prefix = "chat") {
  if (window.crypto && typeof window.crypto.randomUUID === "function") {
    return `${prefix}_${window.crypto.randomUUID()}`;
  }
  return `${prefix}_${Date.now()}_${Math.random().toString(16).slice(2)}`;
}

export function titleFromText(text) {
  const title = String(text || "").replace(/\s+/g, " ").trim();
  return title ? title.slice(0, 64) : "New chat";
}
