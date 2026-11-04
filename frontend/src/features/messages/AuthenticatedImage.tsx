import { useEffect, useState, type ImgHTMLAttributes } from 'react';

/** Native img requests cannot attach an embedded session's in-memory credential. */
export function AuthenticatedImage({ src = '', ...props }: ImgHTMLAttributes<HTMLImageElement>) {
  const [loaded, setLoaded] = useState('');
  const [failed, setFailed] = useState(false);
  let owned = false;
  try { const local = new URL(src || '#', window.location.href); owned = local.origin === window.location.origin && local.pathname === '/workspace/file'; }
  catch { /* Invalid URLs render as unavailable images, never break the chat. */ }
  useEffect(() => {
    if (!owned) return;
    const controller = new AbortController(); let objectUrl = '';
    setLoaded(''); setFailed(false);
    void fetch(src, { signal: controller.signal }).then(async response => {
      if (!response.ok) throw new Error('Image unavailable');
      const blob = await response.blob();
      if (controller.signal.aborted) return;
      objectUrl = URL.createObjectURL(blob); setLoaded(objectUrl);
    }).catch(() => { if (!controller.signal.aborted) setFailed(true); });
    return () => { controller.abort(); if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [src, owned]);
  if (owned && !loaded) return <span>{failed ? 'Image preview unavailable' : 'Loading image…'}</span>;
  return <img {...props} src={owned ? loaded : src} />;
}
