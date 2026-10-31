# WebHelm

WebHelm is migrating to one Node.js daemon, one visible managed Chrome instance, one CDP WebSocket, and explicit CDP session IDs per target. This branch provides an isolated Node pilot for browser sessions. The existing Python deployment remains a migration input and is not replaced by the pilot.

## Pilot status

The Node runtime uses Node.js 22+ built-ins, persistent JavaScript session helpers, per-session event queues, independent concurrent sessions, session-owned tab cleanup, and the canonical extension service-worker RPC. It attaches only to an already-running Chrome endpoint; it does not launch Chrome or create a profile. The managed profile remains `~/.config/browser-workspace/chrome`.

Platform actions are reported as disabled until migrated to Node. ChatGPT’s durable asynchronous FIFO, idempotency, queue restore, sync mode, thread/project state, and verified return semantics are not yet ported. Workspace CRUD can call the extension RPC, but Node session lease/group integration still needs live verification. The Python/PyPI source and deployment files remain in the repository as migration inputs; the npm package excludes Python files and the release workflow now targets npm.

## Pilot install and commands

Node package release name: `webhelm`. The skill’s `bin/webhelm` uses adjacent source in a checkout, or `npx` for a standalone skill installation. The installer manages the global `~/.local/bin/webhelm` link.

```bash
npx skills add lalalic/browser-workspace --skill webhelm
webhelm status
webhelm platform list
```

The public CLI surface is `status`, `session start|list|exec|stop`, and `platform list|profile|run`. Unmigrated platform actions are visible as disabled; `platform run` refuses them.

```bash
webhelm session start --url https://example.com
webhelm session exec SESSION_ID <<'JS'
console.log(await page_info());
console.log(await snapshot());
await click('[data-ref="e2"]');
JS
webhelm session stop SESSION_ID
```

JavaScript helpers include `snapshot`, `js`, `cdp`, `goto_url`, `current_tab`, `new_tab`, `close_tab`, `page_info`, `wait_for_load`, `wait_for_element`, `fill_input`, `click`, `capture_screenshot`, and workspace CRUD/capacity functions. A session’s JS context and simple declared bindings persist between exec calls. Independent sessions use separate CDP attachments and can execute concurrently. Stopping a session closes its owned tabs and leaves unrelated tabs open.

## Isolated pilot

Use an isolated daemon socket/runtime while leaving the live Python daemon and its socket untouched. The browser profile is intentionally shared, so do not start overlapping user workflows during the pilot. This checkout’s `bin/webhelm` resolves the Node source directly.

```bash
export WEBHELM_RUNTIME_DIR=/private/tmp/webhelm-node-pilot
export WEBHELM_SOCKET=/private/tmp/webhelm-node-pilot/session.sock
export WEBHELM_LOCK=/private/tmp/webhelm-node-pilot/session.lock
export WEBHELM_CDP_URL=http://127.0.0.1:9222
./skills/webhelm/bin/webhelm status
```

Use `node --test` for the Node test suite. The current environment did not allow a live CDP connection at port 9222, so this pilot has mock CDP coverage only; do not treat that as real-Chrome verification.

## Extension

`skills/webhelm/extension/` remains the only canonical extension source, with the published ID `kkkpgmhpoeceojalkpfdidffdfnlgdog`. Preserve both the existing Chrome Web Store path and the skill’s offline preparation script. Extension installation requires approval in the managed Chrome profile; no automatic unpacked loading is used.

## Product integrations

After `webhelm status`, callers can import `ensureWorkspace(name, size)` and `deleteWorkspace(name, options)` from the returned `admin_helper`. These product APIs retain their names and use the Node daemon socket. The ordinary CLI does not expose workspace CRUD commands.

## Layout and release

- `src/node-daemon.mjs`, `src/cli.mjs`, and `src/admin.mjs`: Node pilot.
- `skills/webhelm/extension/`: canonical Chrome extension.
- `skills/webhelm/platforms/`: platform manifests and documentation; Python actions remain migration inputs and are disabled in Node.
- `test/node/` and `test/workspace-manager.test.mjs`: Node tests.
- `.github/workflows/npm-publish.yml`: npm release on `npm-v*` tags.
- Legacy Python source, PyPI metadata, and the live Python deployment are not removed by this pilot.
