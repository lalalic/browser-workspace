---
name: browser-workspace
description: Set up and use Browser Workspace with Browser Harness. Depends on the browser-harness skill.
---

# Browser Workspace

Use this skill to set up Browser Workspace after the skill itself has been installed and loaded.

This skill depends on the **browser-harness** skill. Browser Harness installation and base configuration belong to that skill.

## Setup entry point

When this skill is loaded for setup, do the following in order:

1. Ensure the `browser-harness` skill has been applied and `browser-harness` is available.
2. Ask the user to install the bundled Chrome extension manually.
3. Configure the Browser Workspace environment.
4. Apply the bundled Browser Harness helper.
5. Verify Browser Workspace can create and see the configured group.

Do not assume a particular checkout directory, home directory, or project layout.

## 1. Install the bundled Chrome extension

The Chrome extension is bundled with this skill at:

`<browser-workspace>/extension`

Here, `<browser-workspace>` means the local directory containing this `SKILL.md`.

Resolve that directory to an **absolute local path**, then tell the user exactly which folder to select.

Ask the user to do this manually in Chrome:

1. Open `chrome://extensions`.
2. Enable **Developer mode**.
3. Click **Load unpacked**.
4. Select the exact local `<browser-workspace>/extension` directory you resolved above.

Do not direct the user to a store page. Do not mention a repository, clone location, or another machine's filesystem path.

After the user confirms the extension is loaded, continue setup.

Default extension ID:

`kgbghhigmbpefppgkocgjgnnnbhjchic`

## 2. Configure Browser Workspace

Defaults:

```bash
BH_WORKSPACE_NAME=Harness
BH_WORKSPACE_POOL_SIZE=5
```

`BH_WORKSPACE_POOL_SIZE=N` means **N is the maximum concurrent capacity**;
physical Chrome tabs are created lazily as callers acquire them.

The extension ID can be overridden when necessary:

```bash
BH_WORKSPACE_MANAGER_EXTENSION_ID=<extension-id>
```

Do not expose or reuse machine-specific environment values from another installation.

## 3. Apply the bundled Browser Harness helper

The installer is bundled at:

`<browser-workspace>/scripts/install.sh`

Run it from the resolved local skill directory, for example:

```bash
"<browser-workspace>/scripts/install.sh"
```

The installer copies:

`<browser-workspace>/browser-harness/agent_helpers.py`

into the Browser Harness agent workspace and persists the Browser Workspace environment settings in its `.env`.

By default the target is:

`~/.config/browser-harness/agent-workspace/agent_helpers.py`

If `BH_AGENT_WORKSPACE` is set, use that Browser Harness agent workspace instead.

To override the defaults for this installation:

```bash
BH_WORKSPACE_NAME=Research \
BH_WORKSPACE_POOL_SIZE=4 \
"<browser-workspace>/scripts/install.sh"
```

## 4. Verify

Start a new Browser Harness process after applying the helper.

Verify that:

- the configured group is created or reconciled;
- the group name matches `BH_WORKSPACE_NAME`;
- the group contains no more than `BH_WORKSPACE_POOL_SIZE` tabs;
- Browser Harness exposes only tabs belonging to that workspace.

If the extension is not available, stop and ask the user to confirm that the unpacked extension is loaded from the exact local `<browser-workspace>/extension` path.

## Runtime behavior

The helper:

- relies on the extension to reclaim inactive leased tabs after 5 minutes and to eject unrelated Chrome-created tabs from the workspace group;

- creates the selected workspace automatically when it is missing;
- exposes only tabs in `BH_WORKSPACE_NAME`;
- leases `new_tab(url)` from that workspace pool, including `http(s)` and `chrome-extension://` pages;
- returns `close_tab()` tabs to the pool;
- refuses visible activation and operations on tabs outside the workspace;
- learns and owns the Chrome-tab-to-CDP-target mapping when a tab is leased, so downstream Browser Harness callers do not need identity workarounds;
- fails closed only when an untracked Chrome tab cannot be mapped uniquely.

Workspace identity is the unique Chrome tab-group title. Chrome `groupId` is treated as ephemeral and rediscovered after restarts. Duplicate groups with the same workspace title are considered ambiguous and fail closed.

## Changing workspace

Changing the environment affects the next Browser Harness process:

```bash
export BH_WORKSPACE_NAME=Research
export BH_WORKSPACE_POOL_SIZE=4
browser-harness
```

An already-running Browser Harness process keeps the values it started with.

For an existing workspace, `BH_WORKSPACE_POOL_SIZE` is the creation/default size. To resize an existing workspace explicitly:

