---
name: browser-workspace
description: Control the real browser through one Browser Workspace skill and CLI, with leased tab workspaces, persistent Python sessions, compact snapshots, and built-in platform workflows.
---

# Browser Workspace

Browser Workspace is the **only browser skill agents should load**. It includes the browser-control runtime, workspace/tab leasing, persistent Python sessions, snapshot refs, and site-specific platform workflows. Do not load or invoke a separate `browser-harness` or `browser-platforms` skill.

## Agent contract

Use one of two execution paths:

```text
known platform flow
  -> browser-workspace platform run <platform> <action> [--config FILE]
  -> runner creates the browser session
  -> runner executes the platform action
  -> runner always stops and cleans up

custom browser workflow
  -> browser-workspace session start
  -> browser-workspace session exec <session_id>
  -> browser-workspace session stop <session_id>
```

Do not manually create a session around a platform action unless product code intentionally owns a longer-lived browser context. There are no separate top-level `open`, `tabs`, `status`, or `screenshot` commands.

Every logical browser workflow must follow:

```text
start
  -> exec
  -> exec
  -> ...
finally
  -> stop
```

Rules:

- Start one session per logical browser workflow and retain its `session_id`.
- Reuse that same session for every action/observation turn.
- Always stop the session in cleanup/finally, including on failure or cancellation.
- A session owns one leased browser tab and a persistent Python namespace.
- Multiple independent workflows may use different sessions concurrently.

## Start

Default workspace is `Harness`:

```bash
browser-workspace session start
```

Normal agents do not choose a workspace. `session start` defaults to `Harness`; the `--workspace` implementation option is hidden from normal CLI help. Product integrations such as Family Tutor or Agents Relay may set an explicit workspace in their own code/config when isolation is a product requirement.

Start directly at a URL when known:

```bash
browser-workspace session start --url https://example.com
```

The result is JSON containing `session_id`, `workspace`, `target_id`, the starting `url`, and `workspace_supported`.

The Chrome workspace extension is optional. If it is not installed, `session start` still succeeds and browser automation continues without workspace grouping/lease isolation. The result includes a soft `warning` and `extension_url` pointing to the Chrome Web Store. Do not treat this warning as a session failure.

## Exec

`session exec` reads Python from stdin. Helpers are already imported; do not import another browser package.

```bash
browser-workspace session exec <session_id> <<'PY'
print(page_info())
print(snapshot())
PY
```

Python state persists across later calls in the same session:

```bash
browser-workspace session exec <session_id> <<'PY'
meeting_name = "Demo"
print(current_tab())
PY
```

Then later:

```bash
browser-workspace session exec <session_id> <<'PY'
print(meeting_name)
PY
```

A Python file may also be used with `--code-file`.

## Stop

```bash
browser-workspace session stop <session_id>
```

Stopping closes every tab owned or opened by that session—including tabs created with `new_tab()`, `bh.new_tab()`, direct `Target.createTarget`, and detected child/popup tabs—then destroys the session's Python namespace. It does not close unrelated browser tabs. Do not reuse the ID afterward.

A safe shell structure is:

```bash
SESSION_JSON=$(browser-workspace session start)
SESSION_ID=$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["session_id"])' "$SESSION_JSON")
trap 'browser-workspace session stop "$SESSION_ID" >/dev/null 2>&1 || true' EXIT

browser-workspace session exec "$SESSION_ID" <<'PY'
print(snapshot())
PY
```

## Browser helpers

The session exposes the browser primitives directly, including:

```python
page_info()
goto_url(url)
current_tab()
new_tab(url)
close_tab(...)
js(expression, target_id=None)
cdp(method, ...)
wait_for_load()
wait_for_element(...)
fill_input(selector, text)
click(selector)
capture_screenshot(...)
```

Use the higher-level helpers first. Use raw `js(...)`/`cdp(...)` only when needed.

Interaction-specific reference material is bundled under `interaction-skills/` inside this skill.

## Snapshot refs

`snapshot()` returns a compact accessibility-oriented view and writes each returned ref directly onto the corresponding live DOM element as `data-ref="eN"`.

Example:

```text
- button "Calendar" [ref=e1]
- button "Meet now" [ref=e2]
- textbox "Meeting name" [ref=e3]
```

The live DOM then contains equivalent annotations such as:

```html
<button data-ref="e2">Meet now</button>
```

Refs are ordinary CSS selectors. Use normal helpers:

```python
print(snapshot())
click('[data-ref="e2"]')
fill_input('[data-ref="e3"]', 'Demo meeting')
```

Do **not** invent `click("e2")`, `click_ref("e2")`, or an `@e2` API. After navigation or a substantial DOM update, call `snapshot()` again and use the new refs.

`snapshot(interactive_only=False)` may include named content roles in addition to interactive elements. `target_id=` may be used for target-specific inspection.

## Workspaces

Default configuration:

```text
BH_WORKSPACE_NAME=Harness
BH_WORKSPACE_POOL_SIZE=5
```

When the Browser Workspace Chrome extension is installed, the pool size is the maximum concurrent capacity; tabs are created lazily. The extension owns grouping, lease/release, idle reclaim, and workspace isolation.

