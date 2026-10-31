import { existsSync } from "node:fs";
import {
  promptTextMatches,
  submissionFailureDiagnostic,
  submissionReceipt,
  SubmissionVerificationError,
  waitUntilStable,
} from "../runtime/readiness.mjs";
import {
  COMPOSER_JS,
  composerText,
  sleep,
  USER_TURNS_JS,
} from "./_action-common.mjs";
const ATTACH =
  `(() => {const names=[...document.querySelectorAll('button[aria-label^="Remove "]')].map(b=>(b.getAttribute('aria-label')||'').replace(/^Remove file\\s+\\d+:\\s*/, '').replace(/^Remove\\s+/,'' )).filter(Boolean);const visible=e=>{const r=e.getBoundingClientRect();return r.width>0&&r.height>0};return {names,pending:[...document.querySelectorAll('[role="progressbar"],[aria-busy="true"],[data-state="loading"]')].some(visible)};})()`;
export async function run({ helpers, config = {} }) {
  const h = helpers,
    { js, goto_url, wait_for_load, upload_file } = h,
    project_id = String(config.project_id || "").trim(),
    thread_id = String(config.thread_id || "").trim(),
    prompt = String(config.prompt || ""),
    files = Array.isArray(config.file) ? config.file : [],
    app = String(config.app || "").trim();
  if (!project_id || !thread_id) {
    throw new Error("project_id and thread_id are required");
  }
  if (!prompt && !files.length) throw new Error("prompt or file is required");
  const thread_url = `https://chatgpt.com/g/${
    encodeURIComponent(project_id)
  }/c/${encodeURIComponent(thread_id)}`;
  await goto_url(thread_url + "?prompt=" + encodeURIComponent(prompt));
  await wait_for_load();
  const state = async () =>
    await js(
      `(() => {const ss=['#prompt-textarea','[contenteditable="true"][data-composer-markdown]','[contenteditable="true"][data-lexical-editor="true"]','textarea'];const es=[...new Set(ss.flatMap(s=>[...document.querySelectorAll(s)]))],e=es.find(n=>{const r=n.getBoundingClientRect();return !n.disabled&&r.width>0&&r.height>0});if(!e)return {present:false,text:'',sendEnabled:false};const b=e.closest('form')?.querySelector('button[data-testid="send-button"],button[aria-label="Send prompt"],button[aria-label="Send"]');return {present:true,text:(e.innerText||e.value||e.textContent||'').trim(),sendEnabled:!!b&&!b.disabled&&b.getAttribute('aria-disabled')!=='true'};})()`,
    ) || { present: false, text: "", sendEnabled: false };
  await waitUntilStable(state, (s) => s.present, {
    timeout: 20,
    phase: "composer readiness",
    sleep,
  });
  await waitUntilStable(state, (s) => promptTextMatches(s.text, prompt), {
    timeout: 20,
    phase: "prefilled thread readiness",
    sleep,
  });
  if (app) {
    const sel = await js(COMPOSER_JS);
    const ok = await js(
      `(() => {const e=document.querySelector(${
        JSON.stringify(sel)
      });if(!e||e.getAttribute('contenteditable')!=='true')return false;e.focus();const s=window.getSelection(),r=document.createRange();r.selectNodeContents(e);s.removeAllRanges();s.addRange(r);document.execCommand('delete',false,null);s.removeAllRanges();return true;})()`,
    );
    if (!ok) {
      throw new Error(
        "ChatGPT app mention requires a visible contenteditable composer",
      );
    }
    const target = h.target_id || h.targetId;
      await h.cdp("Input.insertText", { text: "@" });
    let chosen = false;
    for (let i = 0; i < 120; i++) {
      chosen = await js(
        `(() => {const w=${
          JSON.stringify(app.toLowerCase())
        },xs=[...document.querySelectorAll('button,[role="option"],[role="menuitem"]')],e=xs.find(n=>{const t=(n.innerText||n.textContent||'').replace(/\\s+/g,'').trim().toLowerCase();return t===w.replace(/\\s+/g,'')||t===(w+w).replace(/\\s+/g,'')});if(!e)return false;e.click();return true;})()`,
      );
      if (chosen) break;
      await sleep(100);
    }
    if (!chosen) {
      throw new Error(`ChatGPT app '${app}' was not offered by the composer`);
    }
    let mention = false;
    for (let i = 0; i < 120; i++) {
      mention = await js(
        `(() => {const e=document.querySelector(${
          JSON.stringify(sel)
        });return !!e&&!![...e.querySelectorAll('[app-mention-name]')].find(n=>(n.getAttribute('app-mention-name')||'').toLowerCase()===${
          JSON.stringify(app.toLowerCase())
        });})()`,
      );
      if (mention) break;
      await sleep(100);
    }
    if (!mention) {
      throw new Error(`ChatGPT app '${app}' mention did not attach`);
    }
    for (let i = 0; i < prompt.length; i += 256) {
      const part = prompt.slice(i, i + 256);
      if (
        !await js(
          `(() => {const e=document.querySelector(${
            JSON.stringify(sel)
          });if(!e)return false;e.focus();const s=window.getSelection(),r=document.createRange();r.selectNodeContents(e);r.collapse(false);s.removeAllRanges();s.addRange(r);const ok=document.execCommand('insertText',false,${
            JSON.stringify(part)
          });e.dispatchEvent(new InputEvent('input',{bubbles:true,inputType:'insertText',data:${
            JSON.stringify(part)
          }}));return ok;})()`,
        )
      ) throw new Error("ChatGPT composer rejected prompt after app mention");
    }
  }
  const attach = async () => await js(ATTACH) || { names: [], pending: false };
  let selector = await js(
    `(() => ['#upload-files','#upload-media','input[name="upload-media"]','input[type="file"]'].find(s=>document.querySelector(s))||null)()`,
  );
  if (files.length && !selector) {
    await js(
      `(() => {const b=[...document.querySelectorAll('button')].find(b=>(b.getAttribute('aria-label')||'').trim()==='Add files and more');if(!b)return false;b.click();return true;})()`,
    );
    for (let i = 0; i < 50 && !selector; i++) {
      selector = await js(
        `(() => ['#upload-files','#upload-media','input[name="upload-media"]','input[type="file"]'].find(s=>document.querySelector(s))||null)()`,
      );
      if (!selector) await sleep(100);
    }
  }
  if (files.length && !selector) {
    throw new Error("ChatGPT file input was not observed");
  }
  const expected = [];
  for (const f of files) {
    if (!existsSync(f)) throw new Error(`attachment does not exist: ${f}`);
    await upload_file(selector, f);
    expected.push(String(f).split(/[\\/]/).pop());
  }
  if (expected.length) {
    await waitUntilStable(
      attach,
      (s) => expected.every((n) => s.names.includes(n)) && !s.pending,
      {
        timeout: 120,
        phase: "attachment readiness",
        sleep,
      },
    );
  }
  const users = async () => await js(USER_TURNS_JS) || [];
  const before = (await users()).length;
  await waitUntilStable(
    async () => ({ composer: await state(), attachments: await attach() }),
    (s) =>
      promptTextMatches(s.composer.text, prompt) && expected.every((n) =>
        s.attachments.names.includes(n)
      ) && !s.attachments.pending && s.composer.sendEnabled,
    { timeout: expected.length ? 45 : 20, phase: "send readiness", sleep },
  );
  const beforeUI = await state();
  const clicked = await js(
    `(() => {const ss=['#prompt-textarea','[contenteditable="true"][data-composer-markdown]','[contenteditable="true"][data-lexical-editor="true"]','textarea'],e=[...new Set(ss.flatMap(s=>[...document.querySelectorAll(s)]))].find(n=>{const r=n.getBoundingClientRect();return !n.disabled&&r.width>0&&r.height>0}),b=e?.closest('form')?.querySelector('button[data-testid="send-button"],button[aria-label="Send prompt"],button[aria-label="Send"]');if(!b||b.disabled||b.getAttribute('aria-disabled')==='true')return false;b.click();return true;})()`,
  );
  if (!clicked) throw new Error("ChatGPT send button changed before click");
  let receipt = null;
  const deadline = Date.now() + 15000;
  while (Date.now() < deadline) {
    receipt = submissionReceipt(
      await users(),
      before,
      prompt,
      (await state()).text,
    );
    if (receipt) break;
    await sleep(100);
  }
  if (!receipt) {
    const aft = await state(), all = await users();
    throw new SubmissionVerificationError(
      "ChatGPT submission verification did not observe an accepted submission",
      submissionFailureDiagnostic(all, before, prompt, aft.text, {
        composer_present: beforeUI.present,
        composer_text_length: beforeUI.text.length,
        send_enabled: beforeUI.sendEnabled,
      }, {
        composer_present: aft.present,
        composer_text_length: aft.text.length,
        send_enabled: aft.sendEnabled,
      }),
    );
  }
  return {
    status: "submitted",
    project_id,
    thread_id,
    thread_url,
    verified_by: receipt.verified_by,
    user_message_id: receipt.turn.id || null,
    app: app || null,
  };
}
