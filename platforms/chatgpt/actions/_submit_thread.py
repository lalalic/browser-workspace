import json
import os
import time
from urllib.parse import quote
from _readiness import wait_until_stable, submission_receipt, prompt_text_matches

CFG=json.load(open("__CFG_PATH__",encoding="utf-8"))
project_id=str(CFG.get("project_id") or "").strip()
thread_id=str(CFG.get("thread_id") or "").strip()
prompt=str(CFG.get("prompt") or "")
files=list(CFG.get("file") or [])
if not project_id or not thread_id: raise RuntimeError("project_id and thread_id are required")
if not prompt and not files: raise RuntimeError("prompt or file is required")
thread_url=f"https://chatgpt.com/g/{quote(project_id,safe='')}/c/{quote(thread_id,safe='')}"
goto_url(thread_url+"?prompt="+quote(prompt,safe=''))
wait_for_load()

def composer_state():
    return js("""(() => {
      const selectors=['#prompt-textarea','[contenteditable="true"][data-composer-markdown]','[contenteditable="true"][data-lexical-editor="true"]','textarea'];
      const elements=[...new Set(selectors.flatMap(s=>[...document.querySelectorAll(s)]))];
      const e=elements.find(node=>{const r=node.getBoundingClientRect();return !node.disabled&&r.width>0&&r.height>0});
      if(!e) return {present:false,text:'',sendEnabled:false};
      const form=e.closest('form');
      const b=form?.querySelector('button[data-testid="send-button"],button[aria-label="Send prompt"],button[aria-label="Send"]');
      return {present:true,text:(e.innerText||e.value||e.textContent||'').trim(),sendEnabled:!!b&&!b.disabled&&b.getAttribute('aria-disabled')!=='true'};
    })()""") or {"present":False,"text":"","sendEnabled":False}

def visible_composer_text():
    return composer_state().get("text","")

def click_visible_send():
    return bool(js("""(() => {
      const selectors=['#prompt-textarea','[contenteditable="true"][data-composer-markdown]','[contenteditable="true"][data-lexical-editor="true"]','textarea'];
      const elements=[...new Set(selectors.flatMap(s=>[...document.querySelectorAll(s)]))];
      const e=elements.find(node=>{const r=node.getBoundingClientRect();return !node.disabled&&r.width>0&&r.height>0});
      if(!e) return false;
      const form=e.closest('form');
      const b=form?.querySelector('button[data-testid="send-button"],button[aria-label="Send prompt"],button[aria-label="Send"]');
      if(!b||b.disabled||b.getAttribute('aria-disabled')==='true') return false;
      b.click(); return true;
    })()"""))

def attachment_state():
    return js(r"""(() => { const names=[...document.querySelectorAll('button[aria-label^="Remove "]')].map(b => (b.getAttribute('aria-label')||'').replace(/^Remove file\s+\d+:\s*/,'').replace(/^Remove\s+/,'')).filter(Boolean); const visible=e=>{const r=e.getBoundingClientRect();return r.width>0&&r.height>0}; const pending=[...document.querySelectorAll('[role="progressbar"],[aria-busy="true"],[data-state="loading"]')].some(visible); return {names,pending}; })()""") or {"names":[],"pending":False}


def user_turns():
    return js("""(() => { const legacy=[...document.querySelectorAll('[data-message-author-role="user"]')].map(e=>({text:(e.innerText||'').trim(),id:e.getAttribute('data-message-id')||''})).filter(x=>x.text); if(legacy.length) return legacy; return [...document.querySelectorAll('h4')].filter(e=>(e.innerText||'').trim()==='You said:').map((e,index)=>({text:(e.parentElement?.innerText||'').replace(/^You said:\\s*/,'').trim(),id:`dom-user-${index}`})).filter(x=>x.text); })()""") or []

def upload_files(paths):
    if not paths: return []
    selector=js("""(() => { for(const s of ['#upload-files','#upload-media','input[name="upload-media"]','input[type="file"]']) if(document.querySelector(s)) return s; return null; })()""")
    if not selector:
        js("""(() => { const b=[...document.querySelectorAll('button')].find(b=>(b.getAttribute('aria-label')||'').trim()==='Add files and more'); if(!b)return false;b.click();return true; })()""")
        deadline=time.time()+5
        while time.time()<deadline and not selector:
            selector=js("""(() => { for(const s of ['#upload-files','#upload-media','input[name="upload-media"]','input[type="file"]']) if(document.querySelector(s)) return s; return null; })()""")
            if not selector: time.sleep(.1)
    if not selector: raise RuntimeError("ChatGPT file input was not observed")
    expected=[]
    for item in paths:
        if not os.path.isfile(item): raise RuntimeError(f"attachment does not exist: {item}")
        upload_file(selector,item); expected.append(os.path.basename(item))
    wait_until_stable(attachment_state,lambda state:set(expected).issubset(state["names"]) and not state["pending"],timeout=120,phase="attachment readiness")
    return expected

wait_until_stable(
    composer_state,
    lambda state: state["present"],
    timeout=20,
    phase="composer readiness",
)
wait_until_stable(
    composer_state,
    lambda state: prompt_text_matches(state["text"],prompt),
    timeout=20,
    phase="prefilled thread readiness",
)
attachments=upload_files(files)
before_users=len(user_turns())
wait_until_stable(
    lambda:{"composer":composer_state(),"attachments":attachment_state()},
    lambda state: prompt_text_matches(state["composer"]["text"],prompt) and set(attachments).issubset(state["attachments"]["names"]) and not state["attachments"]["pending"] and state["composer"]["sendEnabled"],
    timeout=45 if attachments else 20,
    phase="send readiness",
)
if not click_visible_send(): raise RuntimeError("ChatGPT send button changed before click")
deadline=time.time()+15
receipt=None
while time.time()<deadline:
    receipt=submission_receipt(user_turns(),before_users,prompt,visible_composer_text())
    if receipt: break
    time.sleep(.1)
if not receipt: raise RuntimeError("ChatGPT submission verification did not observe an accepted submission")

print(json.dumps({"status":"submitted","project_id":project_id,"thread_id":thread_id,"verified_by":receipt["verified_by"],"user_message_id":receipt["turn"].get("id") or None},ensure_ascii=False),flush=True)