```python
workspace_resize("Research", 6)
```

## Workspace helpers

The installed helper exposes:

```python
workspace_create("Research", 5)
workspace_status()
workspace_list()
workspace_resize("Research", 6)
workspace_delete("Research")
```

Normal Browser Harness page operations remain unchanged.


## Snapshot refs

Browser Workspace provides a `snapshot()` helper for compact, agent-friendly inspection of the current page. The snapshot helper does not create a separate persistent ref registry. Instead, it annotates matching live DOM elements directly with temporary `data-ref` attributes and returns a compact textual representation of those elements.

Example snapshot output:

```text
- button "Calendar" [ref=e1]
- button "Meet now" [ref=e2]
- textbox "Meeting name" [ref=e3]
- button "Start meeting" [ref=e4]
```

Conceptually, the live page has been annotated like:

```html
<button data-ref="e1">Calendar</button>
<button data-ref="e2">Meet now</button>
<input data-ref="e3" aria-label="Meeting name">
<button data-ref="e4">Start meeting</button>
```

Refs from `snapshot()` are ordinary DOM selectors, not a separate interaction API. Use existing Browser Harness helpers with a CSS selector built from the returned ref.

```python
snapshot()
click('[data-ref="e2"]')
fill_input('[data-ref="e3"]', 'Test meeting')
click('[data-ref="e4"]')
```

Do not invent calls such as `click("e2")` or `click_ref("e2")`. The supported pattern is always the normal Browser Harness helper plus a selector such as `[data-ref="e2"]`.

A later `snapshot()` may rewrite or replace existing `data-ref` attributes. Treat refs as a short-lived description of the current DOM, not as stable element identity across navigation or major page changes. If a ref no longer matches, take a new snapshot and use the new ref.

For iframe/target-specific work, take the snapshot in the intended target and use the corresponding Browser Harness target-aware helper/selector pattern for that same target.

## Persistent Python browser sessions

Use Browser Workspace sessions for multi-turn browser work. The CLI is the primary portable interface and works on any Mac where this skill has been applied; MCP, when available, is only another transport over the same local session daemon.

Before executing Python in a session, load the **browser-harness** skill to learn the available helper methods, interaction workflow, and constraints. Helpers are preloaded automatically in the session Python namespace.

### Session lifecycle contract

Every workflow must follow this lifecycle:

```text
start
  -> exec
  -> exec
  -> ...
finally
  -> stop
```

Rules:

- Call `session start` exactly once for one logical browser workflow and keep the returned `session_id`.
- Reuse that same `session_id` for every action-observe-action turn in the workflow.
- Do not start a new session just to continue interacting with the same leased tab.
- Python globals, imports, functions, intermediate values, and the leased tab persist across `session exec` calls.
- Multiple independent workflows may use different session IDs concurrently.
- Always call `session stop` when the workflow finishes, fails, is cancelled, or throws. Treat stop as a `finally` cleanup operation.
- `session stop` releases the leased Browser Workspace tab and discards the Python namespace. Do not reuse the session ID afterward.
- If a caller owns the session, that caller owns cleanup. Do not stop another caller's session.

The installer places the CLI at `~/.local/bin/browser-workspace` by default. If it is on `PATH`, use `browser-workspace`; otherwise invoke that absolute path.

Start a session, optionally selecting a dedicated workspace:

```bash
browser-workspace session start --workspace "Family Tutor"
```

The command returns JSON containing `session_id`, `workspace`, and `target_id`. Save `session_id` and use it for all later calls.

Execute Python using the same stdin/heredoc convention as `browser-harness`:

```bash
browser-workspace session exec <session_id> <<'PY'
print(page_info())
PY
```

Use additional `session exec` calls for later observe/action turns; do not recreate state manually.

A shell workflow should structurally resemble:

```bash
SESSION_JSON=$(browser-workspace session start --workspace Harness)
SESSION_ID=$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["session_id"])' "$SESSION_JSON")
trap 'browser-workspace session stop "$SESSION_ID" >/dev/null 2>&1 || true' EXIT

browser-workspace session exec "$SESSION_ID" <<'PY'
print(page_info())
PY

browser-workspace session exec "$SESSION_ID" <<'PY'
# next action/observe turn; prior Python state is still available
print(current_tab())
PY
```

For a Python file:

```bash
browser-workspace session exec <session_id> --code-file /path/to/action.py
```

Explicit cleanup:

```bash
browser-workspace session stop <session_id>
```

CLI and MCP share the same local session daemon and session IDs, so a session started through one transport can be continued through the other.
