---
name: webhelm
description: Control the shared visible Chrome through WebHelm's Node.js daemon, persistent JavaScript sessions, and site automation where a Node adapter is available.
---

# WebHelm

WebHelm is one browser skill and one Node.js product. Its target architecture uses one daemon, one visible managed Chrome instance, one CDP WebSocket, and explicit per-target CDP `sessionId`s. The bundled Chrome extension source in `extension/` is canonical and retains its published extension ID. Do not install a second extension identity or start an independent browser-harness process.

## Install and commands

The runtime requires Node.js 22 or newer and uses only Node built-ins. The npm package is `webhelm`; the public executable is `webhelm`. During local development, `bin/webhelm` runs the adjacent Node source. For a standalone skill install it resolves the published npm package through `npx`.

```bash
SKILL_DIR="<absolute directory containing this SKILL.md>"
sh "$SKILL_DIR/scripts/install-global-cli.sh"
webhelm status
webhelm session start --url https://example.com
```

The supported command surface is `status`, `session start|list|exec|stop`, and `platform list|profile|run`. Use JavaScript for `session exec`; scripts can come from stdin or `--code-file`:

```bash
webhelm session exec SESSION_ID <<'JS'
console.log(await page_info());
console.log(await snapshot());
JS
```

A JavaScript session persists simple declared bindings between exec calls. Helpers are available directly and through `helpers`: `snapshot`, `js`, `cdp`, `goto_url`, `current_tab`, `new_tab`, `close_tab`, `page_info`, `wait_for_load`, `wait_for_element`, `fill_input`, `click`, `capture_screenshot`, and workspace CRUD helpers. Use `snapshot()` for compact accessibility-oriented refs, then address elements with CSS selectors such as `[data-ref="e2"]`. Batch independent observations/actions in one exec when useful. `js(expression, target_id)` can explicitly inspect a target owned by the session; normal helpers use its current target.

Every workflow follows `session start -> session exec -> ... -> session stop`. Each session owns its root tab, tabs created through `new_tab()`, and detected opener popups. Stop closes those tabs and leaves unrelated Chrome tabs open. Independent sessions use their own CDP attachment and may execute concurrently; a long wait in one session must not block another. Never use raw `Target.createTarget`; use `new_tab(url)` so ownership is tracked.

## Chrome and pilot isolation

The daemon attaches to the existing visible WebHelm Chrome endpoint and keeps the profile at `~/.config/browser-workspace/chrome`. It does not create a second Chrome profile or launch an independent browser. `WEBHELM_CDP_URL` may point at an already-running Chrome endpoint. For a development pilot, set `WEBHELM_RUNTIME_DIR` and `WEBHELM_SOCKET` to isolated paths; the browser profile remains the same managed profile. Do not stop, replace, or migrate a live Python deployment during a pilot.

The session daemon starts lazily and uses a singleton owner lock. If the socket is unreachable while its owner is alive, it refuses duplicate startup. On daemon shutdown, only session-owned tabs are closed. A daemon restart does not recover JavaScript VM namespaces; sessions must be recreated.

The extension remains optional for basic browser control. Workspace CRUD uses its service-worker RPC over the same CDP connection when the published extension is installed. Workspace leasing/grouping is not yet implemented by the Node pilot; the pilot reports this migration gap rather than claiming that tabs are grouped.

## Platform support status

Platform actions are executable only when they have a Node implementation and are explicitly enabled in the Node platform manifest. The current source tree contains Python actions. The Node pilot therefore reports those actions as disabled and `platform run` rejects them; do not treat the Python manifests as evidence that a Node action is available. Keep using the pre-existing Python deployment for platform workflows until their migrations have landed.

The ChatGPT durable asynchronous FIFO, idempotency, queue restore, sync mode, thread/project state, and verified return semantics still require a Node migration and regression coverage. No ChatGPT lifecycle action is enabled by this pilot. Other site actions (ChatGPT, Z.ai, DeepSeek, XHS, CapCut, TikTok, YouTube, WeChat Channels, Teams, Chrome Web Store, and IYF) are likewise migration blockers unless implemented and enabled in a future release.

## Product workspace API

Products such as NeoY and Relay should discover the helper path from `webhelm status`, then import `ensureWorkspace(name, size)` and `deleteWorkspace(name, options)` from the returned `admin_helper`. These APIs use the same WebHelm socket and extension RPC. Workspace lifecycle is not an agent CLI command.

## Extension installation

Keep using the published extension ID `kkkpgmhpoeceojalkpfdidffdfnlgdog` and the existing Chrome Web Store listing or the bundled offline installation path. The offline copy is prepared by:

```bash
sh "$SKILL_DIR/scripts/prepare-local-extension.sh"
```

This prepares files only; approve extension installation in the managed Chrome profile. Never silently load it or modify the default Chrome profile.

## Development and release

Run the Node tests with `npm test` (or `node --test`). The Node daemon is launched lazily by `webhelm`. The npm package contains the Node runtime and skill platform manifests; npm is the release path for the Node CLI. Do not publish a Python wheel for the Node runtime. The legacy Python deployment and PyPI metadata remain present only as migration inputs until platform and queue parity are complete; they are not part of the Node pilot runtime.
