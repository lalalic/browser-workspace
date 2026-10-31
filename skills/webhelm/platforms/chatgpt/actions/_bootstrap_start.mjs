import { sleep, waitUntilStable } from "../runtime/readiness.mjs";
import { COMPOSER_JS, pathThreadId, setField } from "./_action-common.mjs";
export async function run({ helpers: h, config: c = {} }) {
  if (!String(c.instructions || "").trim()) {
    throw new Error("instructions are required");
  }
  const target_id = await h.new_tab("https://chatgpt.com/");
  await h.wait_for_load();
  const selector = await waitUntilStable(() => h.js(COMPOSER_JS), Boolean, {
    timeout: 45,
    phase: "ChatGPT bootstrap composer",
    sleep,
  });
  await setField(h, selector, String(c.instructions || ""));
  const button = await waitUntilStable(
    () =>
      h.js(
        `(() => {const b=document.querySelector('button[data-testid="send-button"],button[aria-label="Send prompt"],button[aria-label="Send"],form button[type="submit"]');if(!b||b.disabled||b.getAttribute('aria-disabled')==='true')return null;b.setAttribute('data-neoy-bootstrap-send','1');return '[data-neoy-bootstrap-send="1"]';})()`,
      ),
    Boolean,
    { timeout: 20, phase: "ChatGPT bootstrap send button", sleep },
  );
  if (
    !await h.js(
      `(() => {const b=document.querySelector('[data-neoy-bootstrap-send="1"]');if(!b)return false;b.click();return true;})()`,
    )
  ) throw new Error("bootstrap send failed");
  const end = Date.now() + 90000;
  let url = "";
  while (Date.now() < end) {
    url = (await h.page_info()).url || "";
    if (pathThreadId(url) && !url.includes("local-chatgpt")) break;
    await sleep(250);
  }
  if (!pathThreadId(url) || url.includes("local-chatgpt")) {
    throw new Error("bootstrap thread durable URL not observed");
  }
  return { status: "started", thread_url: url.split("?")[0], target_id };
}
