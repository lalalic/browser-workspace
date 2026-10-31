export function targetUrl(projectId, threadId, message) {
  if (!threadId || !message) {
    throw new Error("thread_id and message are required");
  }
  const prefix = projectId ? `/g/${encodeURIComponent(projectId)}` : "";
  return `https://chatgpt.com${prefix}/c/${
    encodeURIComponent(threadId)
  }?${new URLSearchParams({ prompt: message })}`;
}
export const PROBE_JS =
  `(() => { const visible=e=>!!e&&!!e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden'; const body=(document.body?.innerText||'').toLowerCase(); if(body.includes('could not load this chatgpt conversation'))return {state:'BLOCKED',error:'thread_load_failed'}; if(body.includes('log in to chatgpt')||body.includes('sign in to chatgpt'))return {state:'BLOCKED',error:'authentication_required'}; const stop=[...document.querySelectorAll('button')].some(b=>{if(!visible(b))return false;const l=(b.getAttribute('aria-label')||'').trim().toLowerCase(),t=(b.getAttribute('title')||'').trim().toLowerCase(),d=(b.getAttribute('data-testid')||'').trim().toLowerCase();return ['stop generating','stop answering','stop response','stop'].includes(l)||['stop generating','stop answering'].includes(t)||['stop-button','stop-generating-button'].includes(d)}); if(stop)return {state:'RUNNING',stop_visible:true}; const e=document.querySelector('#prompt-textarea,[contenteditable="true"][data-lexical-editor="true"],[role="textbox"][contenteditable="true"],textarea'); const editable=e?.getAttribute?.('contenteditable')==='true'; return {state:visible(e)?'READY':'NOT_READY',stop_visible:false,composer_text:e?(editable?(e.textContent||''):(e.value||e.textContent||e.innerText||'')):''}; })()`;
export function classifyProbe(observedUrl, expectedUrl, state) {
  const actual = new URL(observedUrl), expected = new URL(expectedUrl);
  if (
    actual.protocol !== "https:" || actual.host !== "chatgpt.com" ||
    actual.pathname.replace(/\/$/, "") !== expected.pathname.replace(/\/$/, "")
  ) return "BLOCKED";
  if (["RUNNING", "BLOCKED"].includes(state?.state)) return state.state;
  if (actual.search) return "NOT_READY";
  return state?.state === "READY" && String(state.composer_text || "").trim()
    ? "READY"
    : "NOT_READY";
}
