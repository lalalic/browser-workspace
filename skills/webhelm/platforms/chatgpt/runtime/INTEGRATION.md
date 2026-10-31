# Node runtime integration contract

Each action module exports `async run({ helpers, config })`. The runner supplies browser helpers in `helpers`; do not import injected globals into sibling modules. In particular, async `new-turn` requires `helpers.enqueueChatGPTTurn(request)` or a `helpers.chatgptQueue.enqueue(request)` callback. Normal browser actions receive the caller-owned Session helpers and never create/stop the caller's Session.

The daemon owns one `ChatGPTQueue` instance. Import `ChatGPTQueue` or
`createChatGPTQueue` from `runtime/chatgpt-queue.mjs`; provide the daemon's
existing Session callbacks and a writable persistence root:

```js
import { ChatGPTQueue } from './chatgpt-queue.mjs';

const queue = new ChatGPTQueue({
  persistenceRoot: runtimeDirectory,
  startSession: async ({ url }) => sessionManager.start({ url }),
  execSession: async (sessionId, source) => sessionManager.exec(sessionId, source),
  stopSession: async sessionId => sessionManager.stop(sessionId),
  intervalMs: 60_000,
  concurrency: 4,
});
queue.start();
```

`startSession` returns `{ session_id }`. `execSession` executes an **async
JavaScript** source string in that Session and returns either the action value
or `{ ok, value, error, stderr }`; browser helpers (`js`, `page_info`,
`goto_url`, `wait_for_load`, `sleep`) are injected into the Session context.
`stopSession` always receives the private dispatcher Session id. This module
never starts another browser process and does not take ownership of caller
Sessions.

Public methods:

- `enqueue({ thread_id, project_id?, message, idempotency_key, mergeable? })`
  returns `{ ok: true, status: 'queued', queue_id, thread_id, state }`. The key
  may also be spelled `idempotencyKey` for JS callers. Exact key reuse with a
  different payload fails. A request is durably committed before it returns.
- `inspect()` returns pending row summaries without message text.
- `rows()` is an internal diagnostic view and contains prompts; do not expose
  it in daemon status endpoints.
- `reconcile({ queue_id, evidence, accepted })` requires caller-supplied
  read-only evidence. `accepted: true` resolves an uncertain send to `SENT`;
  `false` returns it to `WAITING` only after evidence establishes that no send
  took effect.
- `shutdown()` stops scheduling, waits for active attempts, closes owned
  private Sessions and closes SQLite. `close()` aliases `shutdown()`.

The runtime requires Node.js 22.5 or newer for the built-in `node:sqlite` module. SQLite is stored at `<persistenceRoot>/chatgpt-new-turn.sqlite3` using WAL and
FULL synchronous writes. A new instance reopens the same queue. `CHECKING`
leases expire back to `WAITING`; expired `SENDING` leases become `UNCERTAIN`
and are never automatically resent. Per-thread FIFO holds successors behind
`WAITING`, `BLOCKED`, `SENDING`, or `UNCERTAIN` items. Independent thread heads
may run concurrently. A sent item applies the configured interval cooldown.
Mergeable requests combine only into the same thread's still-pending mergeable
tail; every original idempotency key remains mapped to that queue id.

The queue dispatcher is async and uses the read-only ChatGPT probe before
submission. It enters `SENDING` before its one send attempt. Only the exact
`send-button-disabled` receipt reaches `SENT`; a timeout, ambiguous response,
or transport failure after entering `SENDING` is persisted as `UNCERTAIN`.
