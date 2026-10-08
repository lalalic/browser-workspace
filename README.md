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

`session stop` closes all tabs created/owned by that session while leaving unrelated browser tabs untouched. Raw session CDP cannot create targets: `Target.createTarget` is rejected and callers must use `new_tab()` so workspace/session ownership is preserved.

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

By default Browser Workspace owns exactly one machine-wide persistent, visible Chrome instance. Every session and runtime reuses that same Browser Workspace Chrome; config/runtime overrides never create another Chrome. It uses a Browser Workspace-managed user-data directory, prefers CDP port 9222, and selects the next available candidate only when starting the singleton for the first time. Users do not manage Chrome profiles or remote-debugging settings. Chrome Stable no longer permits silent `--load-extension` for local unpacked extensions, so the extension is treated as an optional workspace-grouping enhancement rather than a prerequisite for browser sessions.

`BU_CDP_URL` / `BU_CDP_WS` remain advanced overrides for callers that intentionally provide their own browser endpoint. `BROWSER_WORKSPACE_CDP_PORT` changes the preferred managed port.

The Web Store build remains available for ordinary interactive Chrome installs, but the managed runtime does not depend on it: `https://chromewebstore.google.com/detail/kgbghhigmbpefppgkocgjgnnnbhjchic`.

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
browser-workspace status
```

The command returns machine-readable JSON including the resolved installation `root`, absolute `admin_helper` path, and daemon status. Calling `status` also ensures the existing Browser Workspace session daemon is ready; it does not create a separate service.

A Node.js product can then load the product-only helper without depending on the `browser-workspace` npm package or hardcoding an install path:

```js
import { execFileSync } from "node:child_process";
import { pathToFileURL } from "node:url";

const status = JSON.parse(
  execFileSync("browser-workspace", ["status"], { encoding: "utf8" })
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
browser-workspace session start --workspace "Relay" --url https://example.com
```

It is hidden from normal CLI help. Product code owns the workspace choice; platform actions remain unaware of workspace/session policy.

Recommended product lifecycle:

```text
product startup
  -> browser-workspace status
  -> import status.admin_helper
  -> ensureWorkspace("Relay", 6)

browser task
  -> browser-workspace session start --workspace "Relay"
  -> browser-workspace session exec <session_id>
  -> browser-workspace session stop <session_id>
```

## Platform boundary

Platform action code is infrastructure-agnostic. It may use browser helpers, but it must not create/stop Browser Workspace sessions, choose workspaces, or import session/workspace infrastructure. The generic platform runner wraps actions in a default Harness session and always cleans up. Product code may execute the same action in a product-owned browser context when longer-lived isolation is required.

Each platform manifest records explicit verification status and evidence. `verified` means live-site verification; migrated code is labeled `migrated_unverified` until exercised in the current integration.


## npx skills installation

After `npx skills add ...`, invoke `~/.agents/skills/browser-workspace/bin/browser-workspace` directly. The first session start bootstraps the skill-owned Python virtual environment automatically; running `scripts/install.sh` is optional.

### Python distribution (PyPI)

Browser Workspace is also packaged as a Python CLI. Once its PyPI trusted publisher is configured and a `pypi-v*` release tag is published, invoke it with:

```bash
uvx browser-workspace status
uvx browser-workspace session list
uvx browser-workspace platform profile wechat-channels
```

The package entry point is `browser_workspace_app.cli:main`, and Python dependencies are managed by `pyproject.toml`. This uses the same existing Chrome profile and Session Daemon socket as the previous npm CLI; it does **not** start a second browser or daemon when the existing one is healthy.

Before building, run `python tools/sync-pypi-package.py` to copy canonical Python and packaged platform assets to the wheel source. Run `uv build`, then validate with `uvx --from dist/browser_workspace-<version>-py3-none-any.whl browser-workspace status`. The PyPI publishing workflow uses GitHub OIDC trusted publishing; configure `lalalic/browser-workspace` with the `pypi` environment as the publisher on PyPI before the first tag release.