Without the extension, browser sessions still work using the built-in browser core. Workspace names, grouping, pool capacity, lease isolation, and idle reclaim are unavailable; tab/navigation/input/snapshot/platform helpers continue to work. `workspace_status()` reports `supported: false` instead of failing.

Available workspace helpers include:

```python
workspace_create("Research", 5)
workspace_status()
workspace_list()
workspace_resize("Research", 6)
workspace_delete("Research")
```

Never use URL as tab identity. Workspace ownership and leased target identity are authoritative.

## Platform contract

Known-site knowledge is bundled under `platforms/`. A platform contains **site/domain behavior only**.

```text
platforms/<name>/
├── SKILL.md        site behavior and rules
├── manifest.yaml   actions + verification metadata
├── actions/        reusable browser action code
└── flows/          optional flow documentation
```

Platform rules:

- Platform actions may use browser helpers such as `new_tab()`, `current_tab()`, `snapshot()`, `js()`, `cdp()`, uploads, downloads, and screenshots.
- Platform repository files must contain **no personal data**. Do not commit a person's name, email, phone number, account/user identifier, private thread/project URL or ID, cookies/tokens, captured user content, or user-specific local filesystem paths under `platforms/`. Runtime values must come from config/input and must not be written back into platform source, manifests, docs, fixtures, or tests.
- Platform tests/examples must use synthetic generic values only. Verification evidence should describe behavior generically and must not name a person's account or preserve captured personal content.
- Platform actions must **not** create/stop Browser Workspace sessions, choose a workspace, call workspace-management APIs, invoke the Browser Workspace CLI, or import session/workspace infrastructure.
- Platform `SKILL.md` and flow docs should describe site behavior, preconditions, side effects, and verification evidence—not Browser Workspace lifecycle mechanics.
- Platform actions must remain usable in either a generic runner-owned session or a product-owned browser context.
- The generic runner owns the normal lifecycle: start a default Harness session, inject browser helpers/config, execute the action, then always stop the session and close its owned tabs.
- Products that require a dedicated or persistent browser context (for example Family Tutor or Agents Relay) may execute the same platform action inside product-owned infrastructure. The platform code itself stays unchanged.
- Do not rediscover a known site's mechanics when a verified platform flow/action already exists.

Run a platform action through the generic runner:

```bash
browser-workspace platform run microsoft-teams meeting --config /path/to/config.json
```

The runner output hides the raw session ID. It returns the platform/action result, optional workspace-extension warning, and cleanup evidence.

### Platform verification contract

Every `platforms/<name>/manifest.yaml` must declare:

```text
platform:
status:
last_verified:
actions:
verification:
  status:
  last_verified:
  evidence:
```

Verification rules:

- `verified`: exercised against the live site and supported by concrete evidence.
- `partially_verified`: some declared flows are live-verified while others remain implemented but unverified.
- `migrated_unverified`: code was migrated from a previously working adapter but has not yet been live-verified in the current Browser Workspace integration.
- Never upgrade a status merely because code compiles or contract tests pass.
- Flow-level verification in `manifest.yaml` should be more specific than the platform-wide status.
- When live behavior changes, update `last_verified`, evidence, and affected flow status in the same change.

Current bundled platforms:

```text
platforms/chatgpt/
platforms/chrome-web-store/
platforms/microsoft-teams/
platforms/tiktok/
platforms/wechat-channels/
platforms/xhs/
platforms/youtube/
```

Read the matching platform `SKILL.md` and `manifest.yaml` before invoking or modifying a known flow.

### Platform contribution workflow

Changes under `platforms/` should go through a pull request rather than being pushed directly to `main`:

1. Create a dedicated branch for the platform change.
2. Update action code, docs, manifest verification evidence, and tests together.
3. Run `python3 -m pytest -q test evals platforms/*/tests`, `node scripts/check-platforms.mjs`, and workspace-manager tests.
4. Push the branch and create a PR against `main`.
5. In the PR description, call out live verification performed, remaining unverified flows, and confirm that no personal data was added.

If repository/PR access is available, create the PR as part of the task. Otherwise, leave the change on a pushed branch and tell the user exactly what still needs to be opened as a PR. Do not silently push platform behavior changes straight to `main`.

## Installation

Run the bundled installer from the skill directory:

```bash
./scripts/install.sh
```

It creates a Browser Workspace-owned `.venv`, installs the vendored browser runtime and dependencies, writes Browser Workspace environment configuration to `agent-workspace/.env`, and links `browser-workspace` into `~/.local/bin` by default.

There is no required separate Browser Harness installation.

The Chrome extension is recommended but not required. Without it Browser Workspace runs in plain-browser mode and `session start` provides the installation link. The public Web Store URL is:

```text
https://chromewebstore.google.com/detail/kgbghhigmbpefppgkocgjgnnnbhjchic
```

The extension is also bundled at `extension/` for unpacked/development installs. Default extension ID:

```text
kgbghhigmbpefppgkocgjgnnnbhjchic
```

## Internal provenance

The low-level browser runtime is forked from `browser-use/browser-harness` and kept internally under `src/browser_harness/`. Browser Workspace is the public product/skill/CLI surface. Upstream licensing is preserved under `licenses/`.
