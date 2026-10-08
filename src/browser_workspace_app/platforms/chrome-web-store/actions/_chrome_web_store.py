"""Chrome Web Store browser mechanics.

This action contains no credentials and defaults to read-only/dry-run behavior.
"""

import json
import re
import time
import zipfile


CFG = json.load(open("__CFG_PATH__", encoding="utf-8"))
ACTION = CFG["action"]
ITEM_ID = CFG.get("item_id", "").strip()
PRODUCT_NAME = CFG.get("product_name", "").strip()
EXPECTED_VERSION = CFG.get("expected_version", "").strip()
PUBLIC_LISTING_URL = CFG.get("public_listing_url", "").strip()
LISTING_URL = CFG.get("listing_url", "").strip()
COMMIT = bool(CFG.get("commit", False))
ALLOW_EXTERNAL_SUBMIT = bool(CFG.get("allow_external_submit", False))

CONSOLE_URL = "https://chromewebstore.google.com/devconsole"
ALLOWED_ACTIONS = {
    "open-item",
    "resolve-item",
    "create-item",
    "verify-draft",
    "save-draft",
    "upload-package",
    "update-listing",
    "submit-review",
    "check-status",
    "verify-published",
}
STATES = {"draft", "submitted", "pending", "rejected", "published", "unknown"}


def fail(message):
    print(json.dumps({"action": ACTION, "status": "unknown", "error": message}))
    raise SystemExit(2)


def package_version(path):
    try:
        with zipfile.ZipFile(path) as package:
            manifest = json.loads(package.read("manifest.json"))
    except (OSError, KeyError, ValueError, zipfile.BadZipFile) as exc:
        fail(f"invalid extension package: {exc}")
    version = str(manifest.get("version", "")).strip()
    if not version:
        fail("package manifest is missing version")
    return version


def validate_package():
    package = CFG.get("package_path", "").strip()
    if not package:
        fail("package_path is required")
    if not EXPECTED_VERSION:
        fail("expected_version is required")
    observed = package_version(package)
    if observed != EXPECTED_VERSION:
        fail(f"package version {observed} does not match expected_version {EXPECTED_VERSION}")
    return observed


def evidence(status, **extra):
    if status not in STATES:
        fail(f"invalid evidence status: {status}")
    record = {
        "action": ACTION,
        "status": status,
        "item_id": ITEM_ID or None,
        "url": page_info().get("url"),
        **extra,
    }
    print(json.dumps(record, ensure_ascii=False))
    return record


def text_exists(needles):
    values = json.dumps([n.lower() for n in needles])
    return js(
        """(() => {
          const text = (document.body?.innerText || '').toLowerCase();
          return %s.some(value => text.includes(value));
        })()""" % values
    ) is True


def visible_version():
    value = js("""(() => document.body?.innerText || '')()""") or ""
    versions = re.findall(r"\b\d+\.\d+(?:\.\d+){1,2}\b", value)
    return EXPECTED_VERSION if EXPECTED_VERSION in versions else (versions[0] if versions else None)


def click_text(label):
    wanted = label.lower()
    return js(
        """(() => {
          const nodes = [...document.querySelectorAll('button,[role=button],a')];
          const node = nodes.find(el => {
            const text = (el.innerText || el.getAttribute('aria-label') || '').trim().toLowerCase();
            return text === %r || text.includes(%r);
          });
          if (!node) return false;
          node.click();
          return true;
        })()""" % (wanted, wanted)
    ) is True


def field_by_label(keys):
    """Find a form control by its accessible/visible label, not generated IDs."""
    return js(
        """(() => {
          const keys = %s;
          const controls = [...document.querySelectorAll('input,textarea,select,[role=combobox],[contenteditable=true]')];
          const labelText = (node) => {
            const ids = (node.getAttribute('aria-labelledby') || '').split(/\\s+/).filter(Boolean);
            const labelled = ids.map(id => document.getElementById(id)?.innerText || '').join(' ');
            const explicit = node.id ? document.querySelector(`label[for="${CSS.escape(node.id)}"]`)?.innerText || '' : '';
            const parent = node.closest('label')?.innerText || node.parentElement?.innerText || '';
            return [node.getAttribute('aria-label'), node.getAttribute('placeholder'), node.name, node.id,
                    labelled, explicit, parent].filter(Boolean).join(' ').toLowerCase();
          };
          const node = controls.find(node => keys.some(key => labelText(node).includes(key)));
          return node?.id ? `#${CSS.escape(node.id)}` : null;
        })()""" % json.dumps([key.lower() for key in keys])
    )


