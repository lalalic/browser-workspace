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

SB = 'document.querySelector("wujie-app").shadowRoot.querySelector("body")'

def open_or_reuse_wechat(url):
    current = current_tab()
    tabs = [tab for tab in list_tabs() if urlparse(tab.get("url") or "").hostname == "channels.weixin.qq.com"]
    target = current if urlparse(current.get("url") or "").hostname == "channels.weixin.qq.com" else (tabs[0] if tabs else None)
    if target is None:
        new_tab(url)
        return current_tab()
    switch_tab(target)
    if page_info().get("url") != url:
        goto_url(url)
    return current_tab()

def shadow_js(expr):
    return js(SB + expr)

def find_rect(sel):
    code = SB + '.querySelector("' + sel + '") ? (function(){ var r = ' + SB + '.querySelector("' + sel + '").getBoundingClientRect(); return JSON.stringify({x:Math.round(r.x+r.width/2), y:Math.round(r.y+r.height/2)}); })() : "null"'
    r = js(code)
    if r and r != "null":
        return json.loads(r)
    return None

print("[1/6] Opening or reusing the WeChat Channels create tab...")
open_or_reuse_wechat("https://channels.weixin.qq.com/platform/post/create")
wait_for_load()
time.sleep(4)

url = page_info()["url"]
if "login" in url.lower():
    print("ERROR: Not logged in. Scan QR at https://channels.weixin.qq.com/")
    capture_screenshot()
    raise SystemExit(1)

for i in range(10):
    sc = js('document.querySelector("wujie-app")?.shadowRoot ? "ok" : "no"')
    if sc == "ok":
        break
    time.sleep(1)
else:
    print("ERROR: Shadow DOM not found after 10s.")
    capture_screenshot()
    raise SystemExit(1)

for i in range(10):
    has_upload = shadow_js('.querySelector(".upload") ? "ok" : "no"')
    if has_upload == "ok":
        break
    time.sleep(1)
else:
    print("ERROR: Upload area not found.")
    capture_screenshot()
    raise SystemExit(1)

print("  -> Logged in, page loaded.")

print("[2/6] Uploading video: " + CFG["video"])
doc = cdp("DOM.getDocument", depth=-1, pierce=True)
sr = cdp("DOM.performSearch", query='input[type="file"][accept*="video"]')
if sr.get("resultCount", 0) > 0:
    nodes = cdp("DOM.getSearchResults", searchId=sr["searchId"], fromIndex=0, toIndex=1)
    nid = nodes["nodeIds"][0]
    cdp("DOM.setFileInputFiles", files=[CFG["video"]], nodeId=nid)
    cdp("DOM.discardSearchResults", searchId=sr["searchId"])
    print("  -> Video file set via DOM.")
else:
    print("ERROR: Cannot find video file input.")
    capture_screenshot()
    raise SystemExit(1)

print("  -> Waiting for upload...")
for attempt in range(120):
    time.sleep(5)
    btn_cls = shadow_js('.querySelector(".weui-desktop-btn_primary")?.classList?.contains("weui-desktop-btn_disabled") ? "disabled" : "enabled"')
    vid_ok = shadow_js('.querySelector(".cover-wrap, video, [class*=uploaded], [class*=video-info], .upload-success, .post-edit-wrap") ? "ready" : "wait"')
    if vid_ok == "ready" or btn_cls == "enabled":
        print("  -> Upload done!")
        break
    if attempt % 6 == 5:
        pct = shadow_js('.querySelector("[class*=progress], .percent")?.textContent || "..."')
        print("  -> Uploading... " + str(pct) + " (" + str((attempt+1)*5) + "s)")
else:
    print("WARNING: Upload timeout.")
    capture_screenshot()
time.sleep(2)

print("[3/6] Setting description...")
tags = CFG.get("tags", [])
desc = CFG["desc"]
if tags:
    desc = desc + " " + " ".join(f"#{t}" for t in tags)
desc_s = json.dumps(desc)
shadow_js('.querySelector(".input-editor[contenteditable=true]")?.focus()')
time.sleep(0.3)
js(SB + '.querySelector(".input-editor").textContent = ' + desc_s)
js(SB + '.querySelector(".input-editor").dispatchEvent(new Event("input", {bubbles:true}))')
time.sleep(0.5)
actual = shadow_js('.querySelector(".input-editor")?.textContent?.substring(0,50) || ""')
if actual:
    print("  -> Description: " + actual)
else:
    print("  -> WARNING: Description may not have been set, trying click+type...")
    c = find_rect(".input-editor")
    if c:
        click_at_xy(c["x"], c["y"])
        time.sleep(0.5)
        type_text(CFG["desc"])
        time.sleep(0.5)

