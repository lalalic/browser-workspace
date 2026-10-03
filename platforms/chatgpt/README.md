# ChatGPT browser platform

Canonical reusable browser mechanics for ChatGPT.

This platform owns ChatGPT-specific page behavior. Callers own lifecycle:

- Agents Relay: disposable worker lifecycle and event/barrier ownership.
- NeoY Tutor Workspace: persistent learner/thread lifecycle.

Use Browser Workspace as the only browser-control engine. Do not duplicate ChatGPT
selectors or submit/result-completion logic in callers.

`temporary-submit` owns the reusable Temporary Chat page mechanics and verified submit receipt. Callers that need delayed cleanup should render the action source into a caller-owned Browser Workspace session and stop that session at their lifecycle barrier.

## Web ChatGPT MCP apps

Use the `mcp-app` action for repeatable inspection of an installed custom MCP app and for a safe tool refresh. It deliberately uses semantic text/role discovery rather than transient snapshot refs such as `e31`.

```bash
cat > /tmp/chatgpt-mcp-app.json <<'JSON'
{"app_name":"neo","operation":"status"}
JSON
browser-workspace platform run chatgpt mcp-app --config /tmp/chatgpt-mcp-app.json
```

A connected app is verified by its detail page exposing `Permissions`, `Disconnect`, and `Refresh tools`. The action returns these as structured booleans.

### Configure a custom MCP app

The proven Web ChatGPT flow is:

1. Start/reuse a Browser Workspace session on `https://chatgpt.com` and take a fresh `snapshot()` before interacting. Never reuse `eNN` refs from an earlier snapshot.
2. Open the visible profile menu by semantic label `Open profile menu`, choose `Settings`, then choose `Plugins`. The durable settings route observed in October 2026 is `/settings/plugins-settings`, but prefer semantic navigation because routes can drift.
3. From Plugins, use the create/add-custom-app control. Enter the app display name and its public HTTPS MCP endpoint. Keep endpoint/client/OAuth values in caller configuration; never commit credentials to this platform.
4. Ask ChatGPT to scan/discover the MCP tools. If OAuth is advertised by the MCP server, continue the OAuth authorization flow and return to ChatGPT.
5. Finish creating/installing the app, then reopen Settings -> Plugins and select the app by exact display name.
6. Verify the detail page exposes `Permissions`, `Disconnect`, and `Refresh tools`. `Disconnect` is the positive signal that the account/OAuth connection is established. Run `mcp-app` with `operation=status` to capture this verification programmatically.
7. After an MCP server descriptor/tool change, use `operation=refresh-tools`, then inspect status again before testing tool calls.

### Snapshot-first fallback for UI drift

If a semantic selector no longer resolves, do not guess coordinates or hard-code old refs. In the same Browser Workspace session:

```python
print(snapshot(interactive_only=False))
```

Use the fresh accessibility/DOM output to rediscover the visible control by role, accessible label, or stable text. When a menu is lazy-loaded, trigger the visible semantic control, wait for hydration, then snapshot again. This is how the profile menu -> Settings -> Plugins path was recovered during the live MCP setup.

Destructive controls (`Disconnect`, `Uninstall`, `Delete app`) are intentionally not exposed as `mcp-app` operations.


## XChat lifecycle control transfer

Browser Workspace owns the ChatGPT UI mechanics for orchestrator lifecycle handoff.

- `new-turn`: given stable `project_id`, `thread_id`, and `message`, wait until the current assistant turn is no longer generating, submit the continuation as the next user turn in the same thread, verify acceptance, and return without waiting for the new assistant answer.
- `new-thread`: given stable `project_id` and `message` (plus optional `source_thread_id` provenance), open the same Project, submit the continuation to create a fresh thread, and return the durable new `thread_id` once ChatGPT replaces any temporary local id.

These actions are control-transfer primitives. The generic Browser Workspace runner owns session start/stop and cleanup. Product code should pass stable Project/Thread IDs rather than persist ChatGPT URLs or DOM identities.
