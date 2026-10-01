import json
import re
import time
from urllib.parse import urlsplit


CFG = json.load(open("__CFG_PATH__", encoding="utf-8"))

def _norm(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()

def _candidate(selector, patterns, root_expr="document"):
    wanted=[p.lower() for p in patterns]
    return js(f"""(() => {{
      const root={root_expr};
      const wanted={json.dumps(wanted)};
      const nodes=[...root.querySelectorAll({json.dumps(selector)})];
      const e=nodes.find(el=>{{
        const text=((el.innerText||el.textContent||el.getAttribute('aria-label')||'')+'').replace(/\\s+/g,' ').trim().toLowerCase();
        return wanted.some(p=>text===p||text.includes(p));
      }});
      if(!e) return false; e.click(); return true;
    }})()""")

def _wait(predicate, label, timeout=15):
    deadline=time.time()+timeout
    last=None
    while time.time()<deadline:
        try:
            last=predicate()
            if last:
                return last
        except Exception:
            pass
        time.sleep(.15)
    raise RuntimeError(f"{label} not found")

def _project_from_url(url):
    m=re.search(r"/g/(g-p-[A-Za-z0-9]{32})(?:-[^/]+)?(?:/|$)", url or "")
    return m.group(1) if m else None

def _project_links():
    return js("""(() => [...document.querySelectorAll('a[href]')].map(a=>({
      text:(a.innerText||a.textContent||'').replace(/\s+/g,' ').trim(),
      href:new URL(a.getAttribute('href'),location.origin).href
    })).filter(x=>/\/g\/g-p-[A-Za-z0-9]{32}/.test(x.href)))()""") or []

def _ensure_project(name):
    wanted=_norm(name).lower()

    # Current ChatGPT sidebar exposes stable project ids directly on project rows.
    existing=js(f"""(() => {{
      const wanted={json.dumps(wanted)};
      const rows=[...document.querySelectorAll('[data-app-action-sidebar-project-row]')];
      const row=rows.find(e=>(e.getAttribute('data-app-action-sidebar-project-label')||'').replace(/\\s+/g,' ').trim().toLowerCase()===wanted);
      return row ? {{
        projectId:row.getAttribute('data-app-action-sidebar-project-id')||'',
        label:row.getAttribute('data-app-action-sidebar-project-label')||''
      }} : null;
    }})()""")
    if existing and existing.get("projectId"):
        project_url=f"https://chatgpt.com/g/{existing['projectId']}/project"
        goto_url(project_url)
        wait_for_load()
        return {"project_id":existing["projectId"],"project_url":page_info().get("url",project_url),"reused":True}

    # Legacy fallback for older ChatGPT Project sidebar surfaces.
    for item in _project_links():
        if _norm(item.get("text")).lower()==wanted:
            pid=_project_from_url(item["href"])
            project_url=f"https://chatgpt.com/g/{pid}/project" if pid else item["href"]
            goto_url(project_url)
            wait_for_load()
            return {"project_id":pid,"project_url":page_info().get("url",project_url),"reused":True}

    clicked=bool(js("""(() => {
      const b=[...document.querySelectorAll('button')].find(b=>(b.getAttribute('aria-label')||'').toLowerCase().includes('add new project'));
      if(!b)return false;b.click();return true;
    })()"""))
    if not clicked:
        clicked=_candidate('button,a,[role="button"]',['new project','create project'])
    if not clicked:
        raise RuntimeError(f"ChatGPT New Project control was not found for {name}")

    selector=_wait(lambda: js("""(() => {
      const visible=e=>{const r=e.getBoundingClientRect();return !!(r.width&&r.height)};
      const e=[...document.querySelectorAll('input[type="text"],input:not([type]),textarea')]
        .find(e=>visible(e)&&/project name|copenhagen trip/i.test((e.getAttribute('aria-label')||'')+' '+(e.getAttribute('placeholder')||''))) ||
        [...document.querySelectorAll('input[type="text"],input:not([type]),textarea')].find(visible);
      if(!e)return null;
      e.setAttribute('data-neoy-project-name','1');
      return '[data-neoy-project-name="1"]';
    })()"""), "ChatGPT project name field")
    fill_input(selector,name,clear_first=True)

    # New Project dialog defaults to account memory. Choose Project-only when offered.
    js("""(() => {
      const visible=e=>{const r=e.getBoundingClientRect();return !!(r.width&&r.height)};
      const fire=e=>{for(const type of ['pointerdown','mousedown','pointerup','mouseup','click']) e.dispatchEvent(new MouseEvent(type,{bubbles:true,cancelable:true,view:window,button:0,buttons:type.includes('down')?1:0}));};
      const b=[...document.querySelectorAll('button,[role="button"]')].filter(visible).find(e=>/default memory/i.test((e.innerText||e.textContent||e.getAttribute('aria-label')||'')));
      if(b){fire(b);return true;} return false;
    })()""")
    time.sleep(.15)
    js("""(() => {
      const fire=e=>{for(const type of ['pointerdown','mousedown','pointerup','mouseup','click']) e.dispatchEvent(new MouseEvent(type,{bubbles:true,cancelable:true,view:window,button:0,buttons:type.includes('down')?1:0}));};
      const nodes=[...document.querySelectorAll('[role="menuitem"],button,[role="button"],label')];
      const e=nodes.find(e=>/project[- ]only/i.test((e.innerText||e.textContent||e.getAttribute('aria-label')||'').replace(/\s+/g,' ').trim()));
      if(!e)return false;fire(e);return true;
    })()""")

    ok=js("""(() => {
      const visible=e=>{const r=e.getBoundingClientRect();return !!(r.width&&r.height)};
      const buttons=[...document.querySelectorAll('button,[role="button"]')].filter(visible);
      const b=buttons.find(e=>{
        const t=(e.innerText||e.textContent||e.getAttribute('aria-label')||'').replace(/\s+/g,' ').trim().toLowerCase();
        return t==='create project'||t==='create'||t==='continue'||t==='done';
      });
      if(!b||b.disabled||b.getAttribute('aria-disabled')==='true')return false;b.click();return true;
    })()""")
    if not ok:
        raise RuntimeError("ChatGPT Create Project button not found")

    deadline=time.time()+30
    while time.time()<deadline:
        info=page_info()
        pid=_project_from_url(info.get("url",""))
        if pid:
            project_url=f"https://chatgpt.com/g/{pid}/project"
            if "/project" not in urlsplit(info.get("url","")).path:
                goto_url(project_url); wait_for_load()
            return {"project_id":pid,"project_url":page_info().get("url",project_url),"reused":False}
        created=js(f"""(() => {{
          const wanted={json.dumps(wanted)};
          const rows=[...document.querySelectorAll('[data-app-action-sidebar-project-row]')];
          const row=rows.find(e=>(e.getAttribute('data-app-action-sidebar-project-label')||'').replace(/\\s+/g,' ').trim().toLowerCase()===wanted);
          return row ? row.getAttribute('data-app-action-sidebar-project-id')||'' : '';
        }})()""")
        if created:
            project_url=f"https://chatgpt.com/g/{created}/project"
            goto_url(project_url); wait_for_load()
            return {"project_id":created,"project_url":page_info().get("url",project_url),"reused":False}
        time.sleep(.25)
    raise RuntimeError(f"ChatGPT Project {name} was not created")

def _settings_panel():
    already=js("""(() => {
      const d=document.querySelector('[role="dialog"]');
      return !!d && /project settings/i.test((d.innerText||d.textContent||''));
    })()""")
    if already:
        return True

    opened=_wait(lambda: js("""(() => {
      const fire=e=>{for(const type of ['pointerdown','mousedown','pointerup','mouseup','click']) e.dispatchEvent(new MouseEvent(type,{bubbles:true,cancelable:true,view:window,button:0,buttons:type.includes('down')?1:0}));};
      const b=[...document.querySelectorAll('button')].find(b=>(b.getAttribute('aria-label')||'')==='Project actions');
      if(!b)return false;fire(b);return true;
    })()"""), "ChatGPT Project actions control",15)

    def open_settings_menu_item():
        return js("""(() => {
          const fire=e=>{for(const type of ['pointerdown','mousedown','pointerup','mouseup','click']) e.dispatchEvent(new MouseEvent(type,{bubbles:true,cancelable:true,view:window,button:0,buttons:type.includes('down')?1:0}));};
          const nodes=[...document.querySelectorAll('[role="menuitem"],button,[role="button"],a')];
          const e=nodes.find(e=>{
            const text=(e.innerText||e.textContent||e.getAttribute('aria-label')||'').replace(/\\s+/g,' ').trim().toLowerCase();
            return text.includes('project settings') || text.includes('edit project') || text.includes('project instructions');
          });
          if(e){fire(e);return true;}
          const b=[...document.querySelectorAll('button')].find(b=>(b.getAttribute('aria-label')||'')==='Project actions');
          if(b) fire(b);
          return false;
        })()""")
    _wait(open_settings_menu_item, "ChatGPT Project settings menu item",8)

    _wait(lambda: js("""(() => {
      const d=document.querySelector('[role="dialog"]');
      return !!d && /project settings/i.test((d.innerText||d.textContent||''));
    })()"""), "ChatGPT Project settings dialog",5)
    return True

def _close_settings_panel():
    js("""(() => {
      const d=document.querySelector('[role="dialog"]');
      if(!d)return true;
      const b=[...d.querySelectorAll('button,[role="button"]')].find(e=>(e.getAttribute('aria-label')||'')==='Close dialog'||/close dialog/i.test((e.innerText||e.textContent||'')));
      if(!b)return false;
      const fire=e=>{for(const type of ['pointerdown','mousedown','pointerup','mouseup','click']) e.dispatchEvent(new MouseEvent(type,{bubbles:true,cancelable:true,view:window,button:0,buttons:type.includes('down')?1:0}));};
      fire(b);return true;
    })()""")
    time.sleep(.2)

def _set_field_value(field_selector,value):
    ok=js(f"""(() => {{
      const e=document.querySelector({json.dumps(field_selector)});
      if(!e)return false;
      e.focus();
      if(e instanceof HTMLTextAreaElement || e instanceof HTMLInputElement){{
        const p=e instanceof HTMLTextAreaElement?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;
        const setter=Object.getOwnPropertyDescriptor(p,'value')?.set;
        setter?.call(e,{json.dumps(value)});
      }}else{{
        const sel=window.getSelection(),r=document.createRange();r.selectNodeContents(e);sel.removeAllRanges();sel.addRange(r);
        document.execCommand('delete',false,null);
        document.execCommand('insertText',false,{json.dumps(value)});
        sel.removeAllRanges();
      }}
      e.dispatchEvent(new InputEvent('input',{{bubbles:true,inputType:'insertText',data:{json.dumps(value)}}}));
      e.dispatchEvent(new Event('change',{{bubbles:true}}));
      return true;
    }})()""")
    if not ok: raise RuntimeError("Could not update Project Instructions field")

def _apply_instructions(value):
    value=str(value or "").strip()
    if not value: raise RuntimeError("Project Instructions are empty")
    _settings_panel()
    selector=_wait(lambda: js("""(() => {
      const root=document.querySelector('[role="dialog"]');
      if(!root||!/project settings/i.test((root.innerText||root.textContent||'')))return null;
      const field=root.querySelector('textarea');
      if(!field)return null;
      field.setAttribute('data-neoy-project-instructions','1');
      return '[data-neoy-project-instructions="1"]';
    })()"""), "ChatGPT Project Instructions field")
    _set_field_value(selector,value)
    # Current ChatGPT Project settings auto-save Instructions.
    time.sleep(1.0)

def _set_project_only_memory():
    _settings_panel()
    current=js("""(() => {
      const d=document.querySelector('[role="dialog"]');
      if(!d)return 'missing';
      const text=(d.innerText||d.textContent||'').replace(/\s+/g,' ').trim().toLowerCase();
      if(text.includes('project-only')) return 'project-only';
      const controls=[...d.querySelectorAll('button,[role="button"]')];
      const memory=controls.find(e=>/default memory|memory/i.test((e.innerText||e.textContent||e.getAttribute('aria-label')||'').replace(/\s+/g,' ').trim().toLowerCase()));
      if(!memory)return 'unavailable';
      const fire=e=>{for(const type of ['pointerdown','mousedown','pointerup','mouseup','click']) e.dispatchEvent(new MouseEvent(type,{bubbles:true,cancelable:true,view:window,button:0,buttons:type.includes('down')?1:0}));};
      fire(memory);return 'opened';
    })()""")
    if current=="project-only":
        _close_settings_panel()
        return {"memory":"project-only"}
    if current=="opened":
        _wait(lambda: js("""(() => {
          const nodes=[...document.querySelectorAll('[role="menuitem"],button,[role="button"],label')];
          const e=nodes.find(e=>/project[- ]only/i.test((e.innerText||e.textContent||e.getAttribute('aria-label')||'').replace(/\s+/g,' ').trim()));
          if(!e)return false;
          const fire=e=>{for(const type of ['pointerdown','mousedown','pointerup','mouseup','click']) e.dispatchEvent(new MouseEvent(type,{bubbles:true,cancelable:true,view:window,button:0,buttons:type.includes('down')?1:0}));};
          fire(e);return true;
        })()"""), "Project-only memory option",3)
        time.sleep(.7)
        _close_settings_panel()
        return {"memory":"project-only"}
    _close_settings_panel()
    return {"memory":"unavailable"}

def _composer_selector():
    return js("""(() => {
      const sels=['#prompt-textarea','[contenteditable="true"][data-composer-markdown]','[contenteditable="true"][data-lexical-editor="true"]','textarea'];
      for(const s of sels){const e=document.querySelector(s);if(!e)continue;const r=e.getBoundingClientRect();if(r.width&&r.height)return s;}
      const visible=[...document.querySelectorAll('[contenteditable="true"]')].filter(e=>{const r=e.getBoundingClientRect();return r.width&&r.height;});
      if(visible.length===1){visible[0].setAttribute('data-neoy-composer','1');return '[data-neoy-composer="1"]';}
      return null;
    })()""")

def _fill_composer(text):
    sel=_wait(_composer_selector,"ChatGPT Project composer",30)
    editable=bool(js(f"""(() => document.querySelector({json.dumps(sel)})?.getAttribute('contenteditable')==='true')()"""))
    if editable:
        _set_field_value(sel,text)
    else:
        fill_input(sel,text,clear_first=True)
    return sel

def _send_initial(text):
    before=page_info().get("url","")
    _fill_composer(text)
    button=_wait(lambda: js("""(() => {
      const b=document.querySelector('button[data-testid="send-button"],button[aria-label="Send prompt"],button[aria-label="Send"],form button[type="submit"]');
      if(!b||b.disabled||b.getAttribute('aria-disabled')==='true')return null;
      b.setAttribute('data-neoy-send','1');return '[data-neoy-send="1"]';
    })()"""), "enabled ChatGPT Send button",20)
    clicked=js("""(() => {const b=document.querySelector('[data-neoy-send="1"]');if(!b)return false;b.click();return true;})()""")
    if not clicked: raise RuntimeError("Initial Project thread Send failed")
    deadline=time.time()+90
    observed_thread=False
    while time.time()<deadline:
        current=page_info().get("url","")
        path=urlsplit(current).path
        if "/c/" in path:
            observed_thread=True
            # ChatGPT first exposes a client-local local-chatgpt id, then replaces
            # it with the durable server thread id. Never persist the temporary URL.
            if "local-chatgpt" not in current:
                assistant_visible=bool(js("""(() => [...document.querySelectorAll('h4')].some(e => (e.innerText || '').trim() === 'ChatGPT said:') || document.querySelector('[data-message-author-role="assistant"]'))()"""))
                if assistant_visible:
                    return current
        time.sleep(.25)
    if observed_thread:
        raise RuntimeError("ChatGPT Project thread stayed on a temporary local-chatgpt URL")
    raise RuntimeError(f"ChatGPT did not create a Project thread from {before}")

target_id=new_tab("https://chatgpt.com/")
wait_for_load()
project=_ensure_project(CFG["project_name"])
if project.get("project_url") and page_info().get("url","")!=project["project_url"]:
    goto_url(project["project_url"]); wait_for_load()
_apply_instructions(CFG["instructions"])
memory_state=_set_project_only_memory()

# Return to the Project root after settings operations if the UI changed location.
project_url=project["project_url"]
if "/project" not in urlsplit(page_info().get("url","")).path:
    goto_url(project_url); wait_for_load()

initial=str(CFG.get("initial_prompt") or "").strip()
if not initial:
    initial="Initialize this learner's Family Tutor thread from the Project Instructions and reply only with READY."
thread_url=_send_initial(initial)
print(json.dumps({
  "status":"completed",
  "project_id":project["project_id"],
  "project_url":project_url,
  "project_reused":project["reused"],
  "memory":memory_state["memory"],
  "thread_url":thread_url.split("?",1)[0],
  "target_id":target_id,
},ensure_ascii=False),flush=True)
