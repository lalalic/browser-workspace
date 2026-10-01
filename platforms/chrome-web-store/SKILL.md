---
name: chrome-web-store-platform
description: "Chrome Web Store platform flows for Browser Workspace platform bundle."
---

# Chrome Web Store

Use the parent Browser Workspace skill contract first.
These assets document the verified platform contract and use the
Browser Workspace session runner as the reusable interaction boundary. Live actions still
require explicit authorization and report observed evidence instead of
inferring success.

Use only the publisher account and listing explicitly selected by the caller.
Publishing and listing updates have external side effects and require an
explicit user request.

## Runner

Invoke `runner/_chrome_web_store.py` through `Browser Workspace session` with
an approved JSON configuration. The supported actions are:

`resolve-item`, `create-item`, `open-item`, `upload-package`, `update-listing`, `verify-draft`, `save-draft`, `submit-review`,
`check-status`, and `verify-published`.

The runner is dry-run by default. `upload-package`, `update-listing`, and
`submit-review` require `commit: true`; `submit-review` additionally requires
the caller to explicitly opt in with `allow_external_submit: true`. This keeps
Release Agent responsible for authorization while this skill owns browser
mechanics. Every action emits a JSON evidence record containing the observed
URL, item id, action, and status (`draft`, `submitted`, `pending`, `rejected`,
`published`, or `unknown`).

`create-item` supports the no-existing-item path: it validates the explicit
package, opens the publisher-scoped dashboard, creates the item only with
`commit: true`, and returns the observed editor item id. `resolve-item` reuses a
matching product item and dry-runs creation when none exists. `verify-draft`
reopens the exact item and proves the dashboard version; `save-draft` is the
reusable no-field-change regression action. Passing a prior item id always
reopens/reuses it, so retries do not create duplicates.

The input `market_package` is product-owned content supplied by Market Agent;
this skill validates presence and maps supplied values to store fields but does
not invent copy or media. It accepts title, short/long description, release
notes, reviewer test instructions, support/privacy URLs, privacy/data-use
declarations, distribution/payment designation, permissions and host
justifications, screenshots, posters/feature graphics, and demo video.
`package_path` and `expected_version` are required for package upload; the ZIP's
`manifest.json` version must match before browser interaction begins.