if CFG["title"]:
    print("[4/6] Setting short title: " + CFG["title"])
    title_s = json.dumps(CFG["title"])
    shadow_js('.querySelector(".weui-desktop-form__input")?.focus()')
    time.sleep(0.2)
    js('Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(' + SB + '.querySelector(".weui-desktop-form__input"), ' + title_s + ')')
    js(SB + '.querySelector(".weui-desktop-form__input").dispatchEvent(new Event("input", {bubbles:true}))')
    time.sleep(0.3)
else:
    print("[4/6] No short title, skipping...")

# Scroll down to make buttons visible
shadow_js('.scrollTo(0, 99999)')
js('document.querySelector("wujie-app").shadowRoot.querySelector("html")?.scrollTo(0, 99999)')
time.sleep(1)

print("[5/6] Pre-action screenshot...")
capture_screenshot()
time.sleep(1)

def find_btn_by_text(text):
    # Find a visible button by its text content (avoids matching hidden dialog buttons)
    r = js(SB + '.querySelectorAll(".weui-desktop-btn").forEach(function(b){}); var found=null; ' + SB + '.querySelectorAll(".weui-desktop-btn").forEach(function(b){ var rect=b.getBoundingClientRect(); if(b.textContent.trim()==="' + text + '" && rect.width>0 && !b.classList.contains("weui-desktop-btn_disabled")){ found={x:Math.round(rect.x+rect.width/2), y:Math.round(rect.y+rect.height/2)}; }}); found ? JSON.stringify(found) : "null"')
    if r and r != "null":
        return json.loads(r)
    return None

if CFG["publish"]:
    print("[6/6] Publishing...")
    c = find_btn_by_text("\u53d1\u8868")  # 发表
    if c:
        click_at_xy(c["x"], c["y"])
        time.sleep(3)
        # Handle confirmation dialog
        shadow_js('.querySelectorAll(".weui-desktop-dialog__wrp").forEach(function(d){ if(d.style.display !== "none"){ var b = d.querySelector(".weui-desktop-btn_primary"); if(b) b.click(); }})')
        time.sleep(3)
        print("  -> Publish action submitted; verifying manager state...")
        action = "publish"
    else:
        print("ERROR: Publish button disabled/not found. Check manager before retrying.")
        capture_screenshot()
        raise SystemExit(1)
else:
    print("[6/6] Saving draft...")
    c = find_btn_by_text("\u4fdd\u5b58\u8349\u7a3f")  # 保存草稿
    if c:
        click_at_xy(c["x"], c["y"])
        time.sleep(3)
        print("  -> Draft action submitted; verifying manager state...")
        action = "draft"
    else:
        print("ERROR: Save draft button disabled/not found. Check manager before retrying.")
        capture_screenshot()
        raise SystemExit(1)

def verify_manager():
    open_or_reuse_wechat(MANAGER_URL)
    expected_title = CFG.get("title") or ""
    expected_desc = CFG.get("desc") or ""
    deadline = time.time() + 40
    content_deadline = time.time() + 15
    while time.time() < deadline:
        ready = js('document.querySelector("wujie-app")?.shadowRoot?.querySelector("body") ? "yes" : "no"') == "yes"
        if ready:
            raw = js(manager_scan_expression("", expected_title, expected_desc)) or "[]"
            try:
                rows = json.loads(raw)
            except json.JSONDecodeError:
                rows = []
            row = choose_manager_row(rows, None, expected_title, expected_desc)
            if row:
                status, label = status_label(row.get("text", ""))
                return {
                    "status": status or "unknown",
                    "status_label": label,
                    "post_id": extract_stable_id(row),
                    "row": row,
                    "reason": None if status else "status_label_not_found",
                }
            has_content = bool(js('document.querySelector("wujie-app")?.shadowRoot?.querySelector("body")?.innerText?.trim() || ""'))
            if has_content and time.time() >= content_deadline:
                return {"status": "not_found", "status_label": None, "post_id": None, "row": None, "reason": "no_matching_manager_row"}
        time.sleep(1)
    return {"status": "unknown", "status_label": None, "post_id": None, "row": None, "reason": "manager_did_not_load"}

verification = verify_manager()
result = {
    "ok": verification["status"] in {"published", "reviewing"} if action == "publish" else verification["status"] == "draft",
    "platform": "wechat-channels",
    "operation": action,
    "status": verification["status"],
    "status_label": verification["status_label"],
    "post_id": verification["post_id"],
    "title": CFG.get("title"),
    "desc": CFG.get("desc"),
    "verified": verification["status"] in {"published", "reviewing", "rejected", "draft"},
    "reason": verification["reason"],
    "row": verification["row"],
    "retry_safe": False,
}
print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
time.sleep(1)
capture_screenshot()
if not result["ok"]:
    raise SystemExit(7 if verification["status"] in {"unknown", "not_found"} else 8)

print("Done!")
