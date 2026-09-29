import { useId } from 'react';

/**
 * Shared visual language for the product.  This is the same blue robot mark
 * used by the original vanilla app and the embed launcher.  Keeping it in one
 * component prevents the shell, assistant and website demo from drifting into
 * different logos as each feature evolves.
 */
export function AgentIcon({ size = 40, className = '', title }: { size?: number; className?: string; title?: string }) {
  const rawId = useId();
  const gradientId = `agent-screen-${rawId.replace(/[^a-zA-Z0-9_-]/g, '')}`;
  return (
    <svg
      className={`agent-icon ${className}`.trim()}
      width={size}
      height={size}
      viewBox="0 0 512 512"
      fill="none"
      role={title ? 'img' : undefined}
      aria-label={title}
      aria-hidden={title ? undefined : true}
    >
      {title ? <title>{title}</title> : null}
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#159BEA" />
          <stop offset="1" stopColor="#1486D8" />
        </linearGradient>
      </defs>
      <path d="M256 112c-4-38 10-58 34-67" stroke="#25283A" strokeWidth="10" strokeLinecap="round" />
      <circle cx="300" cy="40" r="18" fill="#159BEA" stroke="#25283A" strokeWidth="8" />
      <rect x="79" y="164" width="35" height="118" rx="17" fill="#D3D2D1" stroke="#25283A" strokeWidth="9" />
      <rect x="398" y="164" width="35" height="118" rx="17" fill="#D3D2D1" stroke="#25283A" strokeWidth="9" />
      <rect x="101" y="126" width="310" height="213" rx="48" fill={`url(#${gradientId})`} stroke="#25283A" strokeWidth="10" />
      <path d="M128 162c23-19 52-27 87-27h94c34 0 62 8 77 25" stroke="#63C6F3" strokeWidth="9" strokeLinecap="round" opacity=".7" />
      <rect x="181" y="204" width="13" height="52" rx="6.5" fill="#202332" />
      <rect x="318" y="204" width="13" height="52" rx="6.5" fill="#202332" />
      <ellipse cx="166" cy="275" rx="23" ry="12" fill="#F58FAE" />
      <ellipse cx="346" cy="275" rx="23" ry="12" fill="#F58FAE" />
      <path d="M241 275c7 9 23 9 30 0" stroke="#63D2F5" strokeWidth="8" strokeLinecap="round" />
      <path d="M104 319c-23 17-28 44-14 61 9 11 23 11 30 1l20-31" fill="#D3D2D1" stroke="#25283A" strokeWidth="9" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M408 319c23 17 28 44 14 61-9 11-23 11-30 1l-20-31" fill="#D3D2D1" stroke="#25283A" strokeWidth="9" strokeLinecap="round" strokeLinejoin="round" />
      <rect x="171" y="331" width="170" height="105" rx="25" fill="#F1F0ED" stroke="#25283A" strokeWidth="9" />
      <rect x="224" y="352" width="64" height="53" rx="8" fill="#168EDC" stroke="#25283A" strokeWidth="7" />
      <rect x="244" y="368" width="24" height="18" rx="3" fill="#82D8F5" />
      <path d="M190 433v39c0 9 7 16 16 16h31v-55" fill="#C9C8C6" stroke="#25283A" strokeWidth="9" strokeLinejoin="round" />
      <path d="M322 433v39c0 9-7 16-16 16h-31v-55" fill="#C9C8C6" stroke="#25283A" strokeWidth="9" strokeLinejoin="round" />
    </svg>
  );
}

export function LineIcon({ name, size = 18, className = '' }: { name: 'plus' | 'chevron' | 'more' | 'pin' | 'edit' | 'trash' | 'clip' | 'arrow' | 'refresh' | 'close'; size?: number; className?: string }) {
  const paths = {
    plus: 'M12 5v14M5 12h14',
    chevron: 'm9 18 6-6-6-6',
    more: 'M5 12h.01M12 12h.01M19 12h.01',
    pin: 'M12 17v5M7 5h10l-1 6 3 3H5l3-3-1-6z',
    edit: 'm4 16.5-.8 4.3 4.3-.8L19 8.5 15.5 5 4 16.5ZM13.8 6.7l3.5 3.5',
    trash: 'M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3',
    clip: 'm20.5 11.5-7.9 7.9a5 5 0 0 1-7.1-7.1l8.6-8.6a3.5 3.5 0 1 1 5 5l-8.6 8.6a2 2 0 1 1-2.8-2.8l7.9-7.9',
    arrow: 'M5 12h14M13 6l6 6-6 6',
    refresh: 'M21 12a9 9 0 1 1-2.64-6.36M21 3v6h-6',
    close: 'M6 6l12 12M18 6 6 18',
  } as const;
  return <svg className={className} width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d={paths[name]} stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" /></svg>;
}
