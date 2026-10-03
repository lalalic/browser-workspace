import json
import time
from urllib.parse import quote, urlsplit
from _lifecycle_common import wait_for_idle, submit

CFG=json.load(open("__CFG_PATH__",encoding="utf-8"))
project_id=str(CFG.get("project_id") or "").strip() or None
message=str(CFG.get("message") or "").strip()
source_thread_id=str(CFG.get("source_thread_id") or "").strip() or None
temporary=bool(CFG.get("temporary", False))

if not message:
    raise RuntimeError("message is required")
if temporary and project_id:
    raise RuntimeError("temporary=true cannot be combined with project_id")

if temporary:
    start_url="https://chatgpt.com/?temporary-chat=true"
elif project_id:
    start_url=f"https://chatgpt.com/g/{quote(project_id,safe='')}/project"
else:
    start_url="https://chatgpt.com/"

goto_url(start_url)
wait_for_load()
wait_for_idle(timeout=60)

if temporary:
    is_temporary=bool(js("""(() => {
      if (location.search.includes('temporary-chat=true')) return true;
      return [...document.querySelectorAll('button')].some(b =>
        (b.getAttribute('aria-label')||'').toLowerCase().includes('turn off temporary chat') ||
        (b.textContent||'').trim().toLowerCase()==='turn off temporary chat'
      ) || [...document.querySelectorAll('h1')].some(h => (h.textContent||'').trim().toLowerCase()==='temporary chat');
    })()"""))
    if not is_temporary:
        raise RuntimeError("ChatGPT Temporary Chat mode was not activated")

receipt=submit(message)

if temporary:
    print(json.dumps({
      "status":"submitted",
      "mode":"new-thread",
      "temporary":True,
      "project_id":None,
      "source_thread_id":source_thread_id,
      "thread_id":None,
      "thread_url":None,
      "verified_by":receipt["verified_by"],
      "user_message_id":receipt["turn"].get("id") or None,
    },ensure_ascii=False),flush=True)
    raise SystemExit(0)

deadline=time.time()+60
thread_id=None
thread_url=None
while time.time()<deadline:
    current=page_info().get("url","").split("?",1)[0]
    path=urlsplit(current).path.rstrip("/")
    if "/c/" in path and "local-chatgpt" not in current:
        candidate=path.rsplit("/",1)[-1]
        if candidate:
            thread_id=candidate
            thread_url=current
            break
    time.sleep(.2)
if not thread_id:
    raise RuntimeError("ChatGPT did not assign a durable thread id")

print(json.dumps({
  "status":"submitted",
  "mode":"new-thread",
  "temporary":False,
  "project_id":project_id,
  "source_thread_id":source_thread_id,
  "thread_id":thread_id,
  "thread_url":thread_url,
  "verified_by":receipt["verified_by"],
  "user_message_id":receipt["turn"].get("id") or None,
},ensure_ascii=False),flush=True)
