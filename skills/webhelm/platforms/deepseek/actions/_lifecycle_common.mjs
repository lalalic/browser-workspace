import { sleep } from "../../_action_helpers.mjs";
import { stat } from "node:fs/promises";
const COMPOSER = 'textarea[placeholder="Message DeepSeek"]';
const ANSWER_STATE =
  `(()=>{const answers=[...document.querySelectorAll('.ds-assistant-message-main-content')];const generating=!!document.querySelector('[role=button].ds-button--primary:not(.ds-button--disabled)');const finished=document.querySelectorAll('[aria-label="Read aloud"]').length>=answers.length;return{count:answers.length,answer:answers.at(-1)?.innerText.trim()||'',settled:!generating&&finished}})()`;
function threadId(url) {
  try {
    const u = new URL(url),
      id = u.pathname.startsWith("/a/chat/s/")
        ? u.pathname.slice(10).replace(/\/$/, "")
        : "";
    return u.hostname === "chat.deepseek.com" &&
        /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/
          .test(id)
      ? id
      : null;
  } catch {
    return null;
  }
}
function parseJson(answer) {
  const match = answer.match(/```(?:json)?\s*([\s\S]*?)```/);
  try {
    return { data: JSON.parse(match ? match[1] : answer) };
  } catch (e) {
    return { data: null, parse_error: e.message };
  }
}
async function waitAnswer(h, receipt, cfg, minCount, timeout) {
  const end = Date.now() + timeout * 1000;
  while (Date.now() < end) {
    const s = await h.js(ANSWER_STATE);
    if (s.count > minCount && s.answer && s.settled) {
      const r = { ...receipt, status: "completed", answer: s.answer };
      if (cfg.response_format === "json") Object.assign(r, parseJson(s.answer));
      return r;
    }
    await h.wait(1);
  }
  return {
    ...receipt,
    status: "pending",
    next_step:
      "Keep this session and rerun with resume=true and this thread_id; do not resend",
  };
}
export async function run(cfg, mode, h) {
  const timeout = Number(cfg.timeout_seconds ?? 120);
  if (timeout < 1 || timeout > 600 || !Number.isFinite(timeout)) {
    throw new TypeError("timeout_seconds must be between 1 and 600");
  }
  if (!["text", "json"].includes(cfg.response_format ?? "text")) {
    throw new TypeError("response_format must be text or json");
  }
  if (cfg.project_id || cfg.temporary || (cfg.mode ?? "chat") !== "chat") {
    throw new TypeError(
      "DeepSeek lifecycle actions support ordinary chat only, not Projects or Temporary Chat",
    );
  }
  if (cfg.resume) {
    const id = cfg.thread_id || threadId((await h.page_info()).url);
    if (!id || threadId(`https://chat.deepseek.com/a/chat/s/${id}`) !== id) {
      throw new TypeError(
        "resume needs a canonical thread_id or an open DeepSeek thread",
      );
    }
    const url = `https://chat.deepseek.com/a/chat/s/${id}`;
    if (threadId((await h.page_info()).url) !== id) {
      await h.goto_url(url);
      await h.wait_for_load();
    }
    const minCount = cfg.min_answer_count ?? 0;
    if (!Number.isInteger(minCount) || minCount < 0) {
      throw new TypeError("min_answer_count must be a nonnegative integer");
    }
    return waitAnswer(
      h,
      {
        status: "submitted",
        mode,
        project_id: null,
        thread_id: id,
        thread_url: url,
        source_thread_id: cfg.source_thread_id,
        verified_by: "resumed without resubmitting",
        user_message_id: null,
        answers_before: minCount,
      },
      cfg,
      minCount,
      timeout,
    );
  }
  if (typeof cfg.message !== "string" || !cfg.message.trim()) {
    throw new TypeError("message is required and must be a non-empty string");
  }
  const message = cfg.message.trim();
  let expected = null;
  if (mode === "new-turn") {
    expected = cfg.thread_id;
    if (
      typeof expected !== "string" ||
      threadId(`https://chat.deepseek.com/a/chat/s/${expected}`) !== expected
    ) throw new TypeError("thread_id must be a canonical UUID");
  }
  let image = null;
  if (Object.hasOwn(cfg, "image")) {
    image = String(cfg.image);
    if (!image.startsWith("/")) {
      throw new TypeError("image must be an existing absolute local file path");
    }
    try {
      if (!(await stat(image)).isFile()) throw new Error("not a file");
    } catch {
      throw new TypeError("image must be an existing absolute local file path");
    }
    if (!/\.(png|jpg|jpeg|webp|gif|bmp|tif|tiff|avif)$/i.test(image)) {
      throw new TypeError(
        "Use a PNG, JPEG, WebP, GIF, BMP, TIFF, or AVIF image",
      );
    }
  }
  const idle = async () => {
    await h.wait_for_element(COMPOSER, { timeout: 15, visible: true });
    const end = Date.now() + timeout * 1000;
    while (Date.now() < end) {
      const s = await h.js(
        `(()=>{const c=document.querySelector(${
          JSON.stringify(COMPOSER)
        }),send=document.querySelector('[role="button"].ds-button--primary'),attachments=[...document.querySelectorAll('img[alt]')].some(i=>i.closest('[role=button]')&&!i.closest('.ds-message'));return{draft:!!c?.value||attachments,idle:!!c&&!c.disabled&&!!send&&send.classList.contains('ds-button--disabled')}})()`,
      );
      if (s.draft) {
        throw new Error("Unsent draft or attachment; leave it untouched");
      }
      if (s.idle) return;
      await h.wait(.2);
    }
    throw new Error("DeepSeek is still generating; nothing was submitted");
  };
  if (new URL((await h.page_info()).url).hostname === "chat.deepseek.com") {
    await idle();
  }
  await h.goto_url(
    `https://chat.deepseek.com/${expected ? `a/chat/s/${expected}` : ""}`,
  );
  await h.wait_for_load();
  await idle();
  const current = threadId((await h.page_info()).url);
  if (current !== expected) {
    throw new Error("DeepSeek thread redirect mismatch; nothing was submitted");
  }
  const expression =
      `(()=>[...document.querySelectorAll('.ds-message')].filter(e=>e.innerText.trim()===${
        JSON.stringify(message)
      }).length)()`,
    before = await h.js(expression),
    answersBefore = (await h.js(ANSWER_STATE)).count;
  if (image) {
    const ext = image.match(/\.([^.]+)$/)[1].toLowerCase();
    const accepted =
      (await h.js("document.querySelector('input[type=file]')?.accept||''"))
        .split(",");
    if (!accepted.includes("." + ext)) {
      throw new TypeError(
        "DeepSeek's attachment input does not accept this image extension",
      );
    }
    await h.upload_file('input[type="file"]', image);
  }
  await h.fill_input(COMPOSER, message);
  const primary = '[role="button"].ds-button--primary';
  await h.wait_for_element(primary + ":not(.ds-button--disabled)", {
    timeout: cfg.image ? 60 : 15,
    visible: true,
  });
  if (cfg.image) {
    const name = image.split("/").pop();
    if (
      !(await h.js(
        `(()=>[...document.querySelectorAll('img[alt]')].some(i=>i.alt===${
          JSON.stringify(name)
        }&&i.complete&&i.naturalWidth>0))()`,
      ))
    ) throw new Error("Image preview is not ready; nothing was submitted");
  }
  await h.click(primary + ":not(.ds-button--disabled)");
  // The new-chat SPA may create a durable thread and clear the composer
  // without ever saving a user message. That is NOT a delivery receipt.
  // Do not wait the full model timeout when no accepted user message appears.
  // Return a read-only-resumable PENDING state with the thread identity.
  let tentative = null;
  const end = Date.now() + timeout * 1000;
  const admissionEnd = Date.now() + Math.min(timeout * 1000, 12_000);
  while (Date.now() < end) {
    const id = threadId((await h.page_info()).url);
    const accepted = (await h.js(expression)) > before;
    const cleared = await h.js(
      `document.querySelector(${JSON.stringify(COMPOSER)})?.value===''`,
    );
    if (id && cleared && (!expected || id === expected)) {
      if (!tentative) {
        tentative = {
          status: "submitted",
          mode,
          project_id: null,
          thread_id: id,
          thread_url: `https://chat.deepseek.com/a/chat/s/${id}`,
          source_thread_id: cfg.source_thread_id,
          user_message_id: null,
          answers_before: answersBefore,
        };
      }
      if (accepted) {
        const receipt = {
          ...tentative,
          verified_by: "new matching user message, cleared composer, and durable thread URL",
          submission_verified: true,
        };
        if (cfg.wait === false) return receipt;
        return waitAnswer(h, receipt, cfg, answersBefore, timeout);
      }
      // The assistant might become visible before the user-message selector
      // hydrates. A NEW completed answer in the exact thread is independent
      // evidence of delivery, but an empty thread is not.
      const state = await h.js(ANSWER_STATE);
      if (state.count > answersBefore && state.answer && state.settled) {
        const receipt = {
          ...tentative,
          verified_by: "new settled assistant answer in durable thread",
          submission_verified: true,
        };
        const r = { ...receipt, status: "completed", answer: state.answer };
        if (cfg.response_format === "json") Object.assign(r, parseJson(state.answer));
        return r;
      }
    }
    if (Date.now() >= admissionEnd && tentative) {
      return {
        ...tentative,
        status: "pending",
        submission_verified: false,
        verified_by: "thread URL and cleared composer only; user message not verified",
        next_step:
          "Read-only resume this thread; do not resend the text or image",
      };
    }
    await sleep(200);
  }
  if (tentative) {
    return {
      ...tentative,
      status: "pending",
      submission_verified: false,
      verified_by: "thread URL and cleared composer only; user message not verified",
      next_step: "Read-only resume this thread; do not resend",
    };
  }
  throw new Error(
    "Submission may have succeeded but its receipt was not verified; inspect this session before retrying",
  );
}
