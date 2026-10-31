---
name: webhelm
description: Control the user's visible managed Chrome through one native Node.js WebHelm runtime, persistent JavaScript sessions, compact semantic Browser Helpers, workspace tab groups, and integrated site-specific actions.
requires:
  skills:
    - daemon-service-manage
---

# WebHelm — unified browser skill

**WebHelm is the only browser Skill.** It owns one Node.js daemon, the existing managed Chrome profile, one CDP WebSocket with explicit per-target CDP session attachments, one session-owned JavaScript execution environment, and the bundled Chrome tab-group extension. Do not load or launch Browser Harness, Browser Workspace, or Python daemon dependencies separately. The Node runtime is bundled in `runtime/` with the Skill; no npm publication or second runtime download is needed.

## Setup and status

Resolve `SKILL_DIR` from the actual installed Skill path; do not assume `~/.agents` or any other agent-specific location.

```sh
SKILL_DIR="<absolute directory containing this SKILL.md>"
sh "$SKILL_DIR/scripts/install-global-cli.sh"
webhelm status
webhelm platform list
webhelm capacity
```

This requires Node.js **22.5 or newer** and npm. Installation installs locked, local JS dependencies, and manages one executable symlink `~/.local/bin/webhelm`. The CLI automatically starts the single Node daemon and adopts the existing Browser Workspace Chrome profile at `~/.config/browser-workspace/chrome`. If that managed Chrome is missing, WebHelm launches it. Do not restart Chrome merely to update the Skill. `webhelm status` includes the canonical `admin_helper` path for product clients. `webhelm capacity` reports the same Harness workspace capacity schema consumed by Relay, without creating a browser Session or spawning another Harness process.

## Sessions (JavaScript)

Always create one Session per logical workflow. Retain its `session_id` across steps; stop it after success, failure, or cancellation. Stop closes/releases only that Session's tabs, including child windows/popups. Never close unrelated tabs. Sessions on separate tabs execute concurrently, with independent JS state and explicit CDP attachments rather than a global browser lock.

```sh
webhelm session start --url https://example.com
webhelm session exec SESSION_ID <<'JS'
console.log(await page_info());
console.log(await snapshot());
await click('[data-ref="e2"]');
JS
webhelm session stop SESSION_ID
```

The commands are `webhelm session start [--url URL]`, `list`, `exec SESSION_ID [--code-file SCRIPT.mjs]`, `stop SESSION_ID` and `stop --all`. The JS runtime keeps variables and functions between calls. Use `console.log` for compact output, and batch steps within one `exec` where appropriate. Do not call `Target.createTarget` directly: use `new_tab(url)` so workspace ownership is tracked.

### Browser Helpers

Helpers are preinstalled into each Session's JS environment (all async unless stated otherwise):

```js
await snapshot();                   // compact roles and [data-ref="eN"] selectors
await page_info();                  // {url,title,readyState}
await goto_url(url);
await wait_for_load();
await wait_for_element(selector, {timeout:10, visible:true}); // seconds; boolean
await click(selector);
await fill_input(selector, text);
await type_text(text);              // CDP Input.insertText
await upload_file(selector, absoluteFilePath);
await js('document.title');         // in-page JavaScript
await cdp('Page.getNavigationHistory');
await capture_screenshot();         // base64 PNG (optionally save to file)
await new_tab(url);
await current_tab();
await list_tabs();
await switch_tab(targetId);         // only tabs owned by this Session
await close_tab();
await wait(1);                      // seconds
await workspace_status();
```

`snapshot()` writes `data-ref` onto live controls, so interact with `[data-ref="e2"]` using the normal CSS helpers. Refresh snapshot after navigation or substantial page changes. Use raw `js()` or `cdp()` when a higher-level helper is insufficient. Never infer tab identity from URL; CDP target attachment is authoritative. Raw CDP tab creation/attachment and closing another Session's tabs are prohibited.

## Platform Actions

