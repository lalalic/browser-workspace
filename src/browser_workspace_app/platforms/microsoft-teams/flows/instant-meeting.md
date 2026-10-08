# Instant meeting

Status: `verified` on 2026-10-01.

Preconditions:
- Microsoft Teams is already authenticated in the browser context.
- The action may create and join a real meeting.

Canonical flow:
1. Open `https://teams.cloud.microsoft/`.
2. Wait for the left application rail.
3. Click **Calendar**.
4. Resolve the hosted calendar target/iframe when required.
5. Click **Meet now**.
6. If the intermediate dialog appears, click **Start meeting**.
7. Wait for pre-join.
8. Click **Join now**.
9. Verify in-call state using call duration or hangup controls.
10. When cleanup is requested, click leave/hangup and verify the call controls disappear.

Do not identify browser ownership by URL. Do not touch unrelated tabs when the account is already in another call.
