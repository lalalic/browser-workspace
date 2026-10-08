import json
import time
from _readiness import wait_until_stable, submission_receipt, prompt_text_matches


def composer_selector():
    return js("""(() => {
      const selectors=['#prompt-textarea','[contenteditable="true"][data-composer-markdown]','[contenteditable="true"][data-lexical-editor="true"]','textarea'];
      for (const selector of selectors) {
        const e=document.querySelector(selector);
        if (!e || e.disabled) continue;
        const r=e.getBoundingClientRect();
        if (r.width>0 && r.height>0) return selector;
      }
      return null;
    })()""")


def composer_text(selector=None):
    selector=selector or composer_selector()
    if not selector: return ""
    return js(f"""(() => {{
      const e=document.querySelector({json.dumps(selector)});
      if (!e) return '';
      return (e.innerText || e.value || e.textContent || '').trim();
    }})()""") or ""


def send_enabled():
    return bool(js("""(() => {
      const b=document.querySelector('button[data-testid="send-button"],button[aria-label="Send prompt"],button[aria-label="Send"],form button[type="submit"]');
      return !!b && !b.disabled && b.getAttribute('aria-disabled') !== 'true';
    })()"""))


def is_generating():
    return bool(js("""(() => !![...document.querySelectorAll('button')].find(b => {
      const a=(b.getAttribute('aria-label')||'').toLowerCase();
      const t=(b.textContent||'').trim().toLowerCase();
      const id=(b.getAttribute('data-testid')||'').toLowerCase();
      return a.includes('stop answering') || a.includes('stop generating') || t === 'stop' || id.includes('stop');
    }))()"""))


def user_turns():
    return js("""(() => {
      const legacy=[...document.querySelectorAll('[data-message-author-role="user"]')]
        .map(e=>({text:(e.innerText||'').trim(),id:e.getAttribute('data-message-id')||''})).filter(x=>x.text);
      if (legacy.length) return legacy;
      return [...document.querySelectorAll('h4')]
        .filter(e=>(e.innerText||'').trim()==='You said:')
        .map((e,index)=>({text:(e.parentElement?.innerText||'').replace(/^You said:\\s*/,'').trim(),id:`dom-user-${index}`}))
        .filter(x=>x.text);
    })()""") or []


def wait_for_idle(timeout=300):
    return wait_until_stable(
        lambda: {"composer": composer_selector(), "generating": is_generating()},
        lambda state: bool(state["composer"]) and not state["generating"],
        timeout=timeout,
        interval=.25,
        stable_samples=3,
        phase="ChatGPT turn completion",
    )


def fill_prompt(prompt):
    selector=wait_until_stable(
        lambda: composer_selector(),
        lambda value: bool(value),
        timeout=30,
        phase="ChatGPT composer readiness",
    )
    editable=bool(js(f"""(() => document.querySelector({json.dumps(selector)})?.getAttribute('contenteditable')==='true')()"""))
    if editable:
        chunks=[prompt[i:i+256] for i in range(0, len(prompt), 256)]
        ok=js(f"""(() => {{
          const e=document.querySelector({json.dumps(selector)});
          if(!e)return false;
          e.focus();
          const sel=window.getSelection(), range=document.createRange();
          range.selectNodeContents(e); sel.removeAllRanges(); sel.addRange(range);
          document.execCommand('delete',false,null); sel.removeAllRanges();
          for (const chunk of {json.dumps(chunks)}) {{
            const current=window.getSelection(), r=document.createRange();
            r.selectNodeContents(e); r.collapse(false); current.removeAllRanges(); current.addRange(r);
            if(!document.execCommand('insertText',false,chunk)) return false;
          }}
          e.dispatchEvent(new InputEvent('input',{{bubbles:true,inputType:'insertText',data:{json.dumps(prompt)}}}));
          return true;
        }})()""")
        if not ok: raise RuntimeError("ChatGPT composer rejected lifecycle continuation")
    else:
        fill_input(selector,prompt,clear_first=True)
    wait_until_stable(
        lambda: {"text":composer_text(selector),"send":send_enabled()},
        lambda state: prompt_text_matches(state["text"],prompt) and state["send"],
        timeout=20,
        phase="ChatGPT lifecycle continuation readiness",
    )
    return selector


def submit(prompt):
    before=len(user_turns())
    selector=fill_prompt(prompt)
    clicked=js("""(() => {
      const b=document.querySelector('button[data-testid="send-button"],button[aria-label="Send prompt"],button[aria-label="Send"],form button[type="submit"]');
      if(!b||b.disabled||b.getAttribute('aria-disabled')==='true')return false;
      b.click(); return true;
    })()""")
    if not clicked: raise RuntimeError("ChatGPT send button changed before lifecycle submit")
    deadline=time.time()+30
    while time.time()<deadline:
        receipt=submission_receipt(user_turns(),before,prompt,composer_text(selector))
        if receipt: return receipt
        time.sleep(.2)
    raise RuntimeError("ChatGPT lifecycle submission was not observed")
