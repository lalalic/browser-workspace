export const MANAGER_URL = "https://channels.weixin.qq.com/platform/post/list";
const priority = [
  "finderobjectid",
  "postid",
  "contentid",
  "videoid",
  "objectid",
  "exportid",
  "feedid",
  "mediaid",
];
export function statusLabel(text) {
  for (
    const [label, status] of [
      ["审核中", "reviewing"],
      ["未通过", "rejected"],
      ["草稿", "draft"],
      ["已发布", "published"],
      ["已发表", "published"],
    ]
  ) if (text.includes(label)) return { label, status };
  return { label: null, status: null };
}
export function extractStableId(row) {
  const ids = { ...(row.stable_ids || {}) };
  for (const url of row.urls || []) {
    try {
      for (const [key, value] of new URL(url).searchParams) {
        const normalized = key.toLowerCase().replace(/[^a-z0-9]/g, "");
        if (priority.includes(normalized)) ids[normalized] = value;
      }
    } catch {}
  }
  return priority.map((k) => ids[k]).find(Boolean) || null;
}
export function chooseManagerRow(rows, postId, title, desc) {
  const matches = postId
    ? rows.filter((r) => extractStableId(r) === postId)
    : title
    ? rows.filter((r) => (r.text || "").includes(title))
    : desc
    ? rows.filter((r) => (r.text || "").includes(desc))
    : [];
  return matches.sort((a, b) =>
    (a.text || "").length - (b.text || "").length
  )[0] || null;
}
export function managerScanExpression(postId, title, desc) {
  return `(()=>{const root=document.querySelector('wujie-app')?.shadowRoot,body=root?.querySelector('body')||root;if(!body)return '[]';const priority=${
    JSON.stringify(priority)
  },labels=['审核中','未通过','草稿','已发布','已发表'],normalize=x=>x.toLowerCase().replace(/[^a-z0-9]/g,''),targetPostId=${
    JSON.stringify(postId || "")
  },targetTitle=${JSON.stringify(title || "")},targetDesc=${
    JSON.stringify(desc || "")
  },items=new Map();const idsOf=e=>{const m=new Map();for(const a of e.attributes||[]){const k=normalize(a.name),v=a.value.trim();if(v&&priority.includes(k))m.set(k,v)}return m};const add=(e,kind,ids)=>{const attributes={};for(const a of e.attributes||[])if(a.name.startsWith('data-')||['aria-label','title'].includes(a.name))attributes[a.name]=a.value;const urls=[...e.querySelectorAll('a[href]')].map(a=>a.href),text=(e.innerText||e.textContent||'').replace(/\\s+/g,' ').trim();if(!text||text.length>3000)return;const key=kind+JSON.stringify([...ids])+text;if(!items.has(key))items.set(key,{kind,stable_ids:Object.fromEntries(ids),attributes,urls,text,tag:e.tagName.toLowerCase()})};for(const e of body.querySelectorAll('*')){const ids=idsOf(e),text=e.innerText||e.textContent||'';if((targetTitle&&text.includes(targetTitle))||(targetDesc&&text.includes(targetDesc))){let p=e,pi=ids;for(let d=0;p&&p!==body&&d<12;d++,p=p.parentElement){const t=p.innerText||p.textContent||'',x=idsOf(p);if(labels.some(l=>t.includes(l))||x.size){pi=x;break}}add(p&&p!==body?p:e,'text',pi)}if(ids.size){let p=e;for(let d=0;p&&p!==body&&d<12;d++,p=p.parentElement)if(labels.some(l=>(p.innerText||p.textContent||'').includes(l)))break;add(p&&p!==body?p:e,'id',ids)}}return JSON.stringify([...items.values()])})()`;
}
