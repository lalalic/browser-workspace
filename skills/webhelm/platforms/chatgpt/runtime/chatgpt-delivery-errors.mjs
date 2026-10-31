import { appendFile, mkdir } from "node:fs/promises";
import { dirname, join } from "node:path";
import { homedir } from "node:os";
import { randomUUID } from "node:crypto";
const patterns = [
  [
    "conversation_too_long",
    /conversation_too_long|conversation is too long to continue|conversation too long/i,
  ],
  [
    "thread_load_failed",
    /thread_load_failed|could not load this chatgpt conversation|failed to load conversation/i,
  ],
  [
    "authentication_required",
    /login required|log in to chatgpt|session expired|sign in to chatgpt/i,
  ],
  ["rate_limited", /rate.limit|too many requests|http 429|usage limit/i],
  [
    "invalid_thread_id",
    /invalid thread.id|thread.id is required|malformed thread/i,
  ],
  ["thread_redirect_mismatch", /thread redirect mismatch/i],
  [
    "conversation_busy",
    /conversation is busy|turn completion.*not observed ready/i,
  ],
  [
    "send_not_ready",
    /lifecycle continuation readiness was not observed ready|send button.*disabled/i,
  ],
  ["composer_not_found", /composer.*not observed ready|composer.*not found/i],
  ["composer_input_failed", /composer rejected|input failed|prompt.*mismatch/i],
  ["send_click_failed", /send button changed before|send button.*click/i],
  [
    "submission_unverified",
    /submission.*not observed|post.submit.*unverified|cleared composer/i,
  ],
  ["thread_creation_failed", /did not assign a durable thread id/i],
  ["project_not_found", /project not found/i],
  ["project_access_denied", /project.*access denied|permission.*project/i],
  ["attachment_failed", /attachment.*failed|upload.*failed/i],
  [
    "attachment_processing_timeout",
    /attachment.*timeout|attachment.*not observed ready/i,
  ],
  ["session_unavailable", /unknown session|session not found|session.*closed/i],
  [
    "browser_unavailable",
    /chrome.*unavailable|cdp.*disconnect|daemon.*unreachable/i,
  ],
  ["execution_timeout", /timed out|timeout|runtime.evaluate/i],
];
export function classify(error) {
  const raw = String(error || "");
  const code = patterns.find(([, re]) => re.test(raw))?.[0] ||
    "delivery_failed";
  const messages = {
    send_not_ready: "Prompt entered, but Send button did not become ready",
    thread_load_failed: "ChatGPT conversation could not be loaded",
    conversation_too_long: "Conversation is too long to continue",
    submission_unverified: "Submission could not be confirmed",
  };
  return {
    ok: false,
    code,
    message: messages[code] ||
      code.replaceAll("_", " ").replace(/^./, (c) => c.toUpperCase()),
  };
}
export async function normalizeFailure(
  result,
  action,
  {
    logPath = join(
      homedir(),
      ".config/browser-workspace/runtime/chatgpt-delivery-errors.jsonl",
    ),
  } = {},
) {
  if (result?.ok !== false) return result;
  const raw = String(result.stderr || result.error || "");
  const diagnostic_id = randomUUID().replaceAll("-", "");
  try {
    await mkdir(dirname(logPath), { recursive: true });
    await appendFile(
      logPath,
      JSON.stringify({ diagnostic_id, action, error: raw }) + "\n",
    );
  } catch {}
  const normalized = classify(raw);
  if ("cleanup" in result) normalized.cleanup = result.cleanup;
  return normalized;
}