Site-specific actions, manifests, and verified flow documentation live under this same Skill's `platforms/`. There are adapters for ChatGPT, Z.ai, DeepSeek, XHS, CapCut, TikTok, YouTube, WeChat Channels, Teams, Chrome Web Store, and IYF. Platform code is JavaScript `.mjs` and receives the same Session's Browser Helpers. The generic agent owns the Session lifecycle; platform code must not create a second daemon or user session.

```sh
webhelm platform profile z
webhelm platform source z new-turn
webhelm session start --url https://chat.z.ai
webhelm platform run z new-turn --session-id SESSION_ID --config /path/to/turn.json
webhelm session stop SESSION_ID
```

Platform actions require `--session-id` by default. `--auto-session` creates a temporary session for a one-off action, but discards the state required for orchestrator self-heal. When a site changes, inspect the same browser Session and write any verified repair into the matching `platforms/<name>/actions/*.mjs` before declaring the workflow complete. Verify external side effects read-only before retrying an ambiguous submission. A migrated action is **not** automatically live-verified; consult the platform manifest and its flow-specific status.

### ChatGPT FIFO delivery

`chatgpt new-turn` defaults to `mode: "async"`: a durable SQLite per-thread FIFO owned by the same Node daemon. It returns `status:submitted` with a queue receipt, **not** proof of delivery. Idempotency and mergeable requests are supported. `mode:"sync"` is an explicit opt-in and requires a caller-owned `--session-id`.

```sh
webhelm platform run chatgpt new-turn --config /path/to/turn.json
webhelm platform run chatgpt new-turn --mode sync --session-id SESSION_ID --config /path/to/turn.json
```

Use exact strings `async` or `sync`; legacy boolean `sync` is invalid. An ambiguous send becomes `UNCERTAIN` and must not be automatically resent. Stop the old dispatch process and preserve `chatgpt-new-turn.sqlite3` before switching runtime versions. During a controlled deployment, `WEBHELM_CHATGPT_QUEUE_PAUSED=1` prevents the new dispatcher from starting while the installed Node daemon is being smoke-tested. Resume by gracefully stopping this paused daemon and starting it without the variable, only after the old dispatcher has fully stopped. No second queue dispatcher may run simultaneously on the same data. Optional Cookie audit and authenticated read-only keepalive scripts in `scripts/` also use Node.js (see `scripts/AUTH_COOKIE_AUDIT.md`).

## Extension / Workspace

The Chrome extension **Browser Workspace** is bundled in `extension/` as the one canonical source (published ID `kkkpgmhpoeceojalkpfdidffdfnlgdog`). It owns visible Chrome Tab Groups, workspace names, leases, and idle tab pools; it is not another OS daemon. For grouping, install from the verified Chrome Web Store listing in managed Chrome, or run `sh "$SKILL_DIR/scripts/prepare-local-extension.sh"` to stage the offline version and approve **Load unpacked** in Chrome. Do not silently install or duplicate the extension. Without it, basic CDP controls still work; grouping and pool leases are unavailable.

Workspace lifecycle is a product-level operation. NeoY/Relay discover `admin_helper` from `webhelm status` and import `ensureWorkspace(name,size)` / `deleteWorkspace(name,{force})`; these use the same Node daemon socket.

## Development / safe deployment

The Skill's single canonical source is `skills/webhelm/`. Run `npm test --prefix "$SKILL_DIR"` in its repository checkout; the tests include Node daemon, queue, platform actions, and the extension. Validate externally against real Chrome before deploying. For an isolated development daemon, use `WEBHELM_RUNTIME_DIR`, `WEBHELM_SOCKET`, `WEBHELM_LOCK`, and optionally `WEBHELM_CDP_URL` to attach to the existing Chrome without touching the production daemon socket. Never restart user-owned browsers, break active sessions, discard pending queue items, or hide incomplete platform live-verification.

Legacy platform callers (NeoY and Relay) receive the machine-readable Action receipt in `result.stdout` as JSON while new callers can read `result.value`. This compatibility does not change the browser Session lifecycle or queued delivery semantics.
