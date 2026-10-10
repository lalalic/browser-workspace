# Authentication Cookie lifecycle audit

Read-only sampler of the existing Browser Workspace Chrome profile. Does not
start Chrome, change cookies, authenticate, or navigate pages.

Installed as `~/.config/browser-workspace/tasks/auth-cookie-audit.py` and
`auth-cookie-audit-cron.sh`, running every 15 minutes alongside the existing
2-hour page checks. Owner-private history and state live in
`~/.config/browser-workspace/auth-audit/`.

Records Cookie domain, opaque HMAC ID, HMAC fingerprint of encrypted Cookie
value, expiration, creation/update/access timestamps, and security flags.
Never logs raw Cookie values, passwords, tokens, or complete Cookie headers.
The 0600 HMAC key must stay local. The first run establishes a baseline.

`events.jsonl` records changes (added/removed/rotated/expiry extended), counts,
and earliest unexpired Cookie; `latest.json` holds the previous fingerprint
baseline. Presence or an unexpired Cookie cannot prove server-side login.
Actual logged-in / login-required observations can be annotated by invoking
`auth-cookie-audit.py --site wechat --status logged_in` or corresponding
`google_store`, `xiaohongshu` and `login_required` status values, after an
independent UI check. Automatic samplers leave status unknown.

Compare the last successful and first failed page-check timestamps with nearby
Cookie changes. No attempt is made to bypass reauthentication or to force
renewal. Early expiration may belong to non-authentication cookies.
