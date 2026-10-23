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
if js("document.readyState !== 'complete'"):
    raise RuntimeError("ChatGPT target thread is still loading")
if js("""(() => [...document.querySelectorAll('[role="alert"],[data-testid*="error"],[class*="error-banner"]')].some(e => e.getClientRects().length && getComputedStyle(e).visibility !== 'hidden' && getComputedStyle(e).display !== 'none'))()"""):
    raise RuntimeError("ChatGPT target thread shows a visible error")
if not js("""(() => ['#prompt-textarea','[contenteditable=\"true\"][data-composer-markdown]','[contenteditable=\"true\"][data-lexical-editor=\"true\"]','textarea'].some(s => [...document.querySelectorAll(s)].some(e => e.getClientRects().length && getComputedStyle(e).visibility !== 'hidden' && getComputedStyle(e).display !== 'none'))()"""):
    raise RuntimeError("ChatGPT target thread state is ambiguous")
if js("""(() => [...document.querySelectorAll('button[data-testid="stop-button"],button[aria-label*="Stop generating"],button[aria-label*="Stop response"]')].some(b => b.getClientRects().length && getComputedStyle(b).visibility !== 'hidden' && getComputedStyle(b).display !== 'none'))()"""):
    print(json.dumps({"status":"busy","mode":"new-turn","thread_id":thread_id}),flush=True)
else:
    receipt=submit(message, before_click=globals().get("queue_before_submit"))
    if receipt.get("busy"):
        print(json.dumps({"status":"busy","mode":"new-turn","thread_id":thread_id}),flush=True)
    else:
        print(json.dumps({
          "status":"submitted",
          "mode":"new-turn",
          "project_id":project_id,
          "thread_id":thread_id,
          "thread_url":thread_url.split("?",1)[0],
          "verified_by":receipt["verified_by"],
          "user_message_id":receipt["turn"].get("id") or None,
        },ensure_ascii=False),flush=True)
