# ChatGPT browser platform

Canonical reusable browser mechanics for ChatGPT.

This platform owns ChatGPT-specific page behavior. Callers own lifecycle:

- `chatgpt-browser-worker`: disposable worker lifecycle.
- NeoY Tutor Workspace: persistent learner/thread lifecycle.

Use Browser Workspace as the only browser-control engine. Do not duplicate ChatGPT
selectors or submit/result-completion logic in callers.
