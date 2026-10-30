# Verified Lessons

- Imported platform helper modules do not inherit browser helpers injected into the action namespace; pass `js`, `wait_for_element`, and related helpers explicitly.
- CapCut's mode/model menus render asynchronously; wait for semantic roles such as `[role="menuitemradio"]` and `[role="listbox"][aria-label="Model"]` before reading or selecting options.
- Platform files are read live from `WEBHELM_PLATFORM_DIR`, so platform edits need no rebuild. To test unreleased CLI changes, run `WEBHELM_CLI_SOURCE=/path/to/browser-workspace WEBHELM_CLI_REFRESH=1 webhelm ...`. This selects the local CLI without changing the global Skill installation.
- DeepSeek supports visual image questions, not just OCR (live PNG check, 2026-10-29). Read final answers from `.ds-assistant-message-main-content`, not the reasoning panel. Preserve busy composers and resume pending submissions without sending again.
- Z.ai chat routes use `/c/{id}`, with `textarea[placeholder="Send a Message"]`, `#send-message-button`, and `.user-message`. Lifecycle submission actions remain unverified until explicitly exercised live.
