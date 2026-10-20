"""Non-mutating ChatGPT readiness diagnostic for caller-owned sessions."""
import json
from urllib.parse import urlsplit
import _lifecycle_common as common
from _readiness import wait_until_stable

common.js = js

def observe():
    info = page_info()
    url = info.get("url", "")
    selector = common.composer_selector()
    return {
        "host": urlsplit(url).hostname,
        "path": urlsplit(url).path,
        "composer_ready": bool(selector),
        "generating": common.is_generating(),
        "delivery_error": common.visible_delivery_error(),
    }

# A successful check returns true. A failed check returns one stable error ID.
try:
    wait_for_load()
    wait_until_stable(
        observe,
        lambda x: x["host"] == "chatgpt.com" and x["composer_ready"] and not x["delivery_error"],
        timeout=12, phase="platform validation",
    )
    print(json.dumps(True), flush=True)
except Exception:
    try:
        state = observe()
        if state["delivery_error"]:
            failure_id = "DELIVERY_ERROR"
        elif state["host"] != "chatgpt.com":
            failure_id = "PAGE_NOT_READY"
        elif not state["composer_ready"]:
            failure_id = "COMPOSER_NOT_READY"
        else:
            failure_id = "PAGE_NOT_READY"
    except Exception:
        failure_id = "PAGE_NOT_READY"
    print(json.dumps(failure_id), flush=True)
