import json
import os
import re
import time
from urllib.parse import urlsplit


CFG = json.load(open("__CFG_PATH__", encoding="utf-8"))

def _composer():
    selector = js("""(() => {
      const selectors = [
        '#prompt-textarea',
        '[contenteditable="true"][data-composer-markdown]',
        '[contenteditable="true"][data-lexical-editor="true"]',
        'textarea'
      ];
      for (const selector of selectors) {
        const e=document.querySelector(selector);
        if (!e || e.id === 'pending-home-input' || e.disabled) continue;
        const r=e.getBoundingClientRect();
        if (r.width>0 && r.height>0) return selector;
      }
      const visible=[...document.querySelectorAll('[contenteditable="true"]')].filter(e => {
        if (e.id === 'pending-home-input' || e.disabled) return false;
        const r=e.getBoundingClientRect();
        return r.width>0 && r.height>0;
      });
      return visible.length === 1 ? '[contenteditable="true"]' : null;
    })()""")
    if not selector:
        raise RuntimeError("ChatGPT composer was not observed")
    return selector

def _composer_text(selector):
    return js(f"""(() => {{
      const e=document.querySelector({json.dumps(selector)});
      if (!e) return '';
      if (e.getAttribute('contenteditable') !== 'true') return e.value || '';
      const clone=e.cloneNode(true);
      clone.querySelectorAll('[app-mention-name]').forEach(node => node.remove());
      return (clone.innerText || clone.textContent || '').trim();
    }})()""") or ""

def _clear_composer(selector):
    editable=bool(js(f"""(() => {{
      const e=document.querySelector({json.dumps(selector)});
      return !!e && e.getAttribute('contenteditable') === 'true';
    }})()"""))
    if not editable:
        fill_input(selector, "", clear_first=True)
        return
    ok=js(f"""(() => {{
      const e=document.querySelector({json.dumps(selector)});
      if (!e) return false;
      e.focus();
      const sel=window.getSelection();
      const range=document.createRange();
      range.selectNodeContents(e);
      sel.removeAllRanges(); sel.addRange(range);
      document.execCommand('delete', false, null);
      sel.removeAllRanges();
      return true;
    }})()""")
    if not ok:
        raise RuntimeError("composer could not be cleared")

def _attach_app(selector, target_id, app_name, timeout=10):
    name=str(app_name or "").strip()
    if not name:
        return False
    _clear_composer(selector)
    session=cdp("Target.attachToTarget", targetId=target_id, flatten=True)["sessionId"]
    cdp("Input.insertText", session_id=session, text="@")
    wanted=name.lower()
    deadline=time.time()+timeout
    while time.time()<deadline:
        clicked=js(f"""(() => {{
          const wanted={json.dumps(wanted)};
          const buttons=[...document.querySelectorAll('button,[role="option"],[role="menuitem"]')];
          const candidate=buttons.find(e => {{
            const text=(e.innerText||e.textContent||'').replace(/\s+/g,'').trim().toLowerCase();
            return text===wanted || text===wanted+wanted;
          }});
          if(!candidate) return false;
          candidate.click();
          return true;
        }})()""")
        if clicked:
            break
        time.sleep(.1)
    else:
        raise RuntimeError(f"ChatGPT app '{name}' was not offered by the composer")
    deadline=time.time()+timeout
    while time.time()<deadline:
        attached=js(f"""(() => {{
          const e=document.querySelector({json.dumps(selector)});
          if(!e) return false;
          return !![...e.querySelectorAll('[app-mention-name]')].find(
            n => (n.getAttribute('app-mention-name')||'').toLowerCase()==={json.dumps(wanted)}
          );
        }})()""")
        if attached:
            return True
        time.sleep(.1)
    raise RuntimeError(f"ChatGPT app '{name}' mention did not attach")

def _attachment_state():
    return js(r"""(() => {
      const names=[...document.querySelectorAll('button[aria-label^="Remove "]')]
        .map(b => (b.getAttribute('aria-label') || '').replace(/^Remove file\s+\d+:\s*/, '').replace(/^Remove\s+/, ''))
        .filter(Boolean);
      const visible=e => { const r=e.getBoundingClientRect(); return r.width>0 && r.height>0; };
      const pendingSelector='[role="progressbar"], [aria-busy="true"], [data-state="loading"]';
      const pending=[...document.querySelectorAll(pendingSelector)].some(visible);
      return {names, pending};
    })()""") or {"names": [], "pending": False}

def _send_state():
    return js(r"""(() => {
      const b=document.querySelector('button[data-testid="send-button"],button[aria-label="Send prompt"],button[aria-label="Send"]');
      return {present:!!b, enabled:!!b && !b.disabled && b.getAttribute('aria-disabled') !== 'true'};
    })()""") or {"present": False, "enabled": False}

