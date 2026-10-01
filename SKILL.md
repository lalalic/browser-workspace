---
name: browser-workspace
description: Control the real browser through one Browser Workspace skill and CLI, with leased tab workspaces, persistent Python sessions, compact snapshots, and built-in platform workflows.
---

# Browser Workspace

Browser Workspace is the **only browser skill agents should load**. It includes the browser-control runtime, workspace/tab leasing, persistent Python sessions, snapshot refs, and site-specific platform workflows. Do not load or invoke a separate `browser-harness` or `browser-platforms` skill.

## Agent contract

Use only this shell lifecycle:

```text
browser-workspace session start
browser-workspace session exec <session_id>
browser-workspace session stop <session_id>
```

All browser actions happen as Python inside `session exec`. Do not look for separate CLI commands such as `open`, `tabs`, `status`, or `screenshot`.

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

Choose a named workspace:

```bash
browser-workspace session start --workspace "Family Tutor"
```

Start directly at a URL when known:

```bash
browser-workspace session start \
  --workspace Harness \
  --url https://example.com
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
SESSION_JSON=$(browser-workspace session start --workspace Harness)
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

## Platform workflows

Known-site knowledge is bundled into this same skill under `platforms/`:

```text
platforms/chatgpt/
platforms/chrome-web-store/
platforms/microsoft-teams/
platforms/tiktok/
platforms/wechat-channels/
platforms/xhs/
platforms/youtube/
```

When the current task matches a known platform, read that platform's `SKILL.md`/flow files and reuse its runner/helper code instead of rediscovering the site with raw DOM automation. These are internal references of Browser Workspace, not separate skills.

For example, Microsoft Teams meeting automation is documented under `platforms/microsoft-teams/` and includes the verified `Calendar -> Meet now -> Start meeting -> pre-join -> Join now -> in-call` flow.

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
