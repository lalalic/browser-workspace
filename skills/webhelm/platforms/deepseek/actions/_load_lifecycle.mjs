import { stat } from "node:fs/promises";
const source = new URL("./_lifecycle_common.mjs", import.meta.url);

// The WebHelm daemon hot-loads action modules by mtime, but Node otherwise
// caches their static dependencies. Resolve the actual shared lifecycle mtime
// per action invocation, without restarting the daemon or other sessions.
export async function currentLifecycle() {
  const file = await stat(source);
  return import(source.href + "?mtime=" + file.mtimeMs);
}
