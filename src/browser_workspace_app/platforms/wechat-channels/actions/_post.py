import json
import os
import time
from urllib.parse import urlparse

from _common import (
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
    upload_state = js(SB + '.innerText ? (function(text){ var match=text.match(/(?:^|\\n)(\\d{1,3})%(?:\\n|$)/); var percent=match?parseInt(match[1],10):null; var uploading=text.indexOf(\"取消上传\")>=0; return JSON.stringify({percent:percent,uploading:uploading}); })(' + SB + '.innerText) : JSON.stringify({percent:null,uploading:false})')
    try:
        state = json.loads(upload_state or "{}")
    except Exception:
        state = {}
    # Do not infer completion from editor/preview presence or Publish enabled state:
    # those can appear while the video is still uploading.
    if state.get("percent") is None and not state.get("uploading"):
        print("  -> Upload done!")
        break
    if attempt % 3 == 2:
        pct = state.get("percent")
        print("  -> Uploading... " + ((str(pct) + "%") if pct is not None else "processing") + " (" + str((attempt+1)*5) + "s)")
else:
    print("ERROR: Upload did not reach a completed state before timeout.")
    capture_screenshot()
    raise SystemExit(1)
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
    print("  -> WARNING: Description may not have been set; retrying through the semantic editor element...")
    retry_desc = json.dumps(CFG["desc"])
    js(SB + '.querySelector(".input-editor")?.focus()')
    js(SB + '.querySelector(".input-editor").textContent = ' + retry_desc)
    js(SB + '.querySelector(".input-editor").dispatchEvent(new Event("input", {bubbles:true}))')
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
print("[5/6] Pre-action screenshot...")
capture_screenshot()
time.sleep(1)

def click_btn_by_text(text):
    # Semantic DOM click only. Never derive or use viewport/screen coordinates.
    text_s = json.dumps(text)
    return js(
        '(function(){ var body=' + SB + '; var target=null; '
        'body.querySelectorAll(".weui-desktop-btn").forEach(function(btn){ '
        'var style=getComputedStyle(btn); '
        'if(btn.textContent.trim()===' + text_s + ' && '
        '!btn.disabled && !btn.classList.contains("weui-desktop-btn_disabled") && '
        'style.display!=="none" && style.visibility!=="hidden"){ target=btn; } }); '
        'if(!target) return false; target.click(); return true; })()'
    )


if CFG["publish"]:
    print("[6/6] Publishing...")
    clicked = click_btn_by_text("发表")
    if clicked:
        time.sleep(3)
        # Handle confirmation dialog semantically as well.
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
    clicked = click_btn_by_text("保存草稿")
    if clicked:
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
