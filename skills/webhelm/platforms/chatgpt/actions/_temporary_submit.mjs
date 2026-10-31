import { existsSync } from "node:fs";
import {
  promptTextMatches,
  sendReady,
  submissionReceipt,
  waitUntilStable,
} from "../runtime/readiness.mjs";
import {
  COMPOSER_JS,
  composerText,
  sleep,
  targetUrl,
} from "./_action-common.mjs";
const CANDIDATES =
  `(() => [...document.querySelectorAll('button')].map((b,index)=>{const label=(b.getAttribute('aria-label')||'').trim(),text=(b.innerText||'').trim(),s=label+' '+text;if(!/temporary/i.test(s)||!/chat/i.test(s))return null;const r=b.getBoundingClientRect(),c=getComputedStyle(b);return {index,label,text,visible:r.width>0&&r.height>0&&c.visibility!=='hidden'&&c.display!=='none',disabled:!!b.disabled||b.getAttribute('aria-disabled')==='true',pointerEvents:c.pointerEvents};}).filter(Boolean))()`;
export async function run({ helpers: h, config: c = {} }) {
  const prompt = String(c.prompt || "");
  if (!prompt) throw new Error("prompt is required");
  const owned = [];
  let succeeded = false;
  const closeOwned = async () => {
    if (c.close_policy === "never" && succeeded) return;
    while (owned.length) {
      const t = owned.pop();
      try {
        await h.close_tab(t.targetId);
      } catch {
        try {
          const cur = await h.current_tab();
          if (cur?.tabId === t.tabId) await h.close_tab();
        } catch {}
      }
    }
  };
  try {
    const target_id = await h.new_tab(targetUrl({ temporary: true, prompt }));
    const tabs = await h.list_tabs({ include_chrome: false });
    const found = tabs.filter((t) => t.targetId === target_id);
    if (found.length !== 1) {
      throw new Error(
        `Owned Browser Workspace target ${target_id} was not mapped to one tab`,
      );
    }
    owned.push({ targetId: target_id, tabId: found[0].tabId });
    await h.wait_for_load();
    const tempEnabled = async () => {
      const url = (await h.page_info()).url || "",
        cands = await h.js(CANDIDATES) || [];
      return url.includes("temporary-chat=true") ||
        cands.some((x) =>
          x.visible && !x.disabled && x.pointerEvents !== "none" &&
          /turn off/i.test(`${x.label} ${x.text}`)
        );
    };
    const clickToggle = async () => {
      const end = Date.now() + 20000;
      let last = [];
      while (Date.now() < end) {
        if (await tempEnabled()) return;
        last = await h.js(CANDIDATES) || [];
        const a = last.filter((x) =>
          x.visible && !x.disabled && x.pointerEvents !== "none"
        );
        if (a.length > 1) {
          throw new Error(
            `Temporary Chat toggle is ambiguous: ${a.length} actionable controls`,
          );
        }
        if (a.length === 1) {
          const ok = await h.js(
            `(() => {const b=[...document.querySelectorAll('button')][${
              a[0].index
            }],r=b?.getBoundingClientRect(),s=b&&getComputedStyle(b);if(!b||!r.width||!r.height||b.disabled||b.getAttribute('aria-disabled')==='true'||s.pointerEvents==='none')return false;b.click();return true;})()`,
          );
          if (ok) return;
        }
        await sleep(250);
      }
      throw new Error(
        `Temporary Chat toggle was not actionable; candidates=${
          JSON.stringify(last)
        }`,
      );
    };
    await clickToggle();
    await waitUntilStable(tempEnabled, Boolean, {
      timeout: 20,
      phase: "Temporary Chat activation",
      sleep,
    });
    const submitPage = async () => {
      let selector = await waitUntilStable(() => h.js(COMPOSER_JS), Boolean, {
          timeout: 30,
          phase: "composer readiness",
          sleep,
        }),
        txt = await composerText(h, selector);
      if (!promptTextMatches(txt, prompt)) {
        const editable = await h.js(
          `() => document.querySelector(${
            JSON.stringify(selector)
          })?.getAttribute('contenteditable')==='true'`,
        );
        if (editable) {
          await h.js(
            `(() => {const e=document.querySelector(${
              JSON.stringify(selector)
            });e.focus();const s=window.getSelection(),r=document.createRange();r.selectNodeContents(e);s.removeAllRanges();s.addRange(r);document.execCommand('delete',false,null);return true;})()`,
          );
          for (let i = 0; i < prompt.length; i += 256) {
            const part = prompt.slice(i, i + 256);
            if (
              !await h.js(
                `(() => {const e=document.querySelector(${
                  JSON.stringify(selector)
                });e.focus();const ok=document.execCommand('insertText',false,${
                  JSON.stringify(part)
                });e.dispatchEvent(new InputEvent('input',{bubbles:true,inputType:'insertText',data:${
                  JSON.stringify(part)
                }}));return ok;})()`,
              )
            ) throw new Error("Temporary Chat composer rejected prompt");
          }
        } else await h.fill_input(selector, prompt, { clear_first: true });
      }
      const files = c.file || [], names = [];
      let fileSel = await h.js(
        `(() => ['#upload-files','#upload-media','input[name="upload-media"]','input[type="file"]'].find(s=>document.querySelector(s))||null)()`,
      );
      if (files.length && !fileSel) {
        await h.js(
          `(() => {const b=[...document.querySelectorAll('button')].find(x=>(x.getAttribute('aria-label')||'').trim()==='Add files and more');if(!b)return false;b.click();return true;})()`,
        );
        for (let i = 0; i < 50 && !fileSel; i++) {
          fileSel = await h.js(
            `(() => ['#upload-files','#upload-media','input[name="upload-media"]','input[type="file"]'].find(s=>document.querySelector(s))||null)()`,
          );
          await sleep(100);
        }
      }
      if (files.length && !fileSel) {
        throw new Error("ChatGPT file input was not observed");
      }
      for (const f of files) {
        if (!existsSync(f)) throw new Error(`attachment does not exist: ${f}`);
        await h.upload_file(fileSel, f);
        names.push(String(f).split(/[\\/]/).pop());
      }
      const attachments = async () =>
        await h.js(
          `(() => {const names=[...document.querySelectorAll('button[aria-label^="Remove "]')].map(b=>(b.getAttribute('aria-label')||'').replace(/^Remove file\\s+\\d+:\\s*/,'').replace(/^Remove\\s+/,''));return {names,pending:[...document.querySelectorAll('[role="progressbar"],[aria-busy="true"],[data-state="loading"]')].some(e=>e.getBoundingClientRect().width>0)};})()`,
        ) || { names: [], pending: false };
      if (names.length) {
        await waitUntilStable(
          attachments,
          (s) => names.every((x) => s.names.includes(x)) && !s.pending,
          {
            timeout: 120,
            phase: "attachment readiness",
            sleep,
          },
        );
      }
      const users = async () =>
        await h.js(
          `(() => [...document.querySelectorAll('[data-message-author-role="user"]')].map((e,i)=>({text:(e.innerText||'').trim(),id:e.getAttribute('data-message-id')||''})).filter(x=>x.text))()`,
        ) || [];
      const before = (await users()).length;
      await waitUntilStable(
        async () => ({
          text: await composerText(h, selector),
          attachments: await attachments(),
          send: await h.js(
            `(() => {const b=document.querySelector('button[data-testid="send-button"],button[aria-label="Send prompt"],button[aria-label="Send"]');return {enabled:!!b&&!b.disabled&&b.getAttribute('aria-disabled')!=='true'};})()`,
          ),
        }),
        (s) => sendReady(s, { prompt, attachments: names }),
        { timeout: names.length ? 45 : 15, phase: "send readiness", sleep },
      );
      if (
        !await h.js(
          `(() => {const b=document.querySelector('button[data-testid="send-button"],button[aria-label="Send prompt"],button[aria-label="Send"]');if(!b||b.disabled||b.getAttribute('aria-disabled')==='true')return false;b.click();return true;})()`,
        )
      ) throw new Error("Temporary Chat send readiness changed before click");
      const end = Date.now() + 20000;
      let receipt = null, cleared = 0;
      while (Date.now() < end) {
        receipt = submissionReceipt(
          await users(),
          before,
          prompt,
          await composerText(h, selector),
          { allowComposerCleared: true },
        );
        if (receipt?.verified_by === "user-turn") break;
        if (receipt) { if (++cleared >= 2) break; }
        else cleared = 0;
        await sleep(250);
      }
      if (!receipt) {
        throw new Error(
          "ChatGPT submission verification did not observe an accepted submission",
        );
      }
      succeeded = true;
      const cur = await h.page_info(),
        match = String(cur.url).match(/\/c\/([^/?#]+)/);
      const tab = owned.at(-1);
      return {
        operation: "submit",
        status: "submitted",
        temporary: true,
        attachments: names,
        diagnostic_thread_id: match?.[1] || null,
        user_message_id: receipt.turn?.id || null,
        owned_tab_id: tab?.tabId,
        owned_target_id: tab?.targetId,
        verified_by: receipt.verified_by,
        verified: true,
      };
    };
    let result;
    try {
      result = await submitPage();
    } catch (e) {
      if (!String(e).includes("composer readiness was not observed ready")) {
        throw e;
      }
      await h.goto_url(targetUrl({ temporary: true }));
      await h.wait_for_load();
      await clickToggle();
      if (!await tempEnabled()) {
        throw new Error("Temporary Chat mode lost during composer recovery");
      }
      result = await submitPage();
    }
    return result;
  } finally {
    await closeOwned();
  }
}
