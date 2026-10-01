# Browser Workspace

Browser Workspace is a single browser automation skill and CLI built around persistent Python sessions, workspace-owned Chrome tabs, compact snapshot refs, and built-in platform workflows.

## Public interface

Only session lifecycle is exposed at the shell level:

```bash
browser-workspace session start [--workspace NAME] [--url URL]
browser-workspace session exec SESSION_ID <<'PY'
print(snapshot())
PY
browser-workspace session stop SESSION_ID
```

Browser operations are Python helpers inside the session. There are intentionally no parallel top-level `open`, `tabs`, `status`, or `screenshot` commands.

## Included layers

```text
browser-workspace
├── src/browser_harness/     low-level browser/CDP runtime (forked internally)
├── agent-workspace/         Browser Workspace helper layer
├── extension/               Chrome workspace/tab manager
├── session_daemon.py        persistent Python session service
├── platforms/               built-in site workflows
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
