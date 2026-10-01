import { readdir, readFile, stat } from "node:fs/promises";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const platformsDir = new URL("../platforms/", import.meta.url);
const entries = await readdir(platformsDir, { withFileTypes: true });
const platforms = entries.filter((entry) => entry.isDirectory()).map((entry) => entry.name);

if (platforms.length === 0) throw new Error("No browser platforms found");

for (const platform of platforms) {
  const dir = new URL(`../platforms/${platform}/`, import.meta.url);
  const readmeUrl = new URL("README.md", dir);
  const manifestUrl = new URL("manifest.yaml", dir);
  const actionsUrl = new URL("actions/", dir);

  for (const target of [readmeUrl, manifestUrl, actionsUrl]) await stat(target);

  const readme = await readFile(readmeUrl, "utf8");
  const manifest = await readFile(manifestUrl, "utf8");
  if (!readme.trim()) throw new Error(`${platform}/README.md is empty`);
  if (!manifest.trim()) throw new Error(`${platform}/manifest.yaml is empty`);

  for (const required of ["platform:", "status:", "last_verified:", "actions:", "verification:"]) {
    if (!manifest.includes(required)) throw new Error(`${platform}/manifest.yaml missing ${required}`);
  }
  if (!/verification:\s*[\s\S]*?status:/m.test(manifest)) {
    throw new Error(`${platform}/manifest.yaml verification.status missing`);
  }
  if (!/verification:\s*[\s\S]*?last_verified:/m.test(manifest)) {
    throw new Error(`${platform}/manifest.yaml verification.last_verified missing`);
  }
  if (!/verification:\s*[\s\S]*?evidence:/m.test(manifest)) {
    throw new Error(`${platform}/manifest.yaml verification.evidence missing`);
  }

  const actionsBlock = manifest.match(/actions:\s*\n([\s\S]*?)(?=^[A-Za-z_][\w-]*:\s*$|^[A-Za-z_][\w-]*:\s*[^\s]|\Z)/m)?.[1] || "";
  const actionPaths = [...actionsBlock.matchAll(/^\s{2}[\w-]+:\s*["']([^"']+)["']\s*$/gm)].map((m) => m[1]);
  if (actionPaths.length === 0) throw new Error(`${platform}/manifest.yaml has no declared actions`);

  for (const relative of actionPaths) {
    const target = new URL(relative, dir);
    await stat(target);
  }

  const actionEntries = await readdir(actionsUrl, { withFileTypes: true });
  for (const entry of actionEntries) {
    if (!entry.isFile() || !entry.name.endsWith(".py")) continue;
    const path = new URL(entry.name, actionsUrl);
    const source = await readFile(path, "utf8");
    const forbidden = [
      "session_client",
      "platform_runner",
      "workspace_set_name",
      "workspace_set_supported",
      "workspace_create(",
      "workspace_resize(",
      "workspace_delete(",
      "BH_WORKSPACE_",
      "browser-workspace session",
      "--workspace",
    ];
    for (const token of forbidden) {
      if (source.includes(token)) {
        throw new Error(`${platform}/actions/${entry.name} violates platform boundary with ${token}`);
      }
    }
  }
}

async function walk(path) {
  for (const entry of await readdir(path, { withFileTypes: true })) {
    const child = join(path, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === "__pycache__") {
        throw new Error(`Generated __pycache__ must not be committed: ${child}`);
      }
      await walk(child);
    } else if (entry.name.endsWith(".pyc")) {
      throw new Error(`Generated .pyc must not be committed: ${child}`);
    }
  }
}

await walk(fileURLToPath(platformsDir));
console.log(`Browser Workspace platforms: ${platforms.length} OK`);
