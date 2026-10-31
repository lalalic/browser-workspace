import test from "node:test";
import assert from "node:assert/strict";
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";
import { run as newTurn } from "../actions/_new_turn.mjs";
import { targetUrl } from "../runtime/lifecycle-common.mjs";
const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");

test("manifest maps every ChatGPT action to an existing native .mjs module", () => {
  const manifest = readFileSync(join(root, "manifest.yaml"), "utf8");
  const body = manifest.split("actions:\n")[1].split("\nverification:")[0];
  const entries = [...body.matchAll(/^\s{2}[\w-]+:\s+"([^"]+)"/gm)].map((m) =>
    m[1]
  );
  assert.equal(entries.length, 9);
  for (const file of entries) {
    assert.match(file, /\.mjs$/);
    assert.ok(existsSync(join(root, file)), file);
  }
  assert.doesNotMatch(body, /\.py/);
  assert.match(manifest, /^status: migrated_unverified$/m);
  assert.match(manifest, /^  status: migrated_unverified$/m);
});

test("all ChatGPT JavaScript modules pass node syntax validation", () => {
  for (const folder of ["actions", "runtime"]) {
    for (
      const name of readdirSync(join(root, folder)).filter((x) =>
        x.endsWith(".mjs")
      )
    ) {
      const file = join(root, folder, name),
        r = spawnSync(process.execPath, ["--check", file], {
          encoding: "utf8",
        });
      assert.equal(r.status, 0, `${file}: ${r.stderr}`);
    }
  }
});

test("target routing preserves project/thread/temporary URL mapping", () => {
  assert.equal(
    targetUrl({ prompt: "probe" }),
    "https://chatgpt.com/?prompt=probe",
  );
  assert.equal(
    targetUrl({ project_id: "p", prompt: "probe" }),
    "https://chatgpt.com/g/p/project?prompt=probe",
  );
  assert.equal(
    targetUrl({ thread_id: "t", prompt: "probe" }),
    "https://chatgpt.com/c/t?prompt=probe",
  );
  assert.equal(
    targetUrl({ project_id: "p", thread_id: "t", prompt: "probe" }),
    "https://chatgpt.com/g/p/c/t?prompt=probe",
  );
  assert.equal(
    targetUrl({ temporary: true, prompt: "probe" }),
    "https://chatgpt.com/?temporary-chat=true&prompt=probe",
  );
  assert.throws(
    () => targetUrl({ temporary: true, thread_id: "t" }),
    /cannot be combined/,
  );
});

test("new-turn async queues by default and validates exact mode strings", async () => {
  let request;
  const helpers = {
    enqueueChatGPTTurn: async (value) => (request = value, {
      ok: true,
      status: "queued",
      queue_id: "q1",
      thread_id: value.thread_id,
      state: "QUEUED",
    }),
  };
  const result = await newTurn({
    helpers,
    config: {
      project_id: "p",
      thread_id: "t",
      message: "hello",
      idempotency_key: "key",
      mergeable: true,
    },
  });
  assert.equal(result.queue_id, "q1");
  assert.deepEqual(request, {
    thread_id: "t",
    project_id: "p",
    message: "hello",
    idempotency_key: "key",
    mergeable: true,
  });
  for (const mode of [true, "ASYNC", "Sync", "", 1]) {
    await assert.rejects(
      () =>
        newTurn({ helpers, config: { mode, thread_id: "t", message: "x" } }),
      /mode must be exactly/,
    );
  }
  await assert.rejects(
    () =>
      newTurn({
        helpers,
        config: { sync: true, thread_id: "t", message: "x" },
      }),
    /mode must be exactly/,
  );
});

test("new-turn sync mode uses caller Session and returns verified receipt", async () => {
  const { SEND_ENABLED_JS, CLICK_SEND_JS } = await import(
    "../runtime/lifecycle-common.mjs"
  );
  let enabled = true, clicked = 0, nav = "";
  const url = targetUrl({ project_id: "p", thread_id: "t", prompt: "hello" });
  const helpers = {
    goto_url: async (value) => {
      nav = value;
    },
    wait_for_load: async () => {},
    page_info: async () => ({ url }),
    js: async (source) => {
      if (source === SEND_ENABLED_JS) return enabled;
      if (source === CLICK_SEND_JS) {
        clicked++;
        enabled = false;
        return true;
      }
      if (source.includes("could not load this chatgpt conversation")) {
        return null;
      }
      return false;
    },
  };
  const result = await newTurn({
    helpers,
    config: { mode: "sync", project_id: "p", thread_id: "t", message: "hello" },
  });
  assert.equal(nav, url);
  assert.equal(clicked, 1);
  assert.equal(result.status, "submitted");
  assert.equal(result.verified_by, "send-button-disabled");
});

test("delivery failures normalize to stable public error codes", async () => {
  const { classify } = await import("../runtime/chatgpt-delivery-errors.mjs");
  assert.deepEqual(
    classify("ChatGPT visible delivery error: conversation_too_long"),
    {
      ok: false,
      code: "conversation_too_long",
      message: "Conversation is too long to continue",
    },
  );
  assert.equal(
    classify("Log in to ChatGPT")["code"],
    "authentication_required",
  );
  assert.equal(
    classify("unclassified private failure")["code"],
    "delivery_failed",
  );
});

test("generic submission receipts require a matching user turn; Temporary Chat opts into cleared-composer evidence", async () => {
  const { submissionReceipt } = await import("../runtime/readiness.mjs");
  assert.equal(submissionReceipt([], 0, "sent", ""), null);
  assert.equal(
    submissionReceipt([], 0, "sent", "", { allowComposerCleared: true })
      .verified_by,
    "composer-cleared",
  );
  assert.equal(
    submissionReceipt([{ text: "sent", id: "u1" }], 0, "sent", "").turn.id,
    "u1",
  );
});

test('read-only ChatGPT validate waits for hydrated composer instead of early false', async () => {
  const { run } = await import('../actions/_validate.mjs');
  let stateCalls=0;
  const helpers={
    goto_url:async()=>{},wait_for_load:async()=>{},
    js:async code => {
      if(code.includes('log in to chatgpt') && !code.includes('BrowserWorkspaceValidateProbe20261020'))return false;
      if(code.includes('BrowserWorkspaceValidateProbe20261020'))return {ready:++stateCalls>=3,login:false};
      return null;
    },
  };
  assert.equal(await run({helpers}),true);
  assert.equal(stateCalls,3);
});
