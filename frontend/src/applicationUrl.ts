/** Resolve the mounted application base, including deployments behind a path prefix. */
export function applicationBaseUrl(): string {
  const configured = new URL(import.meta.env.BASE_URL, window.location.origin);
  const entry = window.location.pathname.match(/^(.*)\/(?:index\.html|assistant(?:-demo)?(?:\.html)?)$/);
  const inferredPath = entry ? `${entry[1] || ''}/` : window.location.pathname.endsWith('/')
    ? window.location.pathname
    : configured.pathname;
  const inferred = new URL(inferredPath, window.location.origin);
  return configured.pathname === '/' && inferred.pathname !== '/' ? inferred.toString() : configured.toString();
}

/** Resolve application-owned URLs below the mounted deployment base. */
export function applicationUrl(path: string): string {
  const base = new URL(applicationBaseUrl());
  return new URL(path.replace(/^\//, ''), base).toString();
}
