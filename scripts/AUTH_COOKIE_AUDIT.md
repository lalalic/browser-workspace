# Local Chrome authentication lifecycle audit

This read-only collector operates on the **existing** Browser Workspace Chrome
profile (`~/.config/browser-workspace/chrome/Default/Cookies`). It does **not**
start Chrome, change cookies, inject JavaScript, navigate pages, or authenticate.

Installed locally as:

- `~/.config/browser-workspace/tasks/auth-cookie-audit.py`
- `~/.config/browser-workspace/tasks/auth-cookie-audit-cron.sh`
- cron every 15 minutes, independent of the existing 2-hour page checks
- private state and history: `~/.config/browser-workspace/auth-audit/`

Read-only SQLite access includes committed WAL data. Captured fields: site,
host, opaque per-cookie identifier, HMAC of the encrypted value, cookie
creation/update/access times, expiry time, persistence, SameSite, Secure,
HttpOnly, and partition state. Raw values, plaintext tokens, account IDs, and
Cookie headers are never written to logs. The local HMAC key has mode 0600;
losing it prevents comparison with older fingerprints. Do not upload the key
or the private state to issue trackers or external services.

`events.jsonl` contains timestamped counts, earliest future expiration, and
added/removed/rotated/extended statistics. `latest.json` enables comparisons
with the previous read. Both are owner-only files; `collector.log` contains
only aggregate events. The first run is a baseline, so all current entries
appear as newly added.

Run manually:

```sh
/usr/bin/python3 ~/.config/browser-workspace/tasks/auth-cookie-audit.py
```

To annotate a **separately verified** page check, run after it:

```sh
/usr/bin/python3 ~/.config/browser-workspace/tasks/auth-cookie-audit.py --site wechat --status logged_in
/usr/bin/python3 ~/.config/browser-workspace/tasks/auth-cookie-audit.py --site google_store --status login_required
```

These annotations record a *human/agent-observed* status, not a status inferred
from cookies. The scheduled sampler uses `unknown`, because Cookie presence
cannot prove server-side login. Correlate the next failed UI check with the
preceding sampler events to distinguish missing/expired cookies, rolling
renewals, and server-side validation or forced reauthentication. An unchanged,
unexpired Cookie does not prove a server session is valid. Google's earliest
Cookie expiry may belong to an unrelated cookie, not the authentication token.

To remove the sampler, delete only its crontab entry. Do **not** delete or
restart the Chrome profile, daemon, or existing page-check schedule.
