import time, json, os

CFG = json.load(open("__CFG_PATH__"))

# NOTE: XHS overrides JSON.stringify (anti-bot). This script avoids it entirely.
# Use js() for scalar returns only; use .click() instead of click_at_xy with rects.

mode = CFG.get("mode", "image")

def open_or_reuse_xhs(url):
    current=current_tab()
    current_url=current.get("url","")
    if "xiaohongshu.com" in current_url:
        target=current
    else:
        tabs=[t for t in list_tabs() if "xiaohongshu.com" in (t.get("url") or "")]
        target=tabs[0] if tabs else None
    if target:
        switch_tab(target)
        if (current_tab().get("url") or "") != url:
            goto_url(url)
    else:
        new_tab(url)
    return current_tab()

images = CFG.get("images", [CFG.get("image", "")])
video = CFG.get("video", "")
tags = CFG.get("tags", [])
collection = (CFG.get("collection") or "").strip()
collection_description = (CFG.get("collection_description") or "").strip()

# Calculate steps dynamically
base_steps = 6  # navigate, tab, upload, title, body, action
extra = 0
if mode == "image" and len(images) > 1:
    extra += 1
if mode == "video":
    extra += 1  # wait for upload processing
if tags:
    extra += 1
total_steps = base_steps + extra
step = [0]
def next_step(label):
    step[0] += 1
    print(f"[{step[0]}/{total_steps}] {label}")

next_step("Navigating to XHS creator...")
open_or_reuse_xhs("https://creator.xiaohongshu.com/publish/publish")
wait_for_load()
time.sleep(3)

url = current_tab().get("url") or ""
if "login" in url:
    print("ERROR: Not logged in. Log in at creator.xiaohongshu.com first.")
    capture_screenshot()
    raise SystemExit(1)

if mode == "video":
    # Video tab is the default (first) tab — no need to click
    next_step("Using video upload tab (default)...")
    time.sleep(1)

    next_step("Uploading video: " + video)
    # Wait for the upload input; XHS can render the tab shell before mounting the file input.
    for _ in range(20):
        ready = js('document.querySelector(".upload-input,input[type=file]") ? "ready" : "wait"')
        if ready == "ready":
            break
        time.sleep(0.5)
    # Try upload_file first, fall back to DOM.performSearch for hidden inputs
    try:
        upload_file(".upload-input,input[type=file][accept*=video],input[type=file]", video)
    except Exception:
        doc = cdp("DOM.getDocument", depth=-1, pierce=True)
        sr = cdp("DOM.performSearch", query='input[type="file"]')
        if sr.get("resultCount", 0) > 0:
            nodes = cdp("DOM.getSearchResults", searchId=sr["searchId"], fromIndex=0, toIndex=1)
            nid = nodes["nodeIds"][0]
            cdp("DOM.setFileInputFiles", files=[video], nodeId=nid)
            cdp("DOM.discardSearchResults", searchId=sr["searchId"])
        else:
            print("ERROR: Cannot find file input for video upload.")
            capture_screenshot()
            raise SystemExit(1)

    next_step("Waiting for video upload...")
    for attempt in range(180):
        time.sleep(1)
        # A preview/video element appears immediately, even while XHS still says
        # "上传中 0%". Treat the editor's completed state as authoritative.
        upload_state = js('(function(){var t=document.body.innerText||""; if(/上传中\\s*\\d*%?/.test(t)||t.indexOf("取消上传")>=0)return "uploading"; if(t.indexOf("重新上传")>=0||t.indexOf("检测为高清视频")>=0)return "ready"; return "waiting"})()')
        if upload_state == "ready":
            print("  -> Upload processed and editor-ready!")
            break
        if attempt % 15 == 14:
            pct = js('var el=document.querySelector("[class*=progress],.percent,[class*=uploadProgress]"); el ? el.textContent : "..."')
            print(f"  -> Upload state {upload_state}; {pct} ({attempt+1}s)")
    else:
        print("ERROR: video upload never reached the editor-ready state")
        capture_screenshot()
        raise SystemExit(1)

