import type { ElementType, ReactNode } from 'react';

const safeUrl = (value: string): string => {
  const url = value.trim();
  if (!url || url.startsWith('//') || url.startsWith('\\') || /^(?:javascript|data|vbscript):/i.test(url)) return '';
  if (/^(?:https?:|mailto:)/i.test(url) || url.startsWith('#') || url.startsWith('/')) return url;
  return '';
};

function inline(text: string): ReactNode[] {
  const output: ReactNode[] = [];
  // Underscores inside tool names, paths, and scientific identifiers are literal.
  const pattern = /!\[([^\]]*)\]\(([^)\s]+)(?:\s+["']([^"']*)["'])?\)|\[([^\]]+)\]\(([^)\s]+)(?:\s+["']([^"']*)["'])?\)|(`+)([\s\S]*?)\7|\*\*([\s\S]*?)\*\*|(?<![\p{L}\p{N}_])__([\s\S]*?)__(?![\p{L}\p{N}_])|~~([\s\S]*?)~~|(?<![\p{L}\p{N}_])_([^_\n]+)_(?![\p{L}\p{N}_])|\*([^*\n]+)\*/gu;
  let cursor = 0; let match: RegExpExecArray | null; let index = 0;
  while ((match = pattern.exec(text))) {
    if (match.index > cursor) output.push(text.slice(cursor, match.index));
    if (match[1] !== undefined) {
      const url = safeUrl(match[2]);
      output.push(url ? <img key={index++} src={url} alt={match[1]} title={match[3]} loading="lazy" /> : match[0]);
    } else if (match[4] !== undefined) {
      const url = safeUrl(match[5]);
      output.push(url ? <a key={index++} href={url} title={match[6]} target={/^https?:/i.test(url) ? '_blank' : undefined} rel={/^https?:/i.test(url) ? 'noopener noreferrer' : undefined}>{match[4]}</a> : match[0]);
    } else if (match[8] !== undefined) output.push(<code key={index++}>{match[8]}</code>);
    else if (match[9] !== undefined || match[10] !== undefined) output.push(<strong key={index++}>{match[9] ?? match[10]}</strong>);
    else if (match[11] !== undefined) output.push(<del key={index++}>{match[11]}</del>);
    else if (match[12] !== undefined) output.push(<em key={index++}>{match[12]}</em>);
    else if (match[13] !== undefined) output.push(<em key={index++}>{match[13]}</em>);
    cursor = match.index + match[0].length;
  }
  if (cursor < text.length) output.push(text.slice(cursor));
  return output;
}

function mathContent(value: string): ReactNode {
  // Keep formulas readable without injecting HTML. Escaping here is provided by React text nodes.
  return <span className="math-content">{value.replace(/\\([{}])/g, '$1')}</span>;
}

function tableCells(line: string): string[] {
  let value = line.trim();
  if (value.startsWith('|')) value = value.slice(1);
  if (value.endsWith('|') && !value.endsWith('\\|')) value = value.slice(0, -1);
  const cells: string[] = []; let current = ''; let escaped = false;
  for (const char of value) {
    if (char === '|' && !escaped) { cells.push(current.trim()); current = ''; continue; }
    if (char === '\\' && !escaped) { escaped = true; current += char; continue; }
    escaped = false; current += char;
  }
  cells.push(current.trim()); return cells;
}
function tableSeparator(cells: string[]): boolean { return cells.length > 1 && cells.every(cell => /^:?-{3,}:?$/.test(cell)); }

function Table({ header, separator, rows, keyBase }: { header: string[]; separator: string[]; rows: string[][]; keyBase: string }) {
  return <div className="markdown-table-wrap"><table><thead><tr>{header.map((cell, i) => {
    const align = separator[i]?.startsWith(':') && separator[i]?.endsWith(':') ? 'center' : separator[i]?.endsWith(':') ? 'right' : 'left';
    return <th key={`${keyBase}h${i}`} style={{ textAlign: align }}>{inline(cell)}</th>;
  })}</tr></thead><tbody>{rows.map((row, r) => <tr key={`${keyBase}r${r}`}>{header.map((_, i) => {
    const align = separator[i]?.startsWith(':') && separator[i]?.endsWith(':') ? 'center' : separator[i]?.endsWith(':') ? 'right' : 'left';
    return <td key={`${keyBase}c${i}`} style={{ textAlign: align }}>{inline(row[i] ?? '')}</td>;
  })}</tr>)}</tbody></table></div>;
}

export function renderMarkdown(text: string): ReactNode {
  const lines = String(text ?? '').replace(/\r\n/g, '\n').split('\n');
  const nodes: ReactNode[] = []; let paragraph: string[] = []; let list: { type: 'ul' | 'ol'; items: string[] } | null = null;
  const flush = () => { if (paragraph.length) { nodes.push(<p key={`p${nodes.length}`}>{paragraph.map((line, i) => <span key={i}>{i > 0 && <br />}{inline(line)}</span>)}</p>); paragraph = []; } };
  const closeList = () => { if (!list) return; const Tag = list.type; nodes.push(<Tag key={`l${nodes.length}`}>{list.items.map((item, i) => <li key={i}>{inline(item)}</li>)}</Tag>); list = null; };
  for (let i = 0; i < lines.length; i += 1) {
    const raw = lines[i].replace(/\s+$/, ''); const line = raw.trim();
    const fence = raw.match(/^\s*```([\w-]*)\s*$/);
    if (fence) {
      flush(); closeList(); const body: string[] = []; i += 1;
      while (i < lines.length && !/^\s*```\s*$/.test(lines[i])) { body.push(lines[i]); i += 1; }
      nodes.push(<pre key={`code${nodes.length}`}><code className={fence[1] ? `language-${fence[1]}` : undefined}>{body.join('\n')}</code></pre>); continue;
    }
    if (!line) { flush(); closeList(); continue; }
    if ((line.startsWith('$$') && line.endsWith('$$') && line.length > 4) || (line.startsWith('\\(') && line.endsWith('\\)'))) { flush(); closeList(); nodes.push(<div className="math-block" key={`m${nodes.length}`}>{mathContent(line.replace(/^\$\$|\$\$$|^\\\(|\\\)$/g, '') )}</div>); continue; }
    if (line.startsWith('$$') || line.startsWith('\\[')) {
      const close = line.startsWith('$$') ? '$$' : '\\]'; const body = [line.slice(2)]; i += 1;
      while (i < lines.length && !lines[i].trim().endsWith(close)) { body.push(lines[i]); i += 1; }
      body.push((lines[i] || '').replace(new RegExp(`.*${close}`), '')); flush(); closeList(); nodes.push(<div className="math-block" key={`m${nodes.length}`}>{mathContent(body.join('\n'))}</div>); continue;
    }
    const tableNext = lines[i + 1] || '';
    if (line.includes('|') && tableSeparator(tableCells(tableNext))) {
      flush(); closeList(); const header = tableCells(line); const separator = tableCells(tableNext); const rows: string[][] = []; i += 2;
      while (i < lines.length && lines[i].trim() && lines[i].includes('|')) { rows.push(tableCells(lines[i])); i += 1; }
      i -= 1; nodes.push(<Table key={`t${nodes.length}`} header={header} separator={separator} rows={rows} keyBase={`t${nodes.length}`} />); continue;
    }
    const heading = raw.match(/^(#{1,6})\s+(.+)$/);
    if (heading) { flush(); closeList(); const level = Math.min(6, heading[1].length); const Tag = `h${level}` as ElementType; nodes.push(<Tag key={`h${nodes.length}`}>{inline(heading[2])}</Tag>); continue; }
    const quote = raw.match(/^>\s?(.*)$/); if (quote) { flush(); closeList(); nodes.push(<blockquote key={`q${nodes.length}`}>{inline(quote[1])}</blockquote>); continue; }
    const ordered = raw.match(/^\s*\d+[.)]\s+(.+)$/); const unordered = raw.match(/^\s*[-*+]\s+(.+)$/);
    if (ordered || unordered) { flush(); const type = ordered ? 'ol' : 'ul'; if (!list || list.type !== type) { closeList(); list = { type, items: [] }; } list.items.push((ordered || unordered)![1]); continue; }
    paragraph.push(line);
  }
  flush(); closeList(); return <>{nodes}</>;
}

export default renderMarkdown;
