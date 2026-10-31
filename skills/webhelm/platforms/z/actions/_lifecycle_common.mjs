import { sleep } from "../../_action_helpers.mjs";
export const BASE_URL = "https://chat.z.ai/";
export const COMPOSER = 'textarea[placeholder="Send a Message"]';
export const SEND_BUTTON = "#send-message-button";
export const STREAM_OBSERVER =
  `(()=>{if(window.__webhelmZStream?.version===1)return;const observer={version:1,entries:[]};window.__webhelmZStream=observer;const nativeFetch=window.fetch;window.fetch=function(...args){const url=String(args[0]?.url||args[0]||'');const request=nativeFetch.apply(this,args);if(!/\\/api(?:\\/v2)?\\/chat\\/(?:completions|continue)(?:\\?|$)/.test(url))return request;return request.then(response=>{const item={state:'reading',status:response.status,body:'',error:''};observer.entries.push(item);if(observer.entries.length>8)observer.entries.shift();response.clone().text().then(body=>{if(body.length>1500000){item.state='oversized';item.error='Z.ai stream exceeds 1.5MB'}else{item.state='received';item.body=body}}).catch(err=>{item.state='read_error';item.error=String(err)});return response})}})()`;
export const STREAM_STATE =
  `(()=>{const entries=window.__webhelmZStream?.entries||[];return{count:entries.length,latest:entries.length?{state:entries.at(-1).state,status:entries.at(-1).status,error:entries.at(-1).error}:null}})()`;
export const STREAM_BODY =
  `(()=>window.__webhelmZStream?.entries.at(-1)?.body||'')()`;
export function parseSiteStream(body) {
  if (typeof body !== "string") return null;
  let content = "", finished = false;
  for (const block of body.split(/\r?\n\r?\n/)) {
    const lines = block.split(/\r?\n/).filter((x) => x.startsWith("data:")).map(
      (x) => x.slice(5).trim(),
    );
    if (!lines.length) continue;
    let payload;
    try {
      payload = JSON.parse(lines.join("\n"));
    } catch {
      continue;
    }
    if (!payload || typeof payload !== "object") continue;
    if (payload.type === "error") {
      throw new Error("Z.ai returned an error event");
    }
    if (payload.type !== "chat:completion") continue;
    const chunk = payload.data;
    if (
      !chunk || typeof chunk !== "object" ||
      (chunk.scope ?? "legacy") !== "legacy"
    ) continue;
    if (chunk.error) throw new Error("Z.ai completion contains an error");
    if (
      !["analysis", "thinking", "reasoning", "tool_call", "tool_response"]
        .includes(chunk.phase ?? "other")
    ) {
      if (typeof chunk.content === "string") content = chunk.content;
      else if (
        typeof chunk.edit_content === "string" &&
        Number.isInteger(chunk.edit_index) && chunk.edit_index >= 0 &&
        chunk.edit_index <= content.length
      ) content = content.slice(0, chunk.edit_index) + chunk.edit_content;
      else if (typeof chunk.delta_content === "string") {
        content += chunk.delta_content;
      }
    }
    if (chunk.done === true) finished = true;
  }
  return finished && content.trim() ? content.trim() : null;
}
export function threadIdFromUrl(value) {
  const u = new URL(value);
  if (u.hostname !== "chat.z.ai" || !u.pathname.startsWith("/c/")) return null;
  return decodeURIComponent(u.pathname.slice(3).split("/")[0]) || null;
}
export function targetUrl(id = null) {
  return id === null ? BASE_URL : BASE_URL + "c/" + encodeURIComponent(id);
}
const pageState = (h) =>
  h.js(
    `(()=>{const c=document.querySelector(${
      JSON.stringify(COMPOSER)
    });return{composer:!!c,text:c?.value||'',attachmentCount:[...document.querySelectorAll('input[type=file]')].reduce((n,x)=>n+(x.files?.length||0),0)}})()`,
  );
const countMessage = (h, message) =>
  h.js(
    `(()=>{const m=${
      JSON.stringify(message)
    };return[...document.querySelectorAll('.user-message')].filter(e=>{const t=e.innerText.trim();return t===m||(t.startsWith(m)&&/^\\s*Show full message\\s*$/.test(t.slice(m.length))) }).length})()`,
  );
