# Browser Workspace

Chrome extension for named browser-agent workspaces inside the user's normal Chrome profile.

Each workspace is a Chrome tab group whose **total tab count equals the configured pool size**. There is no extra marker tab. Workspace identity is the unique Chrome tab-group title, so runtime `groupId` changes are rediscovered after Chrome restarts.

## Contract

The MV3 service worker exposes:

- `workspace.create(name, poolSize)`
- `workspace.ensure(name, defaultPoolSize)`
- `workspace.status(name)`
- `workspace.list()`
- `workspace.acquire(name, url)`
- `workspace.release(name, tabId)`
- `workspace.resize(name, poolSize)`
- `workspace.delete(name, force=false)`

The extension owns only group/pool lifecycle. Page operations belong to Browser Harness.

## Install for development

Open `chrome://extensions`, enable Developer mode, choose **Load unpacked**, and select:

```
~/Workspace/browser-workspace/extension
```

The manifest contains a stable public key, so the unpacked extension keeps extension ID:

`kgbghhigmbpefppgkocgjgnnnbhjchic`

## Tests

```bash
node --test test/workspace-manager.test.mjs
```
