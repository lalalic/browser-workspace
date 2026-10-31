/** Shared output and timing helpers for injected WebHelm action contexts. */
export const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
export const emit = (value, log = console.log) => log(JSON.stringify(value));
/**
 * Build the persistent action namespace used by VM-based Node runners.
 * Every browser primitive is a direct, awaitable dependency; actions can also
 * import sibling modules and pass this same object without hidden globals.
 */
export function createActionContext(
  { config = {}, helpers = {}, log = console.log } = {},
) {
  const names = [
    "goto_url",
    "wait_for_load",
    "page_info",
    "snapshot",
    "js",
    "cdp",
    "wait_for_element",
    "click",
    "fill_input",
    "new_tab",
    "current_tab",
    "close_tab",
    "capture_screenshot",
    "upload_file",
    "type_text",
    "wait",
  ];
  const context = { config, log, console: { log } };
  for (const name of names) {
    if (typeof helpers[name] === "function") {
      context[name] = (...args) => helpers[name](...args);
    }
  }
  if (typeof context.wait !== "function") {
    context.wait = (seconds) => sleep(seconds * 1_000);
  }
  context.helpers = Object.fromEntries(
    names.filter((name) => typeof context[name] === "function").map((
      name,
    ) => [name, context[name]]),
  );
  return context;
}
export async function until(check, { timeout = 30_000, interval = 250 } = {}) {
  const end = Date.now() + timeout;
  while (Date.now() < end) {
    const value = await check();
    if (value) return value;
    await sleep(interval);
  }
  return null;
}
export function requireValue(value, message) {
  if (!value) throw new Error(message);
  return value;
}