function answerResult(receipt, cfg, answer) {
  const r = {
    ...receipt,
    status: "completed",
    answer,
    verified_by: "Z.ai webpage SSE chat:completion done=true",
  };
  if (cfg.response_format === "json") {
    try {
      r.data = JSON.parse(answer.trim());
    } catch (e) {
      r.data = null;
      r.parse_error = e.message;
    }
  }
  return r;
}
async function streamResult(h, baseline) {
  if (typeof h.cdp !== "function") return null;
  const state = await h.js(STREAM_STATE);
  if (state.count <= baseline || !state.latest) return null;
  const e = state.latest;
  if (["read_error", "oversized"].includes(e.state)) {
    throw new Error("Z.ai webpage stream observer failed: " + e.error);
  }
  if (e.status !== 200) throw new Error("Z.ai completion HTTP " + e.status);
  if (e.state === "reading") return { state: "pending" };
  if (e.state === "received") {
    const answer = parseSiteStream(await h.js(STREAM_BODY));
    return answer ? { state: "completed", answer } : { state: "incomplete" };
  }
  return { state: "pending" };
}
async function waitForAnswer(h, receipt, cfg, deadline, baseline) {
  while (Date.now() < deadline) {
    const id = threadIdFromUrl((await h.page_info()).url);
    if (id && (!receipt.thread_id || receipt.thread_id === id)) {
      receipt.thread_id = id;
      receipt.thread_url = targetUrl(id);
    }
    const seen = await streamResult(h, baseline);
    if (seen?.state === "completed" && receipt.thread_id) {
      return answerResult(receipt, cfg, seen.answer);
    }
    await sleep(200);
  }
  return {
    ...receipt,
    status: "pending",
    next_step: "resume=true in the SAME browser session; never resubmit",
  };
}
export async function run(cfg, mode, h) {
  const timeout = Number(cfg.timeout_seconds ?? 120);
  if (!Number.isFinite(timeout) || timeout < 1 || timeout > 600) {
    throw new TypeError("timeout_seconds must be between 1 and 600");
  }
  if (!["text", "json"].includes(cfg.response_format ?? "text")) {
    throw new TypeError("response_format must be text or json");
  }
  const deadline = Date.now() + timeout * 1000;
  if (cfg.resume) {
    const id = threadIdFromUrl((await h.page_info()).url);
    if (cfg.thread_id && cfg.thread_id !== id) {
      throw new Error("Resume requires original live thread; no resubmission");
    }
    const receipt = {
      status: "submitted",
      mode,
      project_id: null,
      thread_id: id,
      thread_url: id ? targetUrl(id) : null,
      source_thread_id: cfg.source_thread_id,
      user_message_id: null,
    };
    const marker = typeof h.cdp === "function"
      ? await h.js(
        `(()=>{const o=window.__webhelmZStream;const m=o?.submission;const last=[...document.querySelectorAll('.user-message')].at(-1)?.innerText.trim()||'';return m&&{baseline:m.baseline,valid:last.startsWith(m.message),currentCount:o.entries.length}})()`,
      )
      : null;
    if (!marker?.valid || marker.currentCount <= marker.baseline) {
      return {
        ...receipt,
        status: "pending",
        next_step: "No matching previous submission in this tab; do not resend",
      };
    }
    return waitForAnswer(h, receipt, cfg, deadline, marker.baseline);
  }
  if (typeof cfg.message !== "string" || !cfg.message.trim()) {
    throw new TypeError("message is required and must be nonempty");
  }
  const message = cfg.message.trim();
  if (cfg.project_id || cfg.temporary || (cfg.mode ?? "chat") !== "chat") {
    throw new TypeError("Z.ai lifecycle actions support ordinary chat only");
  }
  let expected = null;
  if (mode === "new-turn") {
    const candidate = String(cfg.thread_id ?? "").trim();
    if (!candidate || threadIdFromUrl(targetUrl(candidate)) !== candidate) {
      throw new TypeError("thread_id must be a single URL path segment");
    }
    expected = candidate;
  } else if (mode !== "new-thread") {
    throw new TypeError("mode must be new-thread or new-turn");
  }
  if (new URL((await h.page_info()).url).hostname === "chat.z.ai") {
    const s = await pageState(h);
    if (s.text.trim() || s.attachmentCount) {
      throw new Error("Unsent draft or attachment; leave it untouched");
    }
  }
  if (typeof h.cdp === "function") {
    await h.cdp("Page.addScriptToEvaluateOnNewDocument", {
      source: STREAM_OBSERVER,
    });
  }
  await h.goto_url(targetUrl(expected));
  await h.wait_for_load();
  await h.wait_for_element(COMPOSER, { timeout: 15, visible: true });
  if (typeof h.cdp === "function") await h.js(STREAM_OBSERVER);
  const beforeState = await pageState(h);
  if (beforeState.text.trim() || beforeState.attachmentCount) {
    throw new Error("Unsent draft or attachment; leave it untouched");
  }
  const current = threadIdFromUrl((await h.page_info()).url);
  if (
    (mode === "new-turn" && current !== expected) ||
    (mode === "new-thread" && current)
  ) throw new Error("Z.ai thread mismatch; nothing was submitted");
  const before = await countMessage(h, message),
    baseline = typeof h.cdp === "function"
      ? (await h.js(STREAM_STATE)).count
      : 0;
  if (typeof h.cdp === "function") {
    await h.js(
      `(()=>{const o=window.__webhelmZStream;if(o)o.submission={baseline:${baseline},message:${
        JSON.stringify(message)
      }}})()`,
    );
  }
  await h.click(COMPOSER);
  if (typeof h.cdp === "function") {
    await h.cdp("Input.insertText", { text: message });
  } else await h.fill_input(COMPOSER, message);
  await h.wait_for_element(`${SEND_BUTTON}:not(:disabled)`, {
    timeout: 15,
    visible: true,
  });
  await h.click(SEND_BUTTON);
  const receipt = {
    status: "submitted",
    mode,
    project_id: null,
    thread_id: null,
    thread_url: null,
    source_thread_id: mode === "new-thread" ? cfg.source_thread_id : null,
    user_message_id: null,
  };
  while (Date.now() < deadline) {
    const id = threadIdFromUrl((await h.page_info()).url),
      state = await pageState(h),
      accepted = await countMessage(h, message) > before,
      seen = await streamResult(h, baseline);
    if (id && expected && id !== expected) {
      throw new Error("Z.ai unexpected thread after submission");
    }
    if (id && accepted && !state.text) {
      receipt.thread_id = id;
      receipt.thread_url = targetUrl(id);
      receipt.verified_by =
        "matching user message + cleared composer + durable thread URL";
      if (cfg.wait === false) return receipt;
      if (seen?.state === "completed") {
        return answerResult(receipt, cfg, seen.answer);
      }
      return waitForAnswer(h, receipt, cfg, deadline, baseline);
    }
    await sleep(200);
  }
  return {
    ...receipt,
    status: "pending",
    next_step:
      "Submission might have succeeded; resume in same session, never resend",
  };
}