def _user_turns():
    return js("""(() => {
      const legacy=[...document.querySelectorAll('[data-message-author-role="user"]')]
        .map(e => ({text:(e.innerText || '').trim(), id:e.getAttribute('data-message-id') || ''}))
        .filter(x => x.text);
      if (legacy.length) return legacy;
      return [...document.querySelectorAll('h4')]
        .filter(e => (e.innerText || '').trim() === 'You said:')
        .map((e,index) => {
          const raw=(e.parentElement?.innerText || '').trim();
          return {text:raw.replace(/^You said:\\s*/,'').trim(), id:`dom-user-${index}`};
        })
        .filter(x => x.text);
    })()""") or []

def _assistant_messages():
    return js("""(() => {
      const legacy=[...document.querySelectorAll('[data-message-author-role="assistant"]')]
        .map(e => ({text:(e.innerText || '').trim(), id:e.getAttribute('data-message-id') || ''}))
        .filter(x => x.text);
      if (legacy.length) return legacy;
      return [...document.querySelectorAll('h4')]
        .filter(e => (e.innerText || '').trim() === 'ChatGPT said:')
        .map((e,index) => {
          const raw=(e.parentElement?.innerText || '').trim();
          return {text:raw.replace(/^ChatGPT said:\\s*/,'').trim(), id:`dom-assistant-${index}`};
        })
        .filter(x => x.text);
    })()""") or []

def _is_generating():
    return bool(js("""(() => !![...document.querySelectorAll('button')].find(b => {
      const a=(b.getAttribute('aria-label')||'').toLowerCase();
      const t=(b.textContent||'').trim().toLowerCase();
      const id=(b.getAttribute('data-testid')||'').toLowerCase();
      return a.includes('stop answering') || a.includes('stop generating') || t === 'stop' || id.includes('stop');
    }))()"""))

def _fill_prompt(prompt, timeout=30, preserve_app=False):
    deadline=time.time()+timeout
    last_error=None
    while time.time()<deadline:
        selector=_composer()
        if prompt_text_matches(_composer_text(selector), prompt):
            return selector
        editable=bool(js(f"""(() => {{
          const e=document.querySelector({json.dumps(selector)});
          return !!e && e.getAttribute('contenteditable') === 'true';
        }})()"""))
        try:
            if editable:
                if not preserve_app:
                    _clear_composer(selector)
                else:
                    ok=js(f"""(() => {{
                      const e=document.querySelector({json.dumps(selector)});
                      if (!e) return false;
                      e.focus();
                      const sel=window.getSelection();
                      const range=document.createRange();
                      range.selectNodeContents(e);
                      range.collapse(false);
                      sel.removeAllRanges(); sel.addRange(range);
                      return true;
                    }})()""")
                    if not ok: raise RuntimeError("composer caret could not be placed after app mention")
                for offset in range(0, len(prompt), 256):
                    chunk=prompt[offset:offset+256]
                    inserted=js(f"""(() => {{
                      const e=document.querySelector({json.dumps(selector)});
                      if (!e) return false;
                      e.focus();
                      const ok=document.execCommand('insertText', false, {json.dumps(chunk)});
                      e.dispatchEvent(new InputEvent('input', {{bubbles:true,inputType:'insertText',data:{json.dumps(chunk)}}}));
                      return ok;
                    }})()""")
                    if not inserted: raise RuntimeError("composer rejected prompt chunk")
            else:
                if preserve_app:
                    raise RuntimeError("ChatGPT app mention requires a contenteditable composer")
                fill_input(selector, prompt, clear_first=True)
            return selector
        except RuntimeError as exc:
            last_error=exc
            time.sleep(.25)
    raise RuntimeError(f"ChatGPT composer could not be filled: {last_error}")

def _upload_files(paths):
    if not paths: return []
    selector=js("""(() => {
      for (const s of ['#upload-files','#upload-media','input[name="upload-media"]','input[type="file"]'])
        if (document.querySelector(s)) return s;
      return null;
    })()""")
    if not selector:
        opened=js("""(() => {
          const b=[...document.querySelectorAll('button')].find(b => (b.getAttribute('aria-label')||'').trim()==='Add files and more');
          if (!b) return false; b.click(); return true;
        })()""")
        if opened:
            deadline=time.time()+5
            while time.time()<deadline and not selector:
                selector=js("""(() => {
                  for (const s of ['#upload-files','#upload-media','input[name="upload-media"]','input[type="file"]'])
                    if (document.querySelector(s)) return s;
                  return null;
                })()""")
                if not selector: time.sleep(.1)
    if not selector: raise RuntimeError("ChatGPT file input was not observed")
    expected=[]
    for path in paths:
        if not os.path.isfile(path): raise RuntimeError(f"attachment does not exist: {path}")
        upload_file(selector, path)
        expected.append(os.path.basename(path))
    wait_until_stable(
        _attachment_state,
        lambda state: set(expected).issubset(state["names"]) and not state["pending"],
        timeout=120,
        phase="attachment readiness",
    )
    return expected

