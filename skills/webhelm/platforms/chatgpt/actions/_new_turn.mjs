import {
  prefilledSubmit,
  requireNoDeliveryError,
  targetUrl,
} from "./_action-common.mjs";
export async function run({ helpers, config = {} }) {
  const mode = config.mode === undefined ? "async" : config.mode;
  if (
    typeof mode !== "string" || !["async", "sync"].includes(mode) ||
    Object.prototype.hasOwnProperty.call(config, "sync")
  ) {
    throw new TypeError(
      "mode must be exactly async or sync; legacy sync is not supported",
    );
  }
  const project_id = String(config.project_id || "").trim() || null,
    thread_id = String(config.thread_id || "").trim(),
    message = String(config.message || "").trim();
  if (!thread_id) throw new Error("thread_id is required");
  if (!message) throw new Error("message is required");
  if (mode === "async") {
    let enqueue;
    if (typeof helpers.enqueueChatGPTTurn === "function") {
      enqueue = (request) => helpers.enqueueChatGPTTurn(request);
    } else if (typeof helpers.chatgptQueue?.enqueue === "function") {
      enqueue = (request) => helpers.chatgptQueue.enqueue(request);
    }
    if (!enqueue) {
      throw new Error(
        "async new-turn requires the daemon ChatGPT queue integration",
      );
    }
    return await enqueue({
      thread_id,
      project_id,
      message,
      idempotency_key: config.idempotency_key || config.idempotencyKey,
      mergeable: config.mergeable === undefined ? false : config.mergeable,
    });
  }
  const { goto_url, wait_for_load, page_info } = helpers;
  const url = targetUrl({ project_id, thread_id, prompt: message });
  await goto_url(url);
  await wait_for_load();
  await requireNoDeliveryError(helpers);
  if (
    new URL((await page_info()).url).pathname.replace(/\/$/, "") !==
      new URL(url).pathname.replace(/\/$/, "")
  ) throw new Error("ChatGPT thread redirect mismatch");
  await requireNoDeliveryError(helpers);
  const receipt = await prefilledSubmit(helpers, message);
  return {
    status: "submitted",
    mode: "new-turn",
    project_id,
    thread_id,
    thread_url: url.split("?")[0],
    verified_by: receipt.verified_by,
    user_message_id: receipt.turn?.id || null,
  };
}
