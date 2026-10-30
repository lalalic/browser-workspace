import json
from urllib.parse import quote, urlsplit
import _lifecycle_common as lifecycle_common

lifecycle_common.js = js
raise_if_visible_delivery_error = lifecycle_common.raise_if_visible_delivery_error
submit = lifecycle_common.prefilled_submit

CFG=json.load(open("__CFG_PATH__",encoding="utf-8"))
project_id=str(CFG.get("project_id") or "").strip() or None
thread_id=str(CFG.get("thread_id") or "").strip()
message=str(CFG.get("message") or "").strip()
if not thread_id: raise RuntimeError("thread_id is required")
if not message: raise RuntimeError("message is required")
thread_url=lifecycle_common.target_url(project_id=project_id, thread_id=thread_id, prompt=message)
goto_url(thread_url)
wait_for_load()
raise_if_visible_delivery_error()
if urlsplit(page_info().get("url","")).path.rstrip("/") != urlsplit(thread_url).path.rstrip("/"):
    raise RuntimeError("ChatGPT thread redirect mismatch")
raise_if_visible_delivery_error()
receipt=submit(message)
print(json.dumps({
  "status":"submitted",
  "mode":"new-turn",
  "project_id":project_id,
  "thread_id":thread_id,
  "thread_url":thread_url.split("?",1)[0],
  "verified_by":receipt["verified_by"],
  "user_message_id":receipt["turn"].get("id") or None,
},ensure_ascii=False),flush=True)
