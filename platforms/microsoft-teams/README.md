---
name: microsoft-teams-platform
description: Microsoft Teams browser mechanics and verified meeting flows.
---

# Microsoft Teams

This platform defines site behavior only. Execution lifecycle and isolation are external to platform code.

## Canonical instant-meeting path

For automated meeting E2E, use exactly:

`left sidebar Calendar -> Meet now -> Start meeting (when shown) -> pre-join -> Join now -> in-call`

Do not substitute a Join button from an existing chat or calendar event when the caller asks to create an instant meeting.

## Actions

Canonical action source: `actions/_meeting.py`.

Supported config actions:

- `start-instant-meeting`: open Teams, follow the canonical path, and verify in-call state.
- `status`: report whether the active Teams page is in pre-join or in-call.
- `leave`: leave the active meeting when one is in progress.

If Teams reports that the account is already in another call and the requested instant meeting cannot reach pre-join, fail with evidence rather than manipulating unrelated tabs.

## Verification

See `manifest.yaml`. The instant-meeting path, in-call detection, and exit were live-verified on 2026-10-01.
