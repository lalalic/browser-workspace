import json
CFG = json.load(open("__CFG_PATH__"))
url = CFG.get("url","")
if not url.startswith("https://www.iyf.tv/play/"):
    raise ValueError("Only IYF desktop play URLs are allowed")
new_tab(url)
wait_for_load()
info=page_info()
player = js("!!document.querySelector('video')")
print(json.dumps({"url":info["url"],"title":info["title"],"player":player},ensure_ascii=False))
