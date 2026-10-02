# Browser Workspace

Browser Workspace is a single browser automation skill and CLI built around persistent Python sessions, workspace-owned Chrome tabs, compact snapshot refs, and built-in platform workflows.

## Public interface

The CLI has two public execution paths:

```bash
# Known platform action: runner owns start/stop.
browser-workspace platform run PLATFORM ACTION [--config FILE] [--url URL]

# Custom browser workflow: caller owns lifecycle.
browser-workspace session start [--url URL]
browser-workspace session exec SESSION_ID <<'PY'
print(snapshot())
PY
browser-workspace session stop SESSION_ID
```

`--workspace` is hidden from normal CLI help. Normal sessions use `Harness`; product integrations may set an explicit workspace internally when they require isolation.

`session stop` closes all tabs created/owned by that session while leaving unrelated browser tabs untouched.

## Included layers

```text
browser-workspace
├── src/browser_harness/     low-level browser/CDP runtime (forked internally)
├── agent-workspace/         Browser Workspace helper layer
├── extension/               Chrome workspace/tab manager
├── session_daemon.py        persistent Python session service
├── platforms/               site/domain actions + verification metadata
├── interaction-skills/      browser interaction references
└── SKILL.md                 single agent-facing skill contract
```

Agents should load only the Browser Workspace skill. `browser-harness` and `browser-platforms` are no longer separate runtime/skill dependencies.

## Install

```bash
./scripts/install.sh
```

The installer creates the skill-owned `.venv` and links `browser-workspace` to `~/.local/bin` by default.

The Chrome extension is optional. When absent, sessions continue in plain-browser mode and `session start` returns a soft warning plus the Web Store URL. Workspace grouping/leases require the extension.

Web Store: `https://chromewebstore.google.com/detail/kgbghhigmbpefppgkocgjgnnnbhjchic`

For development, `extension/` can also be loaded unpacked.

## Snapshot model

`snapshot()` uses Chrome's accessibility tree to identify useful controls/content, annotates the corresponding live DOM elements with `data-ref="eN"`, and emits a compact representation. Interact using normal CSS selectors:

```python
print(snapshot())
click('[data-ref="e2"]')
fill_input('[data-ref="e3"]', 'hello')
```

There is no separate ref registry.

## Upstream

The internal browser-control core is forked from `browser-use/browser-harness`. Its license is retained in `licenses/browser-harness-MIT.txt`.



## Product-owned workspaces

Normal browser automation uses the default `Harness` workspace. Products that need isolated browser capacity—such as Agents Relay or Family Tutor—may explicitly configure and use their own workspace.

These integration commands are intentionally **hidden from normal agent help**. They are for product/runtime code, not for ordinary browsing decisions.

### Create or configure a workspace

```bash
browser-workspace workspace create <name> [--size N]
browser-workspace workspace delete <name> [--force]
```

Examples:

```bash
browser-workspace workspace create "Agents Relay"
browser-workspace workspace create "Agents Relay" --size 6
browser-workspace workspace delete "Agents Relay"
```

`create` is idempotent:

- if the workspace does not exist, it is created;
- if it already exists with the same size, it is kept;
- if it already exists with a different size, its capacity is updated.

The size is the maximum concurrent workspace lease capacity. The physical tab pool grows lazily up to that limit; configuring size `6` does not eagerly create six tabs.

The command returns JSON suitable for Node.js or other product runtimes:

```json
{
  "name": "Agents Relay",
  "poolSize": 6,
  "maxCapacity": 6,
  "initialized": true,
  "workspace_supported": true
}
```

A Node.js service can run this during startup, for example:

```js
execFileSync(browserWorkspaceCli, ["workspace", "create", "Agents Relay", "--size", "6"]);
```

### Start a session in a product-owned workspace

```bash
browser-workspace session start --workspace <name> [--url URL]
```

Example:

```bash
browser-workspace session start --workspace "Agents Relay" --url https://example.com
```

`--workspace` is also intentionally hidden from normal CLI help. Product code owns the workspace choice; platform actions remain unaware of workspace/session policy.

Recommended product lifecycle:

```text
product startup
  -> browser-workspace workspace create "Agents Relay" --size 6

browser task
  -> browser-workspace session start --workspace "Agents Relay"
  -> browser-workspace session exec <session_id>
  -> browser-workspace session stop <session_id>
```

## Platform boundary

Platform action code is infrastructure-agnostic. It may use browser helpers, but it must not create/stop Browser Workspace sessions, choose workspaces, or import session/workspace infrastructure. The generic platform runner wraps actions in a default Harness session and always cleans up. Product code may execute the same action in a product-owned browser context when longer-lived isolation is required.

Each platform manifest records explicit verification status and evidence. `verified` means live-site verification; migrated code is labeled `migrated_unverified` until exercised in the current integration.


## npx skills installation

After `npx skills add ...`, invoke `~/.agents/skills/browser-workspace/bin/browser-workspace` directly. The first session start bootstraps the skill-owned Python virtual environment automatically; running `scripts/install.sh` is optional.
