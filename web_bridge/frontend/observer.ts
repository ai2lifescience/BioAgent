/** Observe the actual host tab; no page-specific registration or DOM access from the iframe. */
export function createPageObserver(exclude: HTMLElement, changed: () => void) {
  let closed = false, sequence = 0, timer = 0, lastUrl = location.href;
  const handles = new WeakMap<Element, string>();
  const elements = new Map<string, Element>();
  const clean = (text: string) => text.replace(/Bearer\s+[\w.\-]+/gi, 'Bearer [redacted]').replace(/sk-(?:or-v1-)?[a-zA-Z0-9]{20,}/g, '[redacted]').trim();
  const visible = (element: Element) => !exclude.contains(element) && !element.closest('[data-agent-ui], [hidden], [aria-hidden="true"], script, style, noscript') && Boolean(element.getClientRects().length) && getComputedStyle(element).visibility !== 'hidden';
  const text = (element: Element, max = 500) => clean((element as HTMLElement).innerText || element.textContent || '').slice(0, max);
  const id = (element: Element) => { let value = handles.get(element); if (!value) { value = 'dom:' + (++sequence); handles.set(element, value); elements.set(value, element); } return value; };
  const tables = () => Array.from(document.querySelectorAll('table,[role="table"],[role="grid"]')).filter(visible).filter(e => !e.parentElement?.closest('table,[role="table"],[role="grid"]'));
  function rows(table: Element) { return Array.from(table.querySelectorAll('tr,[role="row"]')).filter(visible).filter(r => r.querySelector('td,[role="cell"],[role="gridcell"]')); }
  function columns(table: Element) { return Array.from(table.querySelectorAll('th,[role="columnheader"]')).filter(visible).slice(0,12).map((c,i)=>({name:text(c,100)||'column_'+(i+1),type:'string'})); }
  function snapshot() {
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    const chunks: string[] = []; let count = 0, node: Node | null;
    while ((node = walker.nextNode()) && count < 16000) {
      const parent = node.parentElement;
      if (!parent || !visible(parent) || parent.closest('input,textarea,select')) continue;
      const value = clean(node.textContent || ''); if (value) { chunks.push(value); count += value.length; }
    }
    const content = chunks.join('\n').slice(0,16000);
    const url = new URL(location.href); ['agent_share','token','access_token','ticket','code'].forEach(k=>url.searchParams.delete(k));
    const value = {
      url:url.href,title:document.title,visible_text:content,
      headings:Array.from(document.querySelectorAll('h1,h2,h3,[role="heading"]')).filter(visible).slice(0,30).map(e=>text(e,160)),
      tables:tables().slice(0,8).map(t=>({resource_id:id(t),title:t.getAttribute('aria-label')||text(t.querySelector('caption')||t,100),columns:columns(t),visible_rows:rows(t).length})),
      controls:Array.from(document.querySelectorAll('button,a,input:not([type=password]):not([type=hidden]):not([type=file]),select,[role=tab]')).filter(visible).slice(0,50).map(e=>({handle:id(e),role:e.getAttribute('role')||e.tagName.toLowerCase(),label:e.getAttribute('aria-label')||text(e,120),selected:e.getAttribute('aria-selected')})),
      visuals:Array.from(document.querySelectorAll('canvas,img,svg[role=img]')).filter(visible).slice(0,20).map(e=>({kind:e.tagName.toLowerCase(),label:e.getAttribute('aria-label')||e.getAttribute('alt')||''})),
      limitations:['Visible DOM only; server-side pagination may contain additional rows.','Canvas and image pixels are not included.']
    };
    let hash=2166136261; for(const char of JSON.stringify(value))hash=Math.imul(hash^char.charCodeAt(0),16777619);
    return {...value,revision:'page-'+(hash>>>0).toString(16)};
  }
  function table(args: Record<string,unknown>) {
    const resource=String(args.resource_id||''); const element=elements.get(resource);
    if(!element || !element.isConnected || !visible(element) || !tables().includes(element))throw new Error('Table is no longer visible; inspect the page again.');
    const all=rows(element), offset=Math.max(0,Number(args.offset)||0), limit=Math.min(200,Math.max(1,Number(args.limit)||50));
    let cols=columns(element);
    if(!cols.length)cols=Array.from(all[0]?.querySelectorAll('td,[role=cell],[role=gridcell]')||[]).slice(0,30).map((_,i)=>({name:'column_'+(i+1),type:'string'}));
    const result: Record<string,string>[]=[];let bytes=0;
    for(const row of all.slice(offset,offset+limit)) {
      const cells=Array.from(row.querySelectorAll('td,[role=cell],[role=gridcell]')).filter(visible);
      const value=Object.fromEntries(cols.map((c,i)=>[c.name,cells[i]?text(cells[i],2000):'']));
      bytes+=new TextEncoder().encode(JSON.stringify(value)).length;if(bytes>300000)break;result.push(value);
    }
    return {resource_id:resource,title:element.getAttribute('aria-label')||'Visible table',columns:cols,rows:result,offset,total_rows:all.length,revision:snapshot().revision,truncated:result.length<Math.min(limit,all.length-offset)};
  }
  const notify=()=>{clearTimeout(timer);timer=window.setTimeout(()=>{if(!closed)changed();},350);};
  const mutations=new MutationObserver(records=>{if(records.some(r=>r.target instanceof Element ? visible(r.target) : r.target.parentElement&&visible(r.target.parentElement)))notify();});
  mutations.observe(document.body,{subtree:true,childList:true,characterData:true,attributes:true,attributeFilter:['aria-selected','aria-expanded','hidden','class']});
  document.addEventListener('input',notify,true);document.addEventListener('change',notify,true);
  const interval=window.setInterval(()=>{if(location.href!==lastUrl){lastUrl=location.href;notify();}for(const [key,e] of elements)if(!e.isConnected)elements.delete(key);},750);
  return {snapshot,table,exportData:(args:Record<string,unknown>)=>{const value=table({...args,limit:200});const quote=(v:unknown)=>'"'+String(v??'').replaceAll('"','""')+'"';return {filename:'visible_table.csv',content_type:'text/csv',content:[value.columns.map(c=>quote(c.name)).join(','),...value.rows.map(r=>value.columns.map(c=>quote(r[c.name])).join(','))].join('\n'),partial:value.truncated||value.total_rows>value.rows.length};},destroy:()=>{closed=true;clearTimeout(timer);clearInterval(interval);mutations.disconnect();document.removeEventListener('input',notify,true);document.removeEventListener('change',notify,true);elements.clear();}};
}
