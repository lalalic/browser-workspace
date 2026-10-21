import json
import time
from urllib.parse import quote, urlsplit
import _lifecycle_common as lifecycle_common

lifecycle_common.js = js
raise_if_visible_delivery_error = lifecycle_common.raise_if_visible_delivery_error
submit = lifecycle_common.prefilled_submit

CFG=json.load(open("__CFG_PATH__",encoding="utf-8"))
project_id=str(CFG.get("project_id") or "").strip() or None
message=str(CFG.get("message") or "").strip()
source_thread_id=str(CFG.get("source_thread_id") or "").strip() or None
temporary=bool(CFG.get("temporary", False))

# The creation action is for ordinary Chat conversations, not Relay jobs.
if any(key in CFG for key in ("job_id", "jobId", "task_id", "taskId", "pr_number", "prNumber")):
    raise RuntimeError("new-thread does not accept Job/Task/PR context")
if CFG.get("mode", "chat") != "chat":
    raise RuntimeError("new-thread supports chat mode only")

def ensure_chat_mode():
    def current_mode():
        return js("""(() => {
          const buttons=[...document.querySelectorAll('button')];
          const find=name=>buttons.find(b=>(b.textContent||'').trim()===name && b.hasAttribute('aria-pressed'));
          const chat=find('Chat'), work=find('Work');
          if (!chat || !work) return 'unknown';
          if (chat.getAttribute('aria-pressed')==='true' && work.getAttribute('aria-pressed')==='false') return 'chat';
          if (work.getAttribute('aria-pressed')==='true' && chat.getAttribute('aria-pressed')==='false') return 'work';
          return 'unknown';
        })()""")
    if current_mode() == 'work':
        if not js("""(() => {
          const chat=[...document.querySelectorAll('button')].find(b=>(b.textContent||'').trim()==='Chat' && b.hasAttribute('aria-pressed'));
          if (!chat || chat.disabled) return false;
          chat.click(); return true;
        })()"""):
            raise RuntimeError("Cannot select Chat mode")
        for _ in range(30):
            if current_mode() == 'chat': break
            time.sleep(.2)
    if current_mode() == 'chat':
        return
    # Temporary Chat has no Chat/Work toggle; verify the dedicated mode UI.
    if temporary and js("""(() => {
      const temporaryButton=[...document.querySelectorAll('button')].some(b =>
        (b.getAttribute('aria-label')||'').toLowerCase().includes('turn off temporary chat'));
      const composer=[...document.querySelectorAll('[role="textbox"],textarea')].some(e =>
        (e.getAttribute('aria-label')||'').trim()==='Ask ChatGPT');
      return temporaryButton && composer;
    })()"""):
        return
    raise RuntimeError("new-thread Chat mode could not be verified")

if not message:
    raise RuntimeError("message is required")
if temporary and project_id:
    raise RuntimeError("temporary=true cannot be combined with project_id")

start_url=lifecycle_common.target_url(project_id=project_id, temporary=temporary, prompt=message)
goto_url(start_url)
wait_for_load()
raise_if_visible_delivery_error()
ensure_chat_mode()
# Switching Work to Chat may discard the URL prefill: navigate again in Chat mode.
if not temporary:
    goto_url(start_url)
    wait_for_load()

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

raise_if_visible_delivery_error()
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
else:
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
