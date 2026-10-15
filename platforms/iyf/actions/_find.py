import json
from urllib.parse import urlparse

CFG = json.load(open("__CFG_PATH__"))
query = str(CFG.get("query", "")).strip()
if not query:
    raise ValueError("config.query is required")
if not page_info()["url"].startswith("https://www.iyf.tv/"):
    goto("https://www.iyf.tv/")
matches = js("""(() => {
  const q = %s;
  return Array.from(document.querySelectorAll('a[href*="/play/"]'))
    .filter(a => a.textContent.includes(q))
    .map(a => ({title: a.textContent.trim().slice(0,120), url:a.href}))
    .filter((a,i,all) => all.findIndex(b => b.url === a.url) === i)
    .slice(0,15)
})()""" % json.dumps(query, ensure_ascii=False))
print(json.dumps({"query": query, "matches": matches}, ensure_ascii=False))
