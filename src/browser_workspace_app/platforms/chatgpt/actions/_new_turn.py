import json
from urllib.parse import quote, urlsplit
import _lifecycle_common as lifecycle_common

lifecycle_common.js = js
lifecycle_common.fill_input = fill_input
wait_for_idle = lifecycle_common.wait_for_idle
submit = lifecycle_common.submit

CFG=json.load(open("__CFG_PATH__",encoding="utf-8"))
project_id=str(CFG.get("project_id") or "").strip() or None
thread_id=str(CFG.get("thread_id") or "").strip()
message=str(CFG.get("message") or "").strip()
if not thread_id: raise RuntimeError("thread_id is required")
if not message: raise RuntimeError("message is required")
if project_id:
    thread_url=f"https://chatgpt.com/g/{quote(project_id,safe='')}/c/{quote(thread_id,safe='')}"
else:
    thread_url=f"https://chatgpt.com/c/{quote(thread_id,safe='')}"
goto_url(thread_url)
wait_for_load()
if urlsplit(page_info().get("url","")).path.rstrip("/") != urlsplit(thread_url).path.rstrip("/"):
    raise RuntimeError("ChatGPT thread redirect mismatch")
wait_for_idle(timeout=int(CFG.get("wait_timeout",300)))
receipt=submit(message)
print(json.dumps({
  "status":"submitted",
  "mode":"new-turn",
  "project_id":project_id,
  "thread_id":thread_id,
  "verified_by":receipt["verified_by"],
  "user_message_id":receipt["turn"].get("id") or None,
},ensure_ascii=False),flush=True)
