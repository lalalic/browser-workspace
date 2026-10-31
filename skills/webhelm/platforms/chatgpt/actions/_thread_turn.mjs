import { existsSync } from "node:fs";
import {
  promptTextMatches,
  submissionFailureDiagnostic,
  submissionReceipt,
  SubmissionVerificationError,
  waitUntilStable,
} from "../runtime/readiness.mjs";
import {
  ASSISTANT_TURNS_JS,
  attachAppMention,
  COMPOSER_JS,
  composerText,
  sleep,
  USER_TURNS_JS,
} from "./_action-common.mjs";
export async function run({ helpers: h, config: c = {} }) {
  if (!c.thread_url) throw new Error("thread_url is required");
  const { js, goto_url, wait_for_load, page_info } = h,
    prompt = String(c.prompt || ""),
    files = c.file || [],
    expected = new URL(String(c.thread_url || "https://chatgpt.com")).pathname
      .replace(/\/$/, "");
  let target_id = c.target_id || null, recovered = false;
  if (target_id) {
    try {
      await h.switch_tab(target_id);
      if (
        new URL((await page_info()).url).pathname.replace(/\/$/, "") !==
          expected
      ) {
        await goto_url(c.thread_url);
        await wait_for_load();
        recovered = true;
      }
    } catch {
      target_id = null;
      recovered = true;
    }
  }
  if (!target_id) {
    target_id = await h.new_tab(c.thread_url);
    await wait_for_load();
  }
  const endHyd = Date.now() + 30000;
  let selector = null;
  while (Date.now() < endHyd) {
    selector = await js(COMPOSER_JS);
    if (
      selector &&
      new URL((await page_info()).url).pathname.replace(/\/$/, "") === expected
    ) break;
    await sleep(250);
  }
  if (!selector) {
    throw new Error(
      "Existing ChatGPT thread redirect mismatch or composer not hydrated",
    );
  }
  const users = async () => await js(USER_TURNS_JS) || [],
    assistants = async () => await js(ASSISTANT_TURNS_JS) || [];
  const getText = async (s) => await composerText(h, s),
    app = String(c.app || "").trim();
  if (app) await attachAppMention(h, selector, target_id, app);
  const editable = await js(
    `() => document.querySelector(${
      JSON.stringify(selector)
    })?.getAttribute('contenteditable')==='true'`,
  );
  if (app || !promptTextMatches(await getText(selector), prompt)) {
    if (editable) {
      await js(
        `(() => {const e=document.querySelector(${
          JSON.stringify(selector)
        });if(!e)return false;e.focus();const s=window.getSelection(),r=document.createRange();r.selectNodeContents(e);r.collapse(false);s.removeAllRanges();s.addRange(r);${
          app ? "" : "document.execCommand('delete',false,null);"
        }return true;})()`,
      );
      for (let i = 0; i < prompt.length; i += 256) {
        const chunk = prompt.slice(i, i + 256);
        if (
          !await js(
            `(() => {const e=document.querySelector(${
              JSON.stringify(selector)
            });if(!e)return false;e.focus();const ok=document.execCommand('insertText',false,${
              JSON.stringify(chunk)
            });e.dispatchEvent(new InputEvent('input',{bubbles:true,inputType:'insertText',data:${
              JSON.stringify(chunk)
            }}));return ok;})()`,
          )
        ) throw new Error("composer rejected prompt chunk");
      }
    } else {
      if (app) {
        throw new Error(
          "ChatGPT app mention requires a contenteditable composer",
        );
      }
      await h.fill_input(selector, prompt, { clear_first: true });
    }
  }
  let input = await js(
    `(() => ['#upload-files','#upload-media','input[name="upload-media"]','input[type="file"]'].find(s=>document.querySelector(s))||null)()`,
  );
  if (files.length && !input) {
    await js(
      `(() => {const b=[...document.querySelectorAll('button')].find(b=>(b.getAttribute('aria-label')||'').trim()==='Add files and more');if(!b)return false;b.click();return true;})()`,
    );
    for (let i = 0; i < 50 && !input; i++) {
      input = await js(
        `(() => ['#upload-files','#upload-media','input[name="upload-media"]','input[type="file"]'].find(s=>document.querySelector(s))||null)()`,
      );
      await sleep(100);
    }
  }
  if (files.length && !input) {
    throw new Error("ChatGPT file input was not observed");
  }
  const names = [];
  for (const f of files) {
    if (!existsSync(f)) throw new Error(`attachment does not exist: ${f}`);
    await h.upload_file(input, f);
    names.push(String(f).split(/[\\/]/).pop());
  }
  const attach = async () =>
    await js(
      `(() => {const names=[...document.querySelectorAll('button[aria-label^="Remove "]')].map(b=>(b.getAttribute('aria-label')||'').replace(/^Remove file\\s+\\d+:\\s*/,'').replace(/^Remove\\s+/,''));return {names,pending:[...document.querySelectorAll('[role="progressbar"],[aria-busy="true"],[data-state="loading"]')].some(e=>e.getClientRects().length>0)};})()`,
    ) || { names: [], pending: false };
  if (names.length) {
    await waitUntilStable(
      attach,
      (s) => names.every((n) => s.names.includes(n)) && !s.pending,
      {
        timeout: 120,
        phase: "attachment readiness",
        sleep,
      },
    );
  }
  const before = await users(), beforeAssistant = (await assistants()).length;
  await waitUntilStable(
    async () => ({
      text: await getText(selector),
      attachments: await attach(),
      send: await js(
        `(() => {const b=document.querySelector('button[data-testid="send-button"],button[aria-label="Send prompt"],button[aria-label="Send"]');return !!b&&!b.disabled&&b.getAttribute('aria-disabled')!=='true';})()`,
      ),
    }),
    (s) =>
      promptTextMatches(s.text, prompt) && names.every((n) =>
        s.attachments.names.includes(n)
      ) && !s.attachments.pending && s.send,
    { timeout: names.length ? 45 : 20, phase: "send readiness", sleep },
  );
  const uiBefore = {
    text_length: (await getText(selector)).length,
    users: before.length,
  };
  if (
    !await js(
      `(() => {const b=document.querySelector('button[data-testid="send-button"],button[aria-label="Send prompt"],button[aria-label="Send"]');if(!b||b.disabled||b.getAttribute('aria-disabled')==='true')return false;b.click();return true;})()`,
    )
  ) throw new Error("ChatGPT send button changed before click");
  let receipt = null;
  const sendEnd = Date.now() + 30000;
  while (Date.now() < sendEnd) {
    receipt = submissionReceipt(
      await users(),
      before.length,
      prompt,
      await getText(selector),
    );
    if (receipt) break;
    await sleep(250);
  }
  if (!receipt) {
    throw new SubmissionVerificationError(
      "ChatGPT submission verification did not observe an accepted submission",
      submissionFailureDiagnostic(
        await users(),
        before.length,
        prompt,
        await getText(selector),
        uiBefore,
        null,
      ),
    );
  }
  const resultEnd = Date.now() + Number(c.result_timeout || 240) * 1000;
  let signature = null, since = null, assistant;
  while (Date.now() < resultEnd) {
    const stop = await js(
      `(() => [...document.querySelectorAll('button')].some(b=>/stop answering|stop generating/i.test(b.getAttribute('aria-label')||'')||/stop/i.test(b.getAttribute('data-testid')||'')))()`,
    );
    if (stop) {
      signature = null;
      since = null;
      await sleep(500);
      continue;
    }
    const list = await assistants();
    if (list.length <= beforeAssistant) {
      await sleep(500);
      continue;
    }
    const latest = list.at(-1), sig = JSON.stringify([latest.id, latest.text]);
    if (sig !== signature) {
      signature = sig;
      since = Date.now();
      await sleep(500);
      continue;
    }
    if (!latest.text || !since || Date.now() - since < 3000) {
      await sleep(500);
      continue;
    }
    assistant = latest;
    break;
  }
  if (!assistant) {
    throw new Error(
      "ChatGPT assistant result did not become complete before timeout",
    );
  }
  return {
    status: "completed",
    thread_url: (await page_info()).url.split("?")[0],
    target_id,
    recovered,
    attachments: names,
    app: app || null,
    verified_by: receipt.verified_by,
    user_message_id: receipt.turn.id || null,
    assistant_message_id: assistant.id || null,
    text: assistant.text || "",
  };
}
