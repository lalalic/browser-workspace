# WebHelm

WebHelm is one **Node.js browser-automation Skill**: one long-running daemon, one machine-wide managed Chrome instance, one CDP WebSocket, explicit independent CDP attachments per tab, and one shared Chrome extension for visible tab groups.

The entire deployable runtime, platform Actions, Chrome extension, Skill instructions, lockfile, and installer live together in **`skills/webhelm/`**. No independent Browser Harness installation, Python interpreter, two-layer daemon, separate WebHelm npm publication, or PyPI release is needed.

## Install

```sh
npx skills add lalalic/browser-workspace --skill webhelm
SKILL_DIR="<actual WebHelm Skill directory>"
sh "$SKILL_DIR/scripts/install-global-cli.sh"
webhelm status
```

Node.js >=22.5 and npm are required. The installer uses the Skill's `package-lock.json` to install one small local JS dependency (`yaml`) and manages `~/.local/bin/webhelm`. Chrome launches automatically if missing, using the existing managed profile at `~/.config/browser-workspace/chrome`.

## Operate

```sh
webhelm session start --url https://example.com
webhelm session exec SESSION_ID <<'JS'
console.log(await snapshot());
await click('[data-ref="e1"]');
JS
webhelm session stop SESSION_ID

webhelm platform list
webhelm platform profile chatgpt
webhelm platform source z new-turn
webhelm platform run chatgpt validate --auto-session
```

Agent-facing Browser Helpers use `await`-style JavaScript in persistent Session contexts. Tabs and popups are owned by their Session, explicit CDP `sessionId` routes are used, and independent Sessions execute concurrently. Extension management remains inside the Skill; only its tab-group lease RPC travels through the extension.

The 11 platform adapters are migrated to `.mjs`, including ChatGPT's durable FIFO SQLite runtime. Migration does not imply every live site flow is verified after the port; consult the platform's `manifest.yaml` and verify real website behavior before using actions with external side effects.

## Code layout

```text
skills/webhelm/
  SKILL.md                    single agent interface
  bin/webhelm                 global CLI target
  runtime/                    Node daemon, CLI, Chrome, Session, platform loader
  platforms/                  site-specific JS actions, manifest, queue
  extension/                  one canonical Chrome extension source
  scripts/                    single installer and offline extension packaging
  package.json, package-lock.json

test/node/                     Node runtime and CLI tests
test/workspace-manager.test.mjs  extension tests
```

## Development / deployment

```sh
npm ci --prefix skills/webhelm
npm test --prefix skills/webhelm
node skills/webhelm/runtime/cli.mjs platform list
```

For live read-only Chrome testing without changing the production daemon:

```sh
export WEBHELM_RUNTIME_DIR=/private/tmp/webhelm-node-test
export WEBHELM_SOCKET=$WEBHELM_RUNTIME_DIR/session.sock
export WEBHELM_LOCK=$WEBHELM_RUNTIME_DIR/daemon.lock
export WEBHELM_CDP_URL=http://127.0.0.1:9222
./skills/webhelm/bin/webhelm status
```

Preserve the persistent ChatGPT `chatgpt-new-turn.sqlite3` queue when retiring any earlier runtime; never run two dispatchers on the same DB. Release through the Skill source and its installer, not PyPI or an external npm package. GitHub extension release assets derive only from the bundled extension source.
