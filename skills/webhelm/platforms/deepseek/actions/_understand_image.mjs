import { run } from "./_lifecycle_common.mjs";
export default async function understandImage(
  { config: cfg, helpers, log = console.log },
) {
  if (!cfg.resume) {
    if (!cfg.image) {
      throw new TypeError("image must be an existing absolute local file path");
    }
    const prompt = cfg.prompt ??
      "Describe this image accurately, including visible text and important visual details. Do not guess details you cannot see.";
    if (typeof prompt !== "string" || !prompt.trim()) {
      throw new TypeError("prompt must be a non-empty string");
    }
    cfg = { ...cfg, message: prompt };
  }
  const result = await run({ ...cfg, wait: true }, "new-thread", helpers);
  result.url = result.thread_url;
  if (cfg.screenshot_path) {
    result.screenshot = await helpers.capture_screenshot(cfg.screenshot_path);
  }
  log(JSON.stringify(result));
  return result;
}
