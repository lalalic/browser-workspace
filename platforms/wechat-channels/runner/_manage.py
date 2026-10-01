import json
import os
import sys
import time
from urllib.parse import urlparse

sys.path.insert(0, "__ADAPTER_DIR__")
from _common_bh import (
    MANAGER_URL,
    choose_manager_row,
    extract_stable_id,
    manager_scan_expression,
    status_label,
)

CFG = json.load(open("__CFG_PATH__"))
OP = CFG["operation"]
POST_ID = CFG.get("post_id")
TITLE = CFG.get("title")
DESC = CFG.get("desc")


def out(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


def open_or_reuse_wechat(url: str) -> dict:
    current = current_tab()
    tabs = [
        tab
        for tab in list_tabs()
        if urlparse(tab.get("url") or "").hostname == "channels.weixin.qq.com"
    ]
    target = (
        current
        if urlparse(current.get("url") or "").hostname == "channels.weixin.qq.com"
        else tabs[0] if tabs else None
    )
    if target is None:
        new_tab(url)
        return current_tab()
    switch_tab(target)
    if page_info().get("url") != url:
        goto_url(url)
    return current_tab()


def wait_for_shadow(timeout_seconds: int = 20) -> bool:
    expression = (
        'document.querySelector("wujie-app")?.shadowRoot?.querySelector("body") '
        '? "yes" : "no"'
    )
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if js(expression) == "yes":
            return True
        time.sleep(0.5)
    return False


def manager_has_content() -> bool:
    expression = (
        '(document.querySelector("wujie-app")?.shadowRoot?.querySelector("body")'
        '?.innerText || "").trim()'
    )
    return bool(js(expression))


def manager_rows(
    post_id: str | None,
    title: str | None,
    desc: str | None,
) -> list[dict]:
    try:
        raw = json.loads(js(manager_scan_expression(post_id, title, desc)) or "[]")
    except (TypeError, json.JSONDecodeError):
        return []
    return raw if isinstance(raw, list) else []


def resolve_manager() -> tuple[str, dict]:
    open_or_reuse_wechat(MANAGER_URL)
    if not wait_for_shadow():
        return "unknown", {"reason": "manager_shadow_root_missing"}
    deadline = time.monotonic() + 30
    content_deadline = time.monotonic() + 12
    row = None
    while time.monotonic() < deadline:
        rows = manager_rows(POST_ID, TITLE, DESC)
        row = choose_manager_row(rows, POST_ID, TITLE, DESC)
        if row is not None:
            break
        if manager_has_content() and time.monotonic() >= content_deadline:
            return "not_found", {"reason": "no_matching_manager_row"}
        time.sleep(1)
    if row is None:
        return "unknown", {"reason": "manager_did_not_load"}
    status, label = status_label(row.get("text", ""))
    return status or "unknown", {
        "reason": None if status else "status_label_not_found",
        "row": row,
        "post_id": extract_stable_id(row) or POST_ID,
        "status_label": label,
    }


if OP != "status":
    out(
        {
            "ok": False,
            "platform": "wechat-channels",
            "operation": OP,
            "error": "unsupported_operation",
            "supported_operations": ["status"],
        }
    )
    raise SystemExit(2)

status, details = resolve_manager()
result = {
    "ok": status in {"published", "reviewing", "rejected", "draft"},
    "platform": "wechat-channels",
    "operation": "status",
    "status": status,
    "post_id": details.get("post_id"),
    "status_label": details.get("status_label"),
    "target": {"post_id": POST_ID, "title": TITLE, "desc": DESC},
    "reason": details.get("reason"),
    "row": details.get("row"),
}
out(result)
raise SystemExit(0 if result["ok"] else 2)
