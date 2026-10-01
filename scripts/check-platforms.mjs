import { readdir, readFile, stat } from "node:fs/promises";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const root = new URL("../", import.meta.url);
const platformsDir = new URL("../platforms/", import.meta.url);

const entries = await readdir(platformsDir, { withFileTypes: true });
const platforms = entries.filter((entry) => entry.isDirectory()).map((entry) => entry.name);

if (platforms.length === 0) {
  throw new Error("No browser platforms found");
}

for (const platform of platforms) {
  const dir = new URL(`../platforms/${platform}/`, import.meta.url);
  for (const file of ["SKILL.md", "manifest.yaml"]) {
    const target = new URL(file, dir);
    await stat(target);
    const text = await readFile(target, "utf8");
    if (!text.trim()) throw new Error(`${platform}/${file} is empty`);
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

await walk(fileURLToPath(new URL("../platforms/", import.meta.url)));
console.log(`browser-platforms: ${platforms.length} platforms OK`);