def require_publisher_login():
    url = page_info().get("url", "")
    if "accounts.google.com" in url or text_exists(["sign in", "log in"]):
        fail("authenticated Chrome Web Store publisher login required")


def publisher_id_from_url(url):
    match = re.search(
        r"https://(?:chrome\.google\.com/webstore/devconsole|chromewebstore\.google\.com/devconsole)/([^/]+)(?:/|$)",
        url,
    )
    return match.group(1) if match else None


def open_item():
    if ACTION == "verify-published":
        url = PUBLIC_LISTING_URL or ("https://chromewebstore.google.com/detail/" + ITEM_ID)
    else:
        url = LISTING_URL
        if not url:
            publisher_id = publisher_id_from_url(page_info().get("url", ""))
            if not publisher_id:
                # The canonical console URL redirects to the publisher-scoped
                # dashboard. Resolve that scope before constructing an item
                # route; the generic /store-item path redirects to the public
                # store and cannot prove the requested item was opened.
                goto_url(CONSOLE_URL)
                wait_for_load()
                require_publisher_login()
                publisher_id = publisher_id_from_url(page_info().get("url", ""))
            if not publisher_id:
                fail("publisher-scoped developer console route not observed")
            url = f"https://chrome.google.com/webstore/devconsole/{publisher_id}/{ITEM_ID}/edit"
    # Browser automation can briefly expose more than one target for a
    # requested URL. Reuse the harness-verified real tab instead of asking the
    # browser controller to create another target; this keeps navigation stable
    # without changing unrelated browser state.
    if ensure_real_tab():
        goto_url(url)
    else:
        # A fresh isolated browser may not have a usable page yet.
        new_tab(url)
    wait_for_load()
    require_publisher_login()
    if ITEM_ID and ITEM_ID not in page_info().get("url", ""):
        fail("observed URL does not contain the requested item id")
    return evidence("unknown", observed_item_id=ITEM_ID or None)


def dashboard_candidates():
    return js("""(() => [...document.querySelectorAll('a[href]')].map(node => ({href: node.href, text: (node.innerText || node.getAttribute('aria-label') || '').trim()})).filter(item => /\\/devconsole\\/[^/]+\\/[a-z]{32}/.test(item.href)))()""") or []


def item_id_from_url(url):
    match = re.search(r"/devconsole/[^/]+/([a-z]{32})/(?:edit|details)?(?:[/?#]|$)", url)
    return match.group(1) if match else None


def dashboard_item_version(item_id):
    for candidate in dashboard_candidates():
        if item_id in candidate.get("href", ""):
            versions = re.findall(r"\b\d+\.\d+(?:\.\d+){1,2}\b", candidate.get("text", ""))
            return versions[0] if versions else None
    return None


def open_dashboard():
    goto_url(CONSOLE_URL)
    wait_for_load()
    require_publisher_login()


def create_or_resolve_item():
    global ITEM_ID
    if ITEM_ID:
        open_item()
        return evidence("draft", observed_item_id=ITEM_ID, reused_item=True)
    if not PRODUCT_NAME:
        fail("product_name is required when item_id is not supplied")
    open_dashboard()
    wanted = PRODUCT_NAME.lower()
    for candidate in dashboard_candidates():
        if wanted in candidate.get("text", "").lower():
            ITEM_ID = item_id_from_url(candidate.get("href", ""))
            if ITEM_ID:
                return evidence("draft", observed_item_id=ITEM_ID, reused_item=True, listing_url=candidate.get("href"))
    if not COMMIT:
        return evidence("draft", dry_run=True, would_create=True, product_name=PRODUCT_NAME)
    create_item()
    ITEM_ID = item_id_from_url(page_info().get("url", ""))
    return evidence("draft", created_item=True, observed_item_id=ITEM_ID, package_version=EXPECTED_VERSION,
                    browser_version=visible_version(), version_verification="reopen-required")


