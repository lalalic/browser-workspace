# Instant meeting

## Preconditions

- Browser Workspace and Browser Workspace are available.
- The browser session is already authenticated to Microsoft Teams.
- The caller is allowed to create/join a real test meeting.
- The caller owns the leased Teams tab used for this flow.

## Interaction

1. Acquire/open `https://teams.cloud.microsoft/` through Browser Workspace.
2. Wait for the left application rail to expose `Calendar`.
3. Click the left-side `Calendar` control.
4. Resolve the hosted calendar iframe belonging to the leased Teams page.
5. Click the calendar `Meet now` control (`Start an instant Teams meeting.`).
6. If Teams opens the `Start a meeting now` dialog, click `Start meeting`.
7. Wait for Teams pre-join and verify `Join now` is present.
8. Click `Join now`.
9. Verify in-call state using call duration or the hangup/leave control.

Do not replace steps 2-5 with an existing-chat `Join` button.

## Verification

Success requires observed pre-join followed by an observed in-call state in the
same leased Teams tab. Return the observed title, call duration, and whether the
hangup control exists.

## Side effects

This creates and joins a real Teams meeting. `leave` exits only the caller-owned
leased meeting tab.
