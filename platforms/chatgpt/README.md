# ChatGPT browser platform

Canonical reusable browser mechanics for ChatGPT.

This platform owns ChatGPT-specific page behavior. Callers own lifecycle:

- Agents Relay: disposable worker lifecycle and event/barrier ownership.
- NeoY Tutor Workspace: persistent learner/thread lifecycle.

Use Browser Workspace as the only browser-control engine. Do not duplicate ChatGPT
selectors or submit/result-completion logic in callers.

`temporary-submit` owns the reusable Temporary Chat page mechanics and verified submit receipt. Callers that need delayed cleanup should render the action source into a caller-owned Browser Workspace session and stop that session at their lifecycle barrier.
