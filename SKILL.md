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

`BH_WORKSPACE_POOL_SIZE=N` means exactly **N Chrome tabs total in the group**.

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
- the group contains exactly `BH_WORKSPACE_POOL_SIZE` tabs;
- Browser Harness exposes only tabs belonging to that workspace.

If the extension is not available, stop and ask the user to confirm that the unpacked extension is loaded from the exact local `<browser-workspace>/extension` path.

## Runtime behavior

The helper:

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
