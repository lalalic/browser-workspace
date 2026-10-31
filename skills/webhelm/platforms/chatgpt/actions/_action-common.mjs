import { promptTextMatches, waitUntilStable } from "../runtime/readiness.mjs";
import {
  prefilledSubmit,
  targetUrl,
  visibleDeliveryError,
} from "../runtime/lifecycle-common.mjs";
export {
  prefilledSubmit,
  promptTextMatches,
  targetUrl,
  visibleDeliveryError,
  waitUntilStable,
};
export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
export const text = (v) => String(v ?? "").trim();
export const pathThreadId = (url) => {
  const m = String(url).match(/\/c\/([^/?#]+)/);
  return m?.[1] || null;
};
export async function requireNoDeliveryError(helpers) {
  const err = await visibleDeliveryError(helpers.js);
  if (err) throw new Error(`ChatGPT visible delivery error: ${err}`);
}
export const SEND_READY_JS =
  `(() => { const b=document.querySelector('button[data-testid="send-button"],button[aria-label="Send prompt"],button[aria-label="Send"],form button[type="submit"]'); return !!b&&!b.disabled&&b.getAttribute('aria-disabled')!=='true'; })()`;
export const USER_TURNS_JS =
  `(() => { const old=[...document.querySelectorAll('[data-message-author-role="user"]')].map(e=>({text:(e.innerText||'').trim(),id:e.getAttribute('data-message-id')||''})).filter(x=>x.text); if(old.length)return old;return [...document.querySelectorAll('h4')].filter(e=>(e.innerText||'').trim()==='You said:').map((e,i)=>({text:(e.parentElement?.innerText||'').replace(/^You said:\\s*/,'').trim(),id:'dom-user-'+i})).filter(x=>x.text); })()`;
export const ASSISTANT_TURNS_JS =
  `(() => { const old=[...document.querySelectorAll('[data-message-author-role="assistant"]')].map(e=>({text:(e.innerText||'').trim(),id:e.getAttribute('data-message-id')||''})).filter(x=>x.text); if(old.length)return old;return [...document.querySelectorAll('h4')].filter(e=>(e.innerText||'').trim()==='ChatGPT said:').map((e,i)=>({text:(e.parentElement?.innerText||'').replace(/^ChatGPT said:\\s*/,'').trim(),id:'dom-assistant-'+i})).filter(x=>x.text); })()`;
export const COMPOSER_JS =
  `(() => { const ss=['#prompt-textarea','[contenteditable="true"][data-composer-markdown]','[contenteditable="true"][data-lexical-editor="true"]','textarea'];for(const s of ss){const e=document.querySelector(s);if(!e||e.disabled||['pending-home-input','pending-conversation-input'].includes(e.id))continue;const r=e.getBoundingClientRect();if(r.width>0&&r.height>0)return s;}const v=[...document.querySelectorAll('[contenteditable="true"]')].filter(e=>!e.disabled&& !['pending-home-input','pending-conversation-input'].includes(e.id)&&e.getBoundingClientRect().width>0&&e.getBoundingClientRect().height>0);return v.length===1?'[contenteditable="true"]':null; })()`;
export async function composerText(helpers, selector) {
  return await helpers.js(
    `(() => {const e=document.querySelector(${
      JSON.stringify(selector)
    });if(!e)return '';if(e.getAttribute('contenteditable')!=='true')return e.value||'';const c=e.cloneNode(true);c.querySelectorAll('[app-mention-name]').forEach(n=>n.remove());return (c.innerText||c.textContent||'').trim();})()`,
  ) || "";
}
export async function setField(helpers, selector, value) {
  const ok = await helpers.js(
    `(() => {const e=document.querySelector(${
      JSON.stringify(selector)
    });if(!e)return false;e.focus();if(e instanceof HTMLTextAreaElement||e instanceof HTMLInputElement){const p=e instanceof HTMLTextAreaElement?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;Object.getOwnPropertyDescriptor(p,'value')?.set?.call(e,${
      JSON.stringify(value)
    });}else{const s=window.getSelection(),r=document.createRange();r.selectNodeContents(e);s.removeAllRanges();s.addRange(r);document.execCommand('delete',false,null);document.execCommand('insertText',false,${
      JSON.stringify(value)
    });s.removeAllRanges();}e.dispatchEvent(new InputEvent('input',{bubbles:true,inputType:'insertText',data:${
      JSON.stringify(value)
    }}));e.dispatchEvent(new Event('change',{bubbles:true}));return true;})()`,
  );
  if (!ok) throw new Error("composer could not be filled");
}

export async function attachAppMention(
  helpers,
  selector,
  targetId,
  name,
  { timeout = 10 } = {},
) {
  const app = String(name || "").trim();
  if (!app) return false;
  const cleared = await helpers.js(
    `(() => {const e=document.querySelector(${
      JSON.stringify(selector)
    });if(!e||e.getAttribute('contenteditable')!=='true')return false;e.focus();const s=window.getSelection(),r=document.createRange();r.selectNodeContents(e);s.removeAllRanges();s.addRange(r);document.execCommand('delete',false,null);return true;})()`,
  );
  if (!cleared) {
    throw new Error(
      "ChatGPT app mention requires a visible contenteditable composer",
    );
  }
  const attached = await helpers.cdp("Target.attachToTarget", {
    targetId,
    flatten: true,
  });
  await helpers.cdp("Input.insertText", {
    session_id: attached.sessionId,
    text: "@",
  });
  const wanted = app.toLowerCase(), end = Date.now() + timeout * 1000;
  let found = false;
  while (Date.now() < end) {
    found = await helpers.js(
      `(() => {const wanted=${
        JSON.stringify(wanted)
      },nodes=[...document.querySelectorAll('button,[role="option"],[role="menuitem"]')],e=nodes.find(n=>{const t=(n.innerText||n.textContent||'').replace(/\\s+/g,'').trim().toLowerCase();return t===wanted.replace(/\\s+/g,'')||t===(wanted+wanted).replace(/\\s+/g,'')});if(!e)return false;e.click();return true;})()`,
    );
    if (found) break;
    await sleep(100);
  }
  if (!found) {
    throw new Error(`ChatGPT app '${app}' was not offered by the composer`);
  }
  while (Date.now() < end) {
    if (
      await helpers.js(
        `(() => {const e=document.querySelector(${
          JSON.stringify(selector)
        });return !!e&&!![...e.querySelectorAll('[app-mention-name]')].find(n=>(n.getAttribute('app-mention-name')||'').toLowerCase()===${
          JSON.stringify(wanted)
        });})()`,
      )
    ) return true;
    await sleep(100);
  }
  throw new Error(`ChatGPT app '${app}' mention did not attach`);
}
