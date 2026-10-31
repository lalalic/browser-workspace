import { targetUrl, visibleDeliveryError } from './_action-common.mjs';

const READINESS = `(()=>{
  const visible=e=>{const r=e.getBoundingClientRect();return r.width>0&&r.height>0};
  const composer=[...document.querySelectorAll('#prompt-textarea,[contenteditable="true"][data-composer-markdown],[contenteditable="true"][data-lexical-editor="true"],textarea')]
    .find(e=>visible(e)&&!e.disabled);
  const text=(composer?.innerText||composer?.value||composer?.textContent||'').trim();
  const b=[...document.querySelectorAll('button[data-testid="send-button"],button[aria-label="Send prompt"],button[aria-label="Send"],form button[type="submit"]')]
    .find(visible);
  const login=[...document.querySelectorAll('a,button')].some(e=>visible(e)&&/^(log in|sign in)$/i.test((e.innerText||'').trim()))
    &&/(log in to chatgpt|sign in to chatgpt)/i.test(document.body?.innerText||'');
  return {ready:!!composer && text.includes('BrowserWorkspaceValidateProbe20261020') && !!b && !b.disabled && b.getAttribute('aria-disabled')!=='true',login};
})()`;

export async function run({ helpers, config = {} }) {
  const {js,goto_url,wait_for_load}=helpers;
  const probe='BrowserWorkspaceValidateProbe20261020';
  await goto_url(targetUrl({
    project_id:String(config.project_id||'').trim()||undefined,
    thread_id:String(config.thread_id||'').trim()||undefined,
    temporary:!!config.temporary,
    prompt:probe,
  }));
  await wait_for_load();
  const end=Date.now()+12_000;
  do {
    const error=await visibleDeliveryError(js);
    if(error)return error;
    const state=await js(READINESS);
    if(state?.login)return 'authentication_required';
    if(state?.ready)return true;
    if(Date.now()>=end)break;
    await new Promise(resolve=>setTimeout(resolve,250));
  }while(true);
  return false;
}
