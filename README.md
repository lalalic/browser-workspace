# WebHelm

Browser Workspace provides the browser runtime and generic CLI. The WebHelm skill and site-specific platform adapters live under `skills/webhelm/` and are distributed separately from the CLI package.

## Public interface

Agents and products invoke only the global `webhelm` command. Install the
WebHelm Skill through any agent's normal Skill mechanism (for example,
`npx skills add lalalic/browser-workspace --skill webhelm`). The Skill may
live in any directory. Its `SKILL.md` tells the agent to run
`scripts/install-global-cli.sh` **relative to that installed Skill**.

The installer points `~/.local/bin/webhelm` to the Skill's launcher, safely
migrates known old links, and refuses to overwrite unrelated user commands.
Ensure `~/.local/bin` is on `PATH`. No agent or product needs to know the
Skill's installation directory, runtime package, or platform directory after
setup. There is no supported `browser-workspace` CLI command.

For a local unreleased CLI build, developers may set
`WEBHELM_CLI_SOURCE=/absolute/path/to/browser-workspace` and
`WEBHELM_CLI_REFRESH=1` when testing a rebuilt wheel with the same version.

The CLI has two public execution paths:

```bash
# Platform action: caller owns the browser session.
webhelm platform run PLATFORM ACTION --session-id SESSION_ID [--config FILE]

# Custom browser workflow: caller owns lifecycle.
webhelm session start [--url URL]
webhelm session exec SESSION_ID <<'PY'
print(snapshot())
PY
webhelm session stop SESSION_ID
```

For ChatGPT lifecycle `new-turn`, async durable-queue delivery is the default
and reports `status: submitted`. Set `"mode": "sync"` in the action config, or
use `--mode sync`, to deliver through a caller-owned `--session-id`; its public
status is also `submitted`. The only accepted mode values are the exact strings
`"async"` and `"sync"`; omitted mode defaults to `"async"`. Other values and the
legacy `sync` config key are rejected (for example, `{"mode": true}` and
`{"sync": true}` are invalid).

`--workspace` is hidden from normal CLI help. Normal sessions use `Harness`; product integrations may set an explicit workspace internally when they require isolation.

`session stop` closes all tabs created/owned by that session while leaving unrelated browser tabs untouched. Raw session CDP cannot create targets: `Target.createTarget` is rejected and callers must use `new_tab()` so workspace/session ownership is preserved.

## Repository layout

```text
browser-workspace
├── src/                         CLI, session daemon, platform runner, managed Chrome (package browser_workspace_app)
│   ├── browser-harness/         helper overlay loaded by browser-harness (BH_AGENT_WORKSPACE)
│   └── admin.mjs                Node API for products to create/delete persistent workspaces
├── extension/                   Chrome workspace/tab manager extension
├── scripts/package-extension.sh extension release zip (used by CI)
├── skills/webhelm/              WebHelm skill: SKILL.md, interaction-skills/, platforms/, scripts/
├── test/                        CLI, daemon, packaging, and extension tests
└── site/                        GitHub Pages (privacy policy)
```

Site-specific code lives only in `skills/webhelm/platforms/<name>/`, including the ChatGPT durable-queue runtime under `platforms/chatgpt/runtime/`. The CLI package ships no platform code. The version is defined once in `src/__init__.py`.

Agents should load only the WebHelm skill. `browser-harness` and `browser-platforms` are no longer separate runtime/skill dependencies.

## Install

```bash
npx skills add lalalic/browser-workspace --skill webhelm
webhelm status
```

The `browser-workspace` PyPI distribution provides the `webhelm` entry point. External callers use the global launcher.

Platform actions are supplied by the installed WebHelm skill, not embedded in
the CLI package. The runner reads the skill-owned directory from
`WEBHELM_PLATFORM_DIR`:

```bash
webhelm platform list
```

By default Browser Workspace owns exactly one machine-wide persistent, visible Chrome instance. Every session and runtime reuses that same Browser Workspace Chrome; config/runtime overrides never create another Chrome. It uses a Browser Workspace-managed user-data directory, prefers CDP port 9222, and selects the next available candidate only when starting the singleton for the first time. Users do not manage Chrome profiles or remote-debugging settings. Chrome Stable no longer permits silent `--load-extension` for local unpacked extensions, so the extension is treated as an optional workspace-grouping enhancement rather than a prerequisite for browser sessions.

`BU_CDP_URL` / `BU_CDP_WS` remain advanced overrides for callers that intentionally provide their own browser endpoint. `BROWSER_WORKSPACE_CDP_PORT` changes the preferred managed port.

