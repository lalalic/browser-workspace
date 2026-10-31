import {
  prefilledSubmit,
  requireNoDeliveryError,
  sleep,
  targetUrl,
} from "./_action-common.mjs";
export async function run({ helpers, config = {} }) {
  const { js, goto_url, wait_for_load, page_info } = helpers;
  const project_id = String(config.project_id || "").trim() || null,
    message = String(config.message || "").trim(),
    source_thread_id = String(config.source_thread_id || "").trim() || null,
    temporary = !!config.temporary;
  if (
    ["job_id", "jobId", "task_id", "taskId", "pr_number", "prNumber"].some(
      (k) => k in config,
    )
  ) throw new Error("new-thread does not accept Job/Task/PR context");
  if ((config.mode ?? "chat") !== "chat") {
    throw new Error("new-thread supports chat mode only");
  }
  if (!message) throw new Error("message is required");
  if (temporary && project_id) {
    throw new Error("temporary=true cannot be combined with project_id");
  }
  const url = targetUrl({ project_id, temporary, prompt: message });
  const mode = async () =>
    await js(
      `(() => {const b=[...document.querySelectorAll('button')],f=n=>b.find(x=>(x.textContent||'').trim()===n&&x.hasAttribute('aria-pressed')),c=f('Chat'),w=f('Work');if(!c||!w)return 'unknown';if(c.getAttribute('aria-pressed')==='true'&&w.getAttribute('aria-pressed')==='false')return 'chat';if(w.getAttribute('aria-pressed')==='true'&&c.getAttribute('aria-pressed')==='false')return 'work';return 'unknown';})()`,
    );
  await goto_url(url);
  await wait_for_load();
  await requireNoDeliveryError(helpers);
  if (await mode() === "work") {
    if (
      !await js(
        `(() => {const c=[...document.querySelectorAll('button')].find(b=>(b.textContent||'').trim()==='Chat'&&b.hasAttribute('aria-pressed'));if(!c||c.disabled)return false;c.click();return true;})()`,
      )
    ) throw new Error("Cannot select Chat mode");
    for (let i = 0; i < 30 && await mode() !== "chat"; i++) await sleep(200);
  }
  if (await mode() !== "chat") {
    const tempMode = temporary &&
      await js(
        `(() => {const t=[...document.querySelectorAll('button')].some(b=>(b.getAttribute('aria-label')||'').toLowerCase().includes('turn off temporary chat'));const c=[...document.querySelectorAll('[role="textbox"],textarea')].some(e=>(e.getAttribute('aria-label')||'').trim()==='Ask ChatGPT');return t&&c;})()`,
      );
    if (!tempMode) {
      throw new Error("new-thread Chat mode could not be verified");
    }
  }
  if (!temporary) {
    await goto_url(url);
    await wait_for_load();
  }
  if (
    temporary &&
    !await js(
      `(() => location.search.includes('temporary-chat=true')||[...document.querySelectorAll('button')].some(b=>(b.getAttribute('aria-label')||'').toLowerCase().includes('turn off temporary chat')||(b.textContent||'').trim().toLowerCase()==='turn off temporary chat')||[...document.querySelectorAll('h1')].some(h=>(h.textContent||'').trim().toLowerCase()==='temporary chat'))()`,
    )
  ) throw new Error("ChatGPT Temporary Chat mode was not activated");
  await requireNoDeliveryError(helpers);
  const receipt = await prefilledSubmit(helpers, message);
  if (temporary) {
    return {
      status: "submitted",
      mode: "new-thread",
      temporary: true,
      project_id: null,
      source_thread_id,
      thread_id: null,
      thread_url: null,
      verified_by: receipt.verified_by,
      user_message_id: receipt.turn?.id || null,
    };
  }
  const end = Date.now() + 60000;
  let thread_id = null, thread_url = null;
  while (Date.now() < end) {
    const current = (await page_info()).url.split("?")[0],
      path = new URL(current).pathname.replace(/\/$/, "");
    if (path.includes("/c/") && !current.includes("local-chatgpt")) {
      thread_id = path.split("/").pop();
      thread_url = current;
      if (thread_id) break;
    }
    await sleep(200);
  }
  if (!thread_id) throw new Error("ChatGPT did not assign a durable thread id");
  return {
    status: "submitted",
    mode: "new-thread",
    temporary: false,
    project_id,
    source_thread_id,
    thread_id,
    thread_url,
    verified_by: receipt.verified_by,
    user_message_id: receipt.turn?.id || null,
  };
}