else:
    # Image mode — click the 2nd tab (上传图文)
    next_step("Switching to image+text tab...")
    js('var tabs=document.querySelectorAll(".creator-tab-item,.tab-item,[class*=publishTypeTabs] span,[class*=publish-type] span");if(tabs.length>=2){tabs[1].click()}else{var all=document.querySelectorAll("span");for(var i=0;i<all.length;i++){if(all[i].textContent.indexOf("\\u56fe\\u6587")>=0){all[i].click();break}}};"done"')
    time.sleep(2)

    check = js('document.querySelector(".upload-input") ? "found" : "notfound"')
    if check != "found":
        js('var spans=document.querySelectorAll("span,div,a");for(var i=0;i<spans.length;i++){var t=spans[i].textContent;if(t&&t.indexOf("\\u56fe\\u6587")>=0&&spans[i].offsetWidth>0){spans[i].click();break}};"retry"')
        time.sleep(2)

    next_step("Uploading image: " + images[0])
    upload_file(".upload-input", images[0])
    time.sleep(4)

    # Upload additional images if any
    if len(images) > 1:
        next_step(f"Uploading {len(images)-1} more image(s)...")
        for i, img in enumerate(images[1:], 2):
            add_btn = js('document.querySelector(".add-upload,.upload-more,.add-btn,[class*=addImage]") ? "found" : "notfound"')
            if add_btn == "found":
                upload_file(".add-upload,.upload-more,.add-btn,[class*=addImage] input[type=file],.upload-input", img)
            else:
                upload_file(".upload-input", img)
            print(f"  -> Image {i}/{len(images)}: {os.path.basename(img)}")
            time.sleep(3)

next_step("Setting title: " + CFG["title"])
title_escaped = json.dumps(CFG["title"])
title_set = js("var inp=document.querySelector('input[placeholder=\"填写标题会有更多赞哦\"],.c-input_inner input,input[placeholder]');if(inp){var ns=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;ns.call(inp," + title_escaped + " );inp.dispatchEvent(new Event('input',{bubbles:true}));inp.dispatchEvent(new Event('change',{bubbles:true}));'done'}else{'missing'}")
if title_set != "done":
    print("ERROR: title input not found")
    capture_screenshot()
    raise SystemExit(1)
time.sleep(0.5)

next_step("Setting body text...")
# Click into the editor area then type
editor_set = js('var ed=document.querySelector(".tiptap.ProseMirror,#post-textarea,.ql-editor,[contenteditable=true]");if(ed){ed.focus();ed.click();"done"}else{"missing"}')
if editor_set != "done":
    print("ERROR: body editor not found")
    capture_screenshot()
    raise SystemExit(1)
time.sleep(0.3)

# Build body with tags appended as hashtags
body = CFG["body"]
if tags:
    tag_str = " " + " ".join(f"#{t}" for t in tags)
    body = body + tag_str
type_text(body)
time.sleep(0.5)

if tags:
    next_step(f"Tags appended: {', '.join(tags)}")

def choose_collection(name, description):
    if not name:
        return None
    opened = js('var es=Array.from(document.querySelectorAll("*")).filter(function(e){var t=(e.innerText||e.textContent||"").trim(); return e.offsetParent && e.children.length===0 && t==="选择合集"}); if(es.length){es[0].click();"yes"}else{"no"}')
    if opened != "yes":
        raise RuntimeError("collection chooser not found")
    time.sleep(.5)
    selected = js('var es=Array.from(document.querySelectorAll("*")).filter(function(e){return e.offsetParent && e.children.length===0 && (e.innerText||e.textContent||"").trim()===' + json.dumps(name) + '}); if(es.length){es[0].click();"yes"}else{"no"}')
    if selected == "yes":
        time.sleep(.5)
        return "selected"
    create = js('var es=Array.from(document.querySelectorAll("button,*")).filter(function(e){return e.offsetParent && e.children.length===0 && (e.innerText||e.textContent||"").trim()==="创建合集"}); if(es.length){es[0].click();"yes"}else{"no"}')
    if create != "yes":
        raise RuntimeError("collection not found and create control missing")
    time.sleep(.5)
    fill_input('input[placeholder="好的合集名称能吸引更多用户"]', name, clear_first=True, timeout=20)
    if description:
        fill_input('input[placeholder="简单介绍你的合集"],textarea[placeholder="简单介绍你的合集"]', description, clear_first=True, timeout=20)
    created = js('var b=Array.from(document.querySelectorAll("button")).find(function(e){return e.offsetParent && (e.innerText||e.textContent||"").trim()==="创建并加入"}); if(b&&!b.disabled){b.click();"yes"}else{"no"}')
    if created != "yes":
        raise RuntimeError("create-and-join collection control unavailable")
    for _ in range(20):
        time.sleep(.5)
        visible = js('(document.body.innerText||"").indexOf(' + json.dumps(name) + ')>=0 && (document.body.innerText||"").indexOf("创建并加入")<0 ? "yes" : "no"')
        if visible == "yes":
            return "created"
    raise RuntimeError("collection creation was not verified")

