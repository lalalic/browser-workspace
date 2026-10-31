import test from "node:test";
import assert from "node:assert/strict";
import { readdir, readFile } from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { parseSiteStream } from "../z/actions/_lifecycle_common.mjs";

const root = path.resolve("skills/webhelm/platforms");
const platforms = [
  "capcut",
  "z",
  "deepseek",
  "xhs",
  "chrome-web-store",
  "iyf",
  "microsoft-teams",
  "tiktok",
  "wechat-channels",
  "youtube",
];

test("all in-scope manifest actions resolve to importable JavaScript modules", async () => {
  for (const platform of platforms) {
    const manifest = await readFile(
      path.join(root, platform, "manifest.yaml"),
      "utf8",
    );
    const block = manifest.match(/^actions:\n((?:[ \t].*\n)+)/m)?.[1];
    assert.ok(block, `${platform} has an actions mapping`);
    for (
      const [, relative] of block.matchAll(/:\s*["']?(actions\/[^"'\s]+)["']?/g)
    ) {
      assert.match(
        relative,
        /\.mjs$/,
        `${platform}: ${relative} uses JavaScript`,
      );
      const full = path.join(root, platform, relative);
      await readFile(full, "utf8");
      const module = await import(pathToFileURL(full));
      assert.equal(
        typeof module.default,
        "function",
        `${platform}: ${relative} exports an action`,
      );
    }
    const pyFiles = (await readdir(path.join(root, platform, "actions")))
      .filter((x) => x.endsWith(".py"));
    for (const py of pyFiles) {
      assert.ok(
        (await readdir(path.join(root, platform, "actions"))).includes(
          py.replace(/\.py$/, ".mjs"),
        ),
        `${platform}: migration module exists for ${py}`,
      );
    }
  }
});

test("Z completion parser requires a done event and ignores analysis chunks", () => {
  assert.equal(
    parseSiteStream(
      'data: {"type":"chat:completion","data":{"phase":"analysis","content":"hidden","done":true}}',
    ),
    null,
  );
  assert.equal(
    parseSiteStream(
      'data: {"type":"chat:completion","data":{"content":"answer","done":false}}',
    ),
    null,
  );
  assert.equal(
    parseSiteStream(
      'data: {"type":"chat:completion","data":{"content":"answer","done":true}}',
    ),
    "answer",
  );
  assert.throws(() => parseSiteStream('data: {"type":"error"}'), /error event/);
});

test("Z lifecycle action leaves an existing draft untouched", async () => {
  const { default: newThread } = await import("../z/actions/_new_thread.mjs");
  const h = {
    page_info: async () => ({ url: "https://chat.z.ai/" }),
    js: async (expression) =>
      expression.includes("attachmentCount")
        ? { text: "unsent", attachmentCount: 0 }
        : null,
  };
  await assert.rejects(
    newThread({ config: { message: "hello" }, helpers: h, log: () => {} }),
    /Unsent draft or attachment/,
  );
  assert.equal(h.page_info instanceof Function, true);
});

test("CapCut generation requires explicit credit authorization before browser actions", async () => {
  const { default: generate } = await import("../capcut/actions/_generate.mjs");
  let calls = 0;
  const helpers = new Proxy({}, {
    get: () => async () => {
      calls += 1;
    },
  });
  await assert.rejects(
    generate({
      config: {
        prompt: "a harmless prompt",
        media_type: "image",
        model: "model",
      },
      helpers,
      log: () => {},
    }),
    /confirm_generation/,
  );
  assert.equal(calls, 0);
});

test("Chrome Web Store review submission stays blocked without both guards", async () => {
  const { default: action } = await import(
    "../chrome-web-store/actions/_chrome_web_store.mjs"
  );
  let url =
    "https://chrome.google.com/webstore/devconsole/publisher/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/edit";
  const helpers = {
    page_info: async () => ({ url }),
    goto_url: async (next) => {
      url = next;
    },
    wait_for_load: async () => {},
    js: async (expression) => expression.includes("toLowerCase") ? false : "",
  };
  const result = await action({
    config: {
      action: "submit-review",
      item_id: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    },
    helpers,
    log: () => {},
  });
  assert.equal(result.status, "draft");
  assert.equal(result.blocked, "explicit submit authorization required");
});

test("migrated manifests and code do not mark actions live-verified", async () => {
  for (const platform of platforms) {
    const manifest = await readFile(
      path.join(root, platform, "manifest.yaml"),
      "utf8",
    );
    assert.match(manifest, /^status: migrated_unverified$/m, platform);
    const actionsDir = path.join(root, platform, "actions");
    for (const file of await readdir(actionsDir)) {
      if (file.endsWith(".mjs")) {
        const source = await readFile(path.join(actionsDir, file), "utf8");
        assert.doesNotMatch(
          source,
          /(?:^|[{,]\s*)verified\s*:\s*true\s*(?:[,}]|$)/m,
          `${platform}/${file} has no fabricated verified flag`,
        );
      }
    }
  }
});