def verify_draft():
    validate_package()
    open_item()
    if not text_exists(["status: draft", "draft"]):
        fail("draft status not observed after reopening exact item")
    open_dashboard()
    observed = dashboard_item_version(ITEM_ID)
    if observed != EXPECTED_VERSION:
        fail(f"reopened draft version {observed or 'unknown'} does not match expected_version {EXPECTED_VERSION}")
    return evidence("draft", observed_item_id=ITEM_ID, observed_version=observed, exact_version_verified=True, reopened=True)


def save_draft():
    open_item()
    if not click_text("Save draft") and not click_text("Save"):
        fail("save draft control not observed")
    return evidence("draft", saved=True, observed_item_id=ITEM_ID)


def create_item():
    observed_version = validate_package()
    if not COMMIT:
        return evidence("draft", dry_run=True, would_create=True,
                        package_path=CFG["package_path"], package_version=observed_version)
    goto_url(CONSOLE_URL)
    wait_for_load()
    require_publisher_login()
    if not publisher_id_from_url(page_info().get("url", "")):
        fail("publisher-scoped developer console route not observed")
    if not click_text("New item") and not click_text("Add a new item"):
        fail("new item control not observed")
    upload_file("input[type=file]", CFG["package_path"].strip())
    wait_for_load()
    require_publisher_login()
    if text_exists(["key field is not allowed"]):
        fail("new item upload rejected: manifest key field is not allowed")
    if text_exists(["there was a problem uploading your file"]):
        fail("new item upload rejected by Chrome Web Store")
    url = page_info().get("url", "")
    match = re.search(r"/devconsole/[^/]+/([^/]+)/edit(?:$|[?#])", url)
    if not match:
        fail("created item editor route not observed")
    return evidence("draft", created_item_id=match.group(1),
                    package_version=observed_version, browser_version=visible_version())


def upload_package():
    package = CFG["package_path"].strip()
    observed_version = validate_package()
    if not COMMIT:
        return evidence("draft", dry_run=True, would_upload=package, package_version=observed_version)
    if not click_text("Package") and not click_text("Upload new package"):
        fail("package upload control not observed")
    upload_file("input[type=file]", package)
    time.sleep(2)
    browser_version = visible_version()
    if browser_version != observed_version:
        fail(f"uploaded package version {browser_version or 'unknown'} does not match expected_version {observed_version}")
    return evidence("draft", uploaded_package=package, package_version=observed_version,
                    browser_version=browser_version)


