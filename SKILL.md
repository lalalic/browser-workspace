---
name: browser-workspace
description: Configure Browser Harness to operate only inside one named Browser Workspace Chrome tab group. Depends on the browser-harness skill.
---

# Browser Workspace + Browser Harness

Use this skill whenever Browser Harness should operate inside a managed Chrome tab-group workspace instead of seeing the user's other Chrome tabs.

The Chrome extension source lives in the standalone repository:

`~/Workspace/browser-workspace`

GitHub repository:

`lalalic/browser-workspace`

This repository owns the Chrome extension, Browser Harness helper, install script, and this skill.

## Setup order

## Dependency

This skill depends on the **browser-harness skill**.

The browser-harness skill owns installation and base setup of Browser Harness. Do not duplicate that installation logic here. Before applying Browser Workspace, ensure the browser-harness skill has been installed/applied successfully and that `browser-harness` is available.

Set up Browser Workspace in this order:

0. Apply the browser-harness skill.
1. Install the Chrome extension.
2. Set the workspace environment variables.
3. Apply the Browser Workspace helper.

### 1. Install the Chrome extension

**Production / published extension:** open the Browser Workspace Chrome Web Store URL directly in the user's normal signed-in Chrome profile and install it. The skill should use the exact store URL once the extension is published; do not ask the user to search the store manually.

**Development fallback until the store listing exists:**

1. Open `chrome://extensions`.
2. Enable Developer mode.
3. Choose **Load unpacked**.
4. Select `~/Workspace/browser-workspace/extension`.

Development extension ID:

`kgbghhigmbpefppgkocgjgnnnbhjchic`

The extension owns workspace/group/pool lifecycle only. Browser Harness remains responsible for page navigation, DOM/AX operations, clicks, typing, screenshots, uploads, and downloads.

### 2. Set environment variables

Set the Browser Harness workspace name and exact pool size before applying the helper:

```bash
export BH_WORKSPACE_NAME=Harness
export BH_WORKSPACE_POOL_SIZE=5
```

Optionally override the extension ID:

```bash
export BH_WORKSPACE_MANAGER_EXTENSION_ID=kgbghhigmbpefppgkocgjgnnnbhjchic
```

`BH_WORKSPACE_POOL_SIZE=N` means exactly **N Chrome tabs total in the group**.

### 3. Apply the Browser Workspace helper

Run:

```bash
~/Workspace/browser-workspace/scripts/install.sh
```

The installer copies `browser-harness/agent_helpers.py` into:

`$BH_AGENT_WORKSPACE/agent_helpers.py`

or, when `BH_AGENT_WORKSPACE` is unset:

`~/.config/browser-harness/agent-workspace/agent_helpers.py`

It also persists the current Browser Workspace environment values into the Browser Harness workspace `.env`, so future `browser-harness` processes use the same workspace by default.

Example one-shot setup:

```bash
BH_WORKSPACE_NAME=Research \
BH_WORKSPACE_POOL_SIZE=4 \
~/Workspace/browser-workspace/scripts/install.sh
```

## Runtime behavior

After setup, use `browser-harness` normally.

Each new Browser Harness process reads the configured environment. The helper:

- creates the selected workspace automatically when it is missing;
- exposes only tabs in `BH_WORKSPACE_NAME`;
- leases `new_tab(url)` from that workspace pool;
- returns `close_tab()` tabs to the pool;
- refuses visible activation and operations on tabs outside the workspace;
- fails closed when Chrome tab to CDP target mapping is ambiguous.

`BH_WORKSPACE_POOL_SIZE=N` means exactly **N Chrome tabs total in the group**. There is no extra marker tab.

Workspace identity is the unique Chrome tab-group title. Chrome `groupId` is treated as ephemeral and rediscovered after restarts. Duplicate groups with the same workspace title are considered ambiguous and fail closed.

## Changing workspace

Changing the env value affects the next Browser Harness process:

```bash
export BH_WORKSPACE_NAME=Research
export BH_WORKSPACE_POOL_SIZE=4
browser-harness
```

An already-running Browser Harness process keeps the values it started with.

For an existing workspace, `BH_WORKSPACE_POOL_SIZE` is the creation/default size. To resize an existing workspace explicitly, use:

```python
workspace_resize("Research", 6)
```

## Workspace helpers

The installed helper also exposes:

```python
workspace_create("Research", 4)
workspace_status()
workspace_list()
workspace_resize("Research", 6)
workspace_delete("Research")
```

Normal Browser Harness page operations remain unchanged.