The **official Chrome Web Store extension** is the only supported extension for ordinary browser sessions: `https://chromewebstore.google.com/detail/browser-workspace/kkkpgmhpoeceojalkpfdidffdfnlgdog` (extension ID `kkkpgmhpoeceojalkpfdidffdfnlgdog`, published version `0.3.1` as verified on 2026-10-30). Install it interactively in the managed Browser Workspace Chrome, approve Chrome's permission prompt, and verify its exact ID and version. Do not use an unpacked extension or assume an old extension ID is the published one. Without the official extension, the runtime remains in plain-browser mode.

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

Normal browser automation uses the default `Harness` workspace. Ordinary agents manage browser sessions only; they do not create, resize, or delete workspaces. Workspace lifecycle belongs to product runtimes such as Agents Relay or NeoY.

Products discover the installed Browser Workspace instance with:

```bash
webhelm status
```

The command returns machine-readable JSON including the resolved installation `root`, absolute `admin_helper` path, and daemon status. Calling `status` also ensures the existing Browser Workspace session daemon is ready; it does not create a separate service.

A Node.js product can then load the product-only helper without hardcoding an install path:

```js
import { execFileSync } from "node:child_process";
import { pathToFileURL } from "node:url";

const status = JSON.parse(
  execFileSync("webhelm", ["status"], { encoding: "utf8" })
);
const { ensureWorkspace, deleteWorkspace } =
  await import(pathToFileURL(status.admin_helper).href);

await ensureWorkspace("Relay", 6);
// later, if the product owns and no longer needs it:
await deleteWorkspace("Relay", { force: true });
```

`ensureWorkspace(name, size)` is idempotent: it creates a missing workspace, keeps one with the same capacity, and reconfigures an existing workspace when the requested size changes. The physical tab pool still grows lazily up to that capacity. `deleteWorkspace(name, { force })` removes the workspace through the existing daemon/extension RPC path.

There is intentionally no `browser-workspace workspace create/delete` CLI. Workspace lifecycle is a product API, not an agent command.

### Start a session in a product-owned workspace

`--workspace` remains an internal integration option for product code:

```bash
webhelm session start --workspace "Relay" --url https://example.com
```

It is hidden from normal CLI help. Product code owns the workspace choice; platform actions remain unaware of workspace/session policy.

Recommended product lifecycle:

```text
product startup
  -> webhelm status
  -> import status.admin_helper
  -> ensureWorkspace("Relay", 6)

browser task
  -> webhelm session start --workspace "Relay"
  -> webhelm session exec <session_id>
  -> webhelm session stop <session_id>
```

## Platform boundary

Platform action code is infrastructure-agnostic. It may use browser helpers, but it must not create/stop Browser Workspace sessions, choose workspaces, or import session/workspace infrastructure. The generic platform runner wraps actions in a default Harness session and always cleans up. Product code may execute the same action in a product-owned browser context when longer-lived isolation is required.

Each platform manifest records explicit verification status and evidence. `verified` means live-site verification; migrated code is labeled `migrated_unverified` until exercised in the current integration.


## WebHelm skill installation

Install the self-contained skill with:

```bash
npx skills add lalalic/browser-workspace --skill webhelm
```

Run the branded CLI using the published Python/PyPI runtime:

```bash
webhelm status
webhelm session start
webhelm platform profile chatgpt
```

The `webhelm` command uses the published Browser Workspace runtime. WebHelm owns its managed Chrome profile and daemon;
it does not modify a user's default Chrome profile. The Chrome Store extension
may require explicit user approval.

### Python distribution (PyPI)

Browser Workspace is also packaged as a Python CLI. Once its PyPI trusted publisher is configured and a `pypi-v*` release tag is published, invoke it with:

```bash
webhelm status
webhelm session list
webhelm platform profile wechat-channels
```

The package entry point is `browser_workspace_app.cli:main`, and Python dependencies are managed by `pyproject.toml`. This uses the same existing Chrome profile and Session Daemon socket as the CLI; it does **not** start a second browser or daemon when the existing one is healthy.

Build with `uv build`, then validate the built CLI through the global launcher with `WEBHELM_CLI_SOURCE=/absolute/path/to/dist/package.whl webhelm --help`. Run tests with `uv run --with pytest pytest -q` (covers `test/` and `skills/`) and `node --test test/workspace-manager.test.mjs`. The PyPI publishing workflow uses GitHub OIDC trusted publishing; configure `lalalic/browser-workspace` with the `pypi` environment as the publisher on PyPI before the first tag release.