def update_listing():
    market = CFG.get("market_package") or {}
    required = ["title", "short_description", "long_description", "support_url"]
    missing = [key for key in required if not str(market.get(key, "")).strip()]
    if missing:
        fail("market_package missing: " + ", ".join(missing))
    if not COMMIT:
        return evidence("draft", dry_run=True, fields=sorted(market))
    # Chrome's editor is a dynamic form. Use labels/aria names rather than
    # brittle generated class names; the caller still receives observed evidence.
    mapped = {key: market[key] for key in market if market[key] not in (None, "", [], {})}
    selectors = {
        "short_description": ["short description", "summary"],
        "long_description": ["long description", "description"],
        "release_notes": ["release notes", "what's new"],
        "reviewer_test_instructions": ["reviewer", "test instructions"],
        "support_url": ["support url", "support website"],
        "privacy_policy_url": ["privacy policy", "privacy url"],
        "privacy_practices": ["privacy practices", "privacy"],
        "data_use": ["data use", "data usage"],
        "distribution": ["distribution", "visibility"],
        "payment": ["payment", "paid"],
        "permissions": ["permissions", "permission justification"],
        "host_permissions": ["host permissions", "host permission"],
        "host_permission_justifications": ["host permission justification", "host permissions"],
        "title": ["title", "name"],
    }
    for label, value in mapped.items():
        if label in {"screenshots", "posters", "feature_graphic", "promotional_graphic", "demo_video"}:
            continue
        keys = selectors.get(label, [label.replace("_", " ")])
        node = field_by_label(keys)
        if not node and label in {"title", "short_description"}:
            # Chrome may expose package-owned title/summary as read-only text.
            # The caller supplied the factual value; verify other editable fields
            # without trying to mutate package metadata through a nonexistent control.
            continue
        if not node:
            fail(f"listing field not observed: {label}")
        changed = js(
            """(() => {
              const node = document.querySelector(%s);
              if (!node) return false;
              node.focus();
              if (node.type === 'checkbox' || node.type === 'radio') node.checked = Boolean(%s);
              else if (node.tagName === 'SELECT') {
                const wanted = String(%s).toLowerCase();
                const option = [...node.options].find(item => (item.text || item.value).toLowerCase() === wanted);
                if (!option) return false;
                node.value = option.value;
              } else if ('value' in node) node.value = %s;
              else node.textContent = %s;
              node.dispatchEvent(new Event('input', {bubbles: true}));
              node.dispatchEvent(new Event('change', {bubbles: true}));
              return true;
            })()""" % (json.dumps(str(node)), json.dumps(bool(value)), json.dumps(str(value)),
                           json.dumps(str(value)), json.dumps(str(value)))
        )
        if changed is not True:
            fail(f"listing field not observed: {label}")
    for field in ("screenshots", "posters", "feature_graphic", "promotional_graphic", "demo_video"):
        for media in (mapped.get(field) if isinstance(mapped.get(field), list) else [mapped.get(field)]):
            if media:
                try:
                    upload_file("input[type=file]", str(media))
                except (OSError, RuntimeError) as exc:
                    fail(f"listing media upload failed: {field}")
    if not click_text("Save draft") and not click_text("Save"):
        fail("save control not observed")
    return evidence("draft", fields=sorted(mapped))


def submit_review():
    if not COMMIT or not ALLOW_EXTERNAL_SUBMIT:
        return evidence("draft", blocked="explicit submit authorization required")
    if not click_text("Submit for review"):
        fail("submit-for-review control not observed")
    time.sleep(2)
    return evidence("submitted")


def check_status():
    if text_exists(["rejected", "needs changes"]):
        return evidence("rejected", observed_version=visible_version())
    if text_exists(["published", "public"]):
        return evidence("published", observed_version=visible_version())
    if text_exists(["submitted", "under review", "pending"]):
        return evidence("pending", observed_version=visible_version())
    return evidence("unknown", observed_version=visible_version())


def verify_published():
    url = page_info().get("url", "")
    if not url.startswith("https://chromewebstore.google.com/detail/"):
        return evidence("unknown", reason="public listing URL not observed")
    if ITEM_ID and ITEM_ID not in url:
        return evidence("unknown", reason="public URL does not match item id")
    observed = visible_version()
    if EXPECTED_VERSION and observed != EXPECTED_VERSION:
        return evidence("unknown", reason="expected version not observed")
    return evidence("published", expected_version=EXPECTED_VERSION or None, observed_version=observed)


if ACTION not in ALLOWED_ACTIONS:
    fail("unsupported action: " + ACTION)
if ACTION in {"resolve-item", "create-item"}:
    if ACTION == "create-item" and not (PRODUCT_NAME or ITEM_ID):
        fail("product_name is required for create-item")
    validate_package()
    create_or_resolve_item()
    raise SystemExit(0)
if ACTION in {"verify-draft", "save-draft", "upload-package", "update-listing", "submit-review", "check-status", "verify-published"} and not ITEM_ID:
    fail("item_id is required for this action")
if ACTION == "open-item" and not (ITEM_ID or LISTING_URL):
    fail("item_id or listing_url is required for open-item")
if ACTION in {"create-item", "upload-package"}:
    validate_package()

if ACTION == "verify-draft":
    verify_draft()
    raise SystemExit(0)
if ACTION == "save-draft":
    save_draft()
    raise SystemExit(0)
if ACTION == "upload-package":
    open_item()
    upload_package()
else:
    open_item()
if ACTION == "update-listing":
    update_listing()
elif ACTION == "submit-review":
    submit_review()
elif ACTION == "check-status":
    check_status()
elif ACTION == "verify-published":
    verify_published()
