info = page_info()
if "capcut.com" not in info["url"].lower():
    raise SystemExit(f"Not on CapCut: {info['url']}")

text = js("document.body.innerText") or ""
markers = ("Media", "Captions", "Export")
found = [marker for marker in markers if marker in text]
print(f"URL: {info['url']}")
print(f"Title: {info['title']}")
print(f"Editor markers: {', '.join(found) if found else 'none'}")
if len(found) != len(markers):
    print("The current page may not be the CapCut editor.")
print(snapshot())