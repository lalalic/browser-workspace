---
name: microsoft-teams-platform
description: "Microsoft Teams meeting browser mechanics for Browser Workspace platform bundle."
---

# Microsoft Teams

Use the parent Browser Workspace skill contract first.
Use Browser Workspace as the only browser-control engine.

## Canonical instant-meeting path

For automated meeting E2E, use exactly this Teams UI path:

`left sidebar Calendar -> Meet now -> Start meeting (when shown) -> pre-join -> Join now -> in-call`

Do not substitute a Join button from an existing chat or calendar event when the
caller asks to create an instant meeting.

## Runner

Invoke `runner/_meeting.py` through one Browser Workspace session.
Supported actions:

- `start-instant-meeting`: acquire a Teams tab, open Calendar, click Meet now,
  wait for pre-join, click Join now, and verify the in-call state.
- `status`: report whether the current leased Teams tab is in pre-join or in-call.
- `leave`: leave the meeting in the current leased Teams tab.

`start-instant-meeting` deliberately performs the whole navigation in one
Browser Workspace session. Browser Workspace owns tab identity and leasing; this
platform flow must not recover tabs by URL or use raw CDP outside Browser
Harness.

If Teams reports that the account is already in another call and the requested
instant meeting cannot reach pre-join, fail with evidence rather than touching
another browser tab. Callers may only clean up meeting tabs they themselves
leased.
