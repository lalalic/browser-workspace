import json
import time
from urllib.parse import quote, urlencode
from _readiness import (
    SubmissionVerificationError,
    submission_failure_diagnostic,
    submission_receipt,
    prompt_text_matches,
    send_ready,
    wait_until_stable,
)


def target_url(*, project_id=None, thread_id=None, temporary=False, prompt=None):
    """Shared ChatGPT navigation URL for new-thread, new-turn and validation."""
    if temporary and (project_id or thread_id):
        raise ValueError("temporary cannot be combined with project_id or thread_id")
    if temporary:
        base = "https://chatgpt.com/"
    elif thread_id:
        prefix = f"/g/{quote(project_id, safe='')}" if project_id else ""
        base = f"https://chatgpt.com{prefix}/c/{quote(thread_id, safe='')}"
    elif project_id:
        base = f"https://chatgpt.com/g/{quote(project_id, safe='')}/project"
    else:
        base = "https://chatgpt.com/"
    params = {}
    if temporary:
        params["temporary-chat"] = "true"
    if prompt is not None:
        params["prompt"] = prompt
    return base + ("?" + urlencode(params) if params else "")


def composer_selector():
    return js("""(() => {
      const selectors=['#prompt-textarea','[contenteditable="true"][data-composer-markdown]','[contenteditable="true"][data-lexical-editor="true"]','textarea'];
      for (const selector of selectors) {
        const e=document.querySelector(selector);
        if (!e || e.disabled) continue;
        const r=e.getBoundingClientRect();
        if (r.width>0 && r.height>0) return selector;
      }
      const generic=[...document.querySelectorAll('[contenteditable="true"]')].filter(e=>{
        if (e.id==='pending-home-input' || e.disabled) return false;
        const r=e.getBoundingClientRect();
        return r.width>0 && r.height>0;
      });
      return generic.length===1 ? '[contenteditable="true"]:not(#pending-home-input)' : null;
    })()""")


def primary_composer_selector():
    return js("""(() => {
      const selectors=['#prompt-textarea','[contenteditable="true"][data-composer-markdown]','[contenteditable="true"][data-lexical-editor="true"]'];
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


def verification_ui_state(selector):
    return {
        "composer_selector": selector,
        "composer_text_length": len((composer_text(selector) or "").strip()),
        "send_enabled": send_enabled(),
        "generating": is_generating(),
        "user_turn_count": len(user_turns()),
    }


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


def visible_delivery_error():
    """Read-only inspection of visible error banners, not historical chat text."""
    return js("""(() => {
      const composer=!!document.querySelector('#prompt-textarea,[data-composer-markdown]');
      const alerts=[...document.querySelectorAll('[role="alert"],[role="status"],[data-sonner-toast],[data-testid*="toast"],[class*="toast"],[class*="error-banner"]')];
      for(const e of alerts) {
        if(!e.getClientRects().length) continue;
        const t=(e.innerText||'').toLowerCase();
        if(t.includes('this conversation is too long to continue') || t.includes('conversation is too long to continue')) return 'conversation_too_long';
        if(t.includes('could not load this chatgpt conversation')) return 'thread_load_failed';
      }
      // A failed navigation may render an error page without an alert role.
      if(!composer && (document.body?.innerText||'').toLowerCase().includes('could not load this chatgpt conversation')) return 'thread_load_failed';
      return null;
    })()""")


def raise_if_visible_delivery_error():
    code=visible_delivery_error()
    if code: raise RuntimeError(f'ChatGPT visible delivery error: {code}')


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
    try:
        selector=wait_until_stable(
            lambda: primary_composer_selector(),
            lambda value: bool(value),
            timeout=20,
            phase="ChatGPT canonical composer readiness",
        )
    except RuntimeError:
        # The preferred selector timed out; still try the generic composer.
        selector=wait_until_stable(
            lambda: composer_selector(),
            lambda value: bool(value),
            timeout=5,
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
    try:
        wait_until_stable(
            lambda: {"text":composer_text(selector),"send":send_enabled()},
            lambda state: send_ready(state, prompt=prompt),
            timeout=20,
            phase="ChatGPT lifecycle continuation readiness",
        )
    except RuntimeError as exc:
        raise_if_visible_delivery_error()
        raise RuntimeError(f"{exc}; diagnostic={json.dumps(verification_ui_state(selector), ensure_ascii=False)}") from exc
    return selector


def submit(prompt, *, send=True):
    if not send:
        # URL-prefilled probe: wait for hydration exactly as real submission
        # waits for Send, but never fill the composer or click the button.
        try:
            wait_until_stable(
                lambda: {"send": send_enabled()},
                lambda state: send_ready(state),
                timeout=15, interval=.25, stable_samples=3,
                phase="prefilled Send readiness",
            )
            return {"send_enabled": True}
        except RuntimeError:
            return {"send_enabled": False}
    selector=fill_prompt(prompt)
    ui_before=verification_ui_state(selector)
    clicked=js("""(() => {
      const b=document.querySelector('button[data-testid="send-button"],button[aria-label="Send prompt"],button[aria-label="Send"],form button[type="submit"]');
      if(!b||b.disabled||b.getAttribute('aria-disabled')==='true')return false;
      b.click(); return true;
    })()""")
    if not clicked: raise RuntimeError("ChatGPT send button changed before lifecycle submit")
    try:
        wait_until_stable(
            lambda: {"composer_empty": not bool(composer_text(selector).strip()), "send_disabled": not send_enabled()},
            lambda state: state["composer_empty"] and state["send_disabled"],
            timeout=30, interval=.2, stable_samples=3,
            phase="post-submit composer reset",
        )
    except RuntimeError as exc:
        raise SubmissionVerificationError(
            "ChatGPT submission did not reach a stable cleared composer and disabled Send button",
            {"ui_before":ui_before,"ui_after":verification_ui_state(selector),"reason":"post_submit_ui_unverified"},
        ) from exc
    return {"verified_by":"composer-cleared", "turn": {"id":""}}
