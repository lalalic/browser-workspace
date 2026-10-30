import time, json

CFG = json.load(open("__CFG_PATH__"))

total_steps = 7
step = [0]
def next_step(label):
    step[0] += 1
    print(f"[{step[0]}/{total_steps}] {label}")

next_step("Opening TikTok upload page...")
new_tab("https://www.tiktok.com/creator#/upload?scene=creator_center")
wait_for_load()
time.sleep(5)

url = page_info()["url"]
if "login" in url.lower() or "accounts" in url.lower():
    print("ERROR: Not logged in. Log in at tiktok.com first.")
    capture_screenshot()
    raise SystemExit(1)

# Check for uid null error (not logged in)
# The page loads but shows login modal if not authenticated
login_check = js('document.querySelector("[class*=login-modal],[class*=LoginModal]") ? "login" : "ok"')
if login_check == "login":
    print("ERROR: Login modal detected. Log in at tiktok.com first.")
    capture_screenshot()
    raise SystemExit(1)

# Wait for upload area to appear
for i in range(15):
    found = js('document.querySelector("input[type=file],input[accept*=video],[class*=upload-btn],[class*=upload-card]") ? "found" : "wait"')
    if found == "found":
        break
    time.sleep(2)
else:
    print("ERROR: Upload area not found. May not be logged in.")
    capture_screenshot()
    raise SystemExit(1)

print("  -> Logged in, page loaded.")

next_step("Uploading video: " + CFG["video"])
# TikTok has a file input, may be hidden — try multiple selectors
try:
    upload_file("input[type=file]", CFG["video"])
except Exception:
    # Fallback: find input via DOM search
    doc = cdp("DOM.getDocument", depth=-1, pierce=True)
    sr = cdp("DOM.performSearch", query='input[type="file"]')
    if sr.get("resultCount", 0) > 0:
        nodes = cdp("DOM.getSearchResults", searchId=sr["searchId"], fromIndex=0, toIndex=1)
        nid = nodes["nodeIds"][0]
        cdp("DOM.setFileInputFiles", files=[CFG["video"]], nodeId=nid)
        cdp("DOM.discardSearchResults", searchId=sr["searchId"])
    else:
        print("ERROR: Cannot find file input.")
        capture_screenshot()
        raise SystemExit(1)

next_step("Waiting for video upload + processing...")
for attempt in range(120):
    time.sleep(5)
    # Check for upload completion indicators
    done = js('''
        (function() {
            var indicators = document.querySelectorAll("[class*=progress],[class*=percent],[class*=upload-progress]");
            for (var i = 0; i < indicators.length; i++) {
                var t = indicators[i].textContent;
                if (t && (t.indexOf("100") >= 0 || t.indexOf("Complete") >= 0 || t.indexOf("Done") >= 0)) return "done";
            }
            // Check if caption editor appeared (means upload accepted)
            if (document.querySelector("[class*=caption],[class*=editor] [contenteditable],[data-text=true]")) return "done";
            return "uploading";
        })()
    ''')
    if done == "done":
        print("  -> Upload done!")
        break
    if attempt % 6 == 5:
        pct = js('var el=document.querySelector("[class*=progress-text],[class*=percent]"); el ? el.textContent.trim() : "..."')
        print(f"  -> Uploading... {pct} ({(attempt+1)*5}s)")
else:
    print("WARNING: Upload may still be processing.")
    capture_screenshot()
time.sleep(3)

next_step("Setting caption...")
caption_escaped = json.dumps(CFG["caption"])
# TikTok uses a contenteditable div or DraftJS editor for caption
js('''
    (function() {
        var ed = document.querySelector("[class*=caption-editor] [contenteditable],[class*=notranslate][contenteditable],[data-text=true],.DraftEditor-root [contenteditable],[class*=editor-container] [contenteditable]");
        if (!ed) ed = document.querySelector("[contenteditable=true]");
        if (ed) {
            ed.focus();
            ed.textContent = ''' + caption_escaped + ''';
            ed.dispatchEvent(new Event("input", {bubbles: true}));
        }
    })()
''')
time.sleep(1)

# Set visibility if not public
if CFG["visibility"] != "public":
    next_step("Setting visibility to " + CFG["visibility"] + "...")
    # Click "Who can watch this video" dropdown
    js('''
        (function() {
            var selects = document.querySelectorAll("[class*=select],[class*=dropdown],[class*=visibility]");
            for (var i = 0; i < selects.length; i++) {
                var t = selects[i].textContent;
                if (t && (t.indexOf("Everyone") >= 0 || t.indexOf("Public") >= 0 || t.indexOf("Friends") >= 0)) {
                    selects[i].click();
                    break;
                }
            }
        })()
    ''')
    time.sleep(1)
    # Map visibility to TikTok's menu options
    vis_map = {"friends": "Friends", "private": "Only me"}
    vis_text = vis_map.get(CFG["visibility"], "Everyone")
    js('var opts=document.querySelectorAll("[class*=option],[class*=menu-item],[role=option]");for(var i=0;i<opts.length;i++){if(opts[i].textContent.indexOf("' + vis_text + '")>=0){opts[i].click();break}};""')
    time.sleep(1)
else:
    next_step("Visibility: public (default)")

# Toggle social features if needed
toggles_changed = []
if not CFG.get("allow_comments", True):
    toggles_changed.append("comments off")
if not CFG.get("allow_duets", True):
    toggles_changed.append("duets off")
if not CFG.get("allow_stitch", True):
    toggles_changed.append("stitch off")

if toggles_changed:
    next_step("Adjusting toggles: " + ", ".join(toggles_changed))
    # TikTok has toggle switches for comments, duets, stitch
    js('''
        (function() {
            var toggles = document.querySelectorAll("[class*=toggle],[class*=switch]");
            var labels = ["comment", "duet", "stitch"];
            var states = [''' + json.dumps(CFG.get("allow_comments", True)) + ''', ''' + json.dumps(CFG.get("allow_duets", True)) + ''', ''' + json.dumps(CFG.get("allow_stitch", True)) + '''];
            toggles.forEach(function(t) {
                var text = (t.closest("[class*=form-item],[class*=setting]") || t.parentElement).textContent.toLowerCase();
                for (var i = 0; i < labels.length; i++) {
                    if (text.indexOf(labels[i]) >= 0) {
                        var isOn = t.classList.contains("on") || t.getAttribute("aria-checked") === "true" || t.querySelector("[class*=active]");
                        if (isOn !== states[i]) t.click();
                    }
                }
            });
        })()
    ''')
    time.sleep(1)
else:
    next_step("Social features: defaults (all enabled)")

capture_screenshot()

next_step("Posting video...")
# Click the Post button
js('''
    (function() {
        var btns = document.querySelectorAll("button,[class*=btn-post],[class*=post-button]");
        for (var i = 0; i < btns.length; i++) {
            var t = btns[i].textContent.trim();
            if (t === "Post" || t === "发布") {
                btns[i].click();
                return;
            }
        }
    })()
''')
time.sleep(5)

capture_screenshot()
print("Done! Video posted to TikTok.")
