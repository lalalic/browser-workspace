import time, json

CFG = json.load(open("__CFG_PATH__"))

tags = CFG.get("tags", [])
thumbnail = CFG.get("thumbnail", "")
has_extras = bool(tags or thumbnail)
total_steps = 7 + (1 if tags else 0) + (1 if thumbnail else 0)
step = [0]
def next_step(label):
    step[0] += 1
    print(f"[{step[0]}/{total_steps}] {label}")

def click_btn(text):
    for _ in range(5):
        r = js('var btns=document.querySelectorAll("ytcp-button");var b=Array.from(btns).find(function(x){return x.textContent.trim()==="' + text + '"});b?JSON.stringify(b.getBoundingClientRect()):null')
        if r and r != "None":
            rect = json.loads(r)
            click_at_xy(int(rect["x"]+rect["width"]/2), int(rect["y"]+rect["height"]/2))
            return True
        time.sleep(1)
    return False

next_step("Opening YouTube Studio upload...")
new_tab("https://www.youtube.com/upload")
wait_for_load()
time.sleep(3)

url = page_info()["url"]
if "accounts.google.com" in url:
    print("ERROR: Not logged in")
    capture_screenshot()
    raise SystemExit(1)

next_step("Uploading video...")
upload_file("input[type=file]", CFG["video"])
time.sleep(5)

next_step("Waiting for processing...")
time.sleep(3)

next_step("Setting title: " + CFG["title"])
title_escaped = json.dumps(CFG["title"])
js('var b=document.querySelectorAll("#textbox")[0];b.textContent=' + title_escaped + ';b.dispatchEvent(new Event("input",{bubbles:true}));""')
time.sleep(0.5)

next_step("Setting description...")
desc_escaped = json.dumps(CFG["desc"])
js('var b=document.querySelectorAll("#textbox")[1];b.textContent=' + desc_escaped + ';b.dispatchEvent(new Event("input",{bubbles:true}));""')
time.sleep(0.5)

# Upload thumbnail if provided
if thumbnail:
    next_step("Uploading thumbnail...")
    # Click "Upload thumbnail" button to reveal file input
    js('var btn=document.querySelector("#still-picker ytcp-button,#upload-prompt");if(btn)btn.click();""')
    time.sleep(1)
    upload_file("#file-loader input[type=file],input[accept*=image]", thumbnail)
    time.sleep(3)

# Add tags via "Show more" → tags input
if tags:
    next_step("Adding tags: " + ", ".join(tags))
    # Expand "Show more" section
    js('var btn=document.querySelector("#toggle-button ytcp-button,ytcp-button#toggle-button");if(btn)btn.click();""')
    time.sleep(1)
    # Find tags input and type comma-separated tags
    tag_str = ",".join(tags)
    tag_escaped = json.dumps(tag_str)
    js('var inp=document.querySelector("input.tags-input,input[aria-label*=Tag],input[placeholder*=Tag]");if(inp){var ns=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,"value").set;ns.call(inp,' + tag_escaped + ');inp.dispatchEvent(new Event("input",{bubbles:true}));inp.dispatchEvent(new Event("change",{bubbles:true}))};"done"')
    time.sleep(0.5)

next_step("Setting audience" + (" (MADE FOR KIDS)" if CFG.get("made_for_kids") else "") + " + advancing wizard...")
if CFG.get("made_for_kids"):
    # COPPA: select explicitly by name — never rely on radio order
    js('var r=document.querySelector("tp-yt-paper-radio-button[name=VIDEO_MADE_FOR_KIDS_MFK]");if(r){r.click()}')
else:
    js('var g=document.querySelector(".made-for-kids-group");if(g){g.querySelectorAll("tp-yt-paper-radio-button")[1].click()}')
time.sleep(1)

for w_step in ["Video elements", "Initial check", "Visibility"]:
    print("  -> " + w_step)
    click_btn("Next")
    time.sleep(2)

vis = CFG["vis"]
next_step("Setting visibility to " + vis + " and saving...")
for _ in range(5):
    found = js('document.querySelector("[name=' + vis + ']") ? "found" : "notfound"')
    if found == "found":
        js('document.querySelector("[name=' + vis + ']").click()')
        time.sleep(1)
        break
    time.sleep(1)

click_btn("Save")
time.sleep(5)

capture_screenshot()
print("Done! Video saved as " + vis + ".")