if collection:
    next_step("Joining collection: " + collection)
    print("  -> Collection " + choose_collection(collection, collection_description))

def creator_manager_receipt(title):
    goto_url("https://creator.xiaohongshu.com/new/note-manager")
    try:
        wait_for_load()
    except Exception:
        pass
    rows = []
    for _ in range(30):
        time.sleep(.5)
        raw = js('Array.from(document.querySelectorAll(".note-card")).map(function(c){var t=c.querySelector(".note-card__title"); return JSON.stringify({title:t?(t.innerText||t.textContent||"").trim():"", text:(c.innerText||"").trim(), impression:c.dataset.impression||""})}).join("\\n")') or ""
        rows = []
        for line in raw.splitlines():
            try:
                row = json.loads(line)
                imp = json.loads(row.get("impression") or "{}")
                row["note_id"] = (((imp.get("noteTarget") or {}).get("value") or {}).get("noteId"))
                if row.get("title") == title:
                    rows.append(row)
            except Exception:
                pass
        if rows:
            break
    if not rows:
        return None
    newest = rows[0]
    text = newest.get("text") or ""
    status = "reviewing" if "审核中" in text else "rejected" if "未通过" in text else "published"
    return {"note_id": newest.get("note_id"), "title": title, "status": status, "duplicate_count": len(rows), "card_text": text}

if CFG["action"] == "publish":
    next_step("Publishing...")
    # XHS can render the publish button before video processing is complete. A
    # programmatic click on a disabled button is a no-op, so wait for the real
    # control to become enabled before clicking it.
    publish_result = "missing"
    for attempt in range(180):
        publish_result = js('var btn=[...document.querySelectorAll("button,[role=button]")].find(function(b){return b.offsetParent && (b.innerText||b.textContent||"").trim()==="发布"}) || document.querySelector(".publishBtn,.publish-btn,button.css-k01wfk,[class*=submit]");if(!btn){"missing"}else if(btn.disabled || btn.getAttribute("aria-disabled")==="true" || btn.classList.contains("disabled")){"disabled"}else{btn.scrollIntoView({block:"center"});btn.click();"clicked"}')
        if publish_result == "clicked":
            break
        if attempt % 15 == 14:
            print(f"  -> Publish control {publish_result}; waiting for processing... ({attempt+1}s)")
        time.sleep(1)
    if publish_result != "clicked":
        # XHS may expose the publish control only through the accessibility tree.
        nodes = cdp("Accessibility.getFullAXTree")["nodes"]
        target = next((n for n in nodes if (n.get("role") or {}).get("value") == "button" and (n.get("name") or {}).get("value") == "发布" and n.get("backendDOMNodeId")), None)
        if target:
            box = cdp("DOM.getBoxModel", backendNodeId=target["backendDOMNodeId"])["model"]["content"]
            x = sum(box[0::2]) / 4
            y = sum(box[1::2]) / 4
            click_at_xy(x, y)
            publish_result = "clicked"
        else:
            print("ERROR: publish button not found")
            capture_screenshot()
            raise SystemExit(1)
    redirect_verified = False
    for _ in range(20):
        time.sleep(1)
        state = js('location.href.indexOf("publish/success")>=0 || /发布成功|成功发布/.test(document.body.innerText||"") ? "success" : "wait"')
        if state == "success":
            redirect_verified = True
            break
    receipt = creator_manager_receipt(CFG["title"])
    if not receipt or not receipt.get("note_id"):
        print("ERROR: publish was not verified in creator manager")
        capture_screenshot()
        raise SystemExit(2)
    receipt["redirect_verified"] = redirect_verified
    receipt["collection"] = collection or None
    print("XHS_RECEIPT " + json.dumps(receipt, ensure_ascii=False, separators=(",", ":")))
    verified = receipt["status"] in {"published", "reviewing"}
    if not verified:
        print("ERROR: creator manager reports " + receipt["status"])
        raise SystemExit(2)
else:
    next_step("Saving as draft...")
    # Find 暂存 button by unicode
    js('var btns=document.querySelectorAll("button");for(var i=0;i<btns.length;i++){if(btns[i].textContent.indexOf("\\u6682\\u5b58")>=0){btns[i].click();break}};"done"')

time.sleep(3)
capture_screenshot()
if CFG["action"] == "publish":
    print("Done! Post published." if verified else "Done! Post submitted; verification pending.")
else:
    print("Done! Post saved as draft.")