def _submit(prompt, files, target_id):
    selector=_composer()
    app_name=CFG.get("app")
    app_attached=_attach_app(selector, target_id, app_name) if app_name else False
    selector=_fill_prompt(prompt, preserve_app=app_attached)
    attachments=_upload_files(files)
    before_users=len(_user_turns())
    before_assistants=len(_assistant_messages())
    state=wait_until_stable(
        lambda: {"selector":_composer(),"text":_composer_text(_composer()),"attachments":_attachment_state(),"send":_send_state()},
        lambda s: prompt_text_matches(s["text"], prompt) and set(attachments).issubset(s["attachments"]["names"]) and not s["attachments"]["pending"] and s["send"]["enabled"],
        timeout=45 if attachments else 20,
        phase="send readiness",
    )
    selector=state["selector"]
    clicked=js("""(() => {
      const b=document.querySelector('button[data-testid="send-button"],button[aria-label="Send prompt"],button[aria-label="Send"]');
      if (!b || b.disabled || b.getAttribute('aria-disabled') === 'true') return false;
      b.click(); return true;
    })()""")
    if not clicked: raise RuntimeError("ChatGPT send button changed before click")
    deadline=time.time()+30
    receipt=None
    while time.time()<deadline:
        receipt=submission_receipt(_user_turns(), before_users, prompt, _composer_text(selector))
        if receipt: break
        time.sleep(.25)
    if not receipt: raise RuntimeError("ChatGPT submission verification did not observe an accepted submission")
    return before_assistants, attachments, receipt

def _result(before_assistants, timeout):
    deadline=time.time()+timeout
    signature=None
    stable_since=None
    while time.time()<deadline:
        if _is_generating():
            signature=None
            stable_since=None
            time.sleep(.5)
            continue
        messages=_assistant_messages()
        if len(messages)<=before_assistants:
            time.sleep(.5)
            continue
        latest=messages[-1]
        sig=(latest.get("id"), latest.get("text"))
        if sig!=signature:
            signature=sig
            stable_since=time.time()
            time.sleep(.5)
            continue
        if not latest.get("text") or stable_since is None or time.time()-stable_since<3:
            time.sleep(.5)
            continue
        return latest
    raise RuntimeError("ChatGPT assistant result did not become complete before timeout")

def _open_thread():
    thread_url=CFG["thread_url"]
    expected_path=urlsplit(thread_url).path.rstrip("/")
    target_id=CFG.get("target_id")
    recovered=False
    if target_id:
        try:
            switch_tab(target_id)
            current_path=urlsplit(page_info().get("url","")).path.rstrip("/")
            if current_path!=expected_path:
                # The Tutor slot is the durable identity. If its CDP target still
                # exists but was navigated elsewhere, recover in-place rather than
                # acquiring another Browser Workspace lease.
                goto_url(thread_url)
                wait_for_load()
                recovered=True
                deadline=time.time()+30
                while time.time()<deadline:
                    if urlsplit(page_info().get("url","")).path.rstrip("/")==expected_path:
                        break
                    time.sleep(.25)
                else:
                    raise RuntimeError("bound Tutor target could not recover its thread")
        except Exception:
            target_id=None
            recovered=True
    if not target_id:
        target_id=new_tab(thread_url)
        wait_for_load()
        deadline=time.time()+30
        while time.time()<deadline:
            if urlsplit(page_info().get("url","")).path.rstrip("/")==expected_path:
                break
            time.sleep(.25)
        else:
            raise RuntimeError("Existing ChatGPT thread redirect mismatch")
    wait_until_stable(
        lambda: {"selector": _composer()},
        lambda state: bool(state["selector"]),
        timeout=30,
        phase="thread hydration",
    )
    return target_id, recovered

target_id, recovered=_open_thread()
before_assistants, attachments, receipt=_submit(CFG["prompt"], CFG.get("file", []), target_id)
assistant=_result(before_assistants, CFG.get("result_timeout", 240))
print(json.dumps({
    "status":"completed",
    "thread_url":page_info().get("url","").split("?",1)[0],
    "target_id":target_id,
    "recovered":recovered,
    "attachments":attachments,
    "app":CFG.get("app") or None,
    "verified_by":receipt["verified_by"],
    "user_message_id":receipt["turn"].get("id") or None,
    "assistant_message_id":assistant.get("id") or None,
    "text":assistant.get("text",""),
}, ensure_ascii=False), flush=True)
