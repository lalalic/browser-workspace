# Verified Lessons

- Imported platform helper modules do not inherit browser helpers injected into the action namespace; pass `js`, `wait_for_element`, and related helpers explicitly.
- CapCut's mode/model menus render asynchronously; wait for semantic roles such as `[role="menuitemradio"]` and `[role="listbox"][aria-label="Model"]` before reading or selecting options.
- Platform files are read live from `WEBHELM_PLATFORM_DIR`, so platform edits need no rebuild. To test unreleased CLI changes, run `WEBHELM_CLI_SOURCE=/path/to/browser-workspace WEBHELM_CLI_REFRESH=1 webhelm ...`. This selects the local CLI without changing the global Skill installation.
- DeepSeek supports visual image questions, not just OCR (live PNG check, 2026-10-29). Read final answers from `.ds-assistant-message-main-content`, not the reasoning panel. Preserve busy composers and resume pending submissions without sending again.
- Z.ai chat routes use `/c/{id}`, with `textarea[placeholder="Send a Message"]`, `#send-message-button`, and `.user-message`. Lifecycle submission actions remain unverified until explicitly exercised live.
- Keep exactly one version-controlled Chrome extension source at `skills/webhelm/extension/`. Package the Web Store ZIP from that source by converting only the manifest at build time (remove the unpacked public key, add the Web Store `update_url`). Tests, Skill distribution, and release workflows must reference that same source.
- Plain-browser fallback must not reuse pre-existing `about:blank` targets for new sessions. Sessions close their owned targets, so allocate a distinct CDP Target and clean it up if initial navigation fails. E2E must confirm all pre-existing tabs survive session stop.
