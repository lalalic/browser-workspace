from urllib.parse import quote, urlencode
from _readiness import (
    SubmissionVerificationError,
    submission_failure_diagnostic,
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


SEND_ENABLED_JS = """(() => {
      const b=document.querySelector('button[data-testid="send-button"],button[aria-label="Send prompt"],button[aria-label="Send"],form button[type="submit"]');
      return !!b && !b.disabled && b.getAttribute('aria-disabled') !== 'true';
    })()"""


def send_enabled():
    return bool(js(SEND_ENABLED_JS))


def visible_delivery_error():
    """Read-only inspection of visible error banners, not historical chat text."""
    return js("""(() => {
      const alerts=[...document.querySelectorAll('[role="alert"],[role="status"],[data-sonner-toast],[data-testid*="toast"],[class*="toast"],[class*="error-banner"]')];
      for(const e of alerts) {
        if(!e.getClientRects().length) continue;
        const t=(e.innerText||'').toLowerCase();
        if(t.includes('this conversation is too long to continue') || t.includes('conversation is too long to continue')) return 'conversation_too_long';
        if(t.includes('could not load this chatgpt conversation')) return 'thread_load_failed';
      }
      // A failed navigation may render an error page without an alert role.
      if((document.body?.innerText||'').toLowerCase().includes('could not load this chatgpt conversation')) return 'thread_load_failed';
      return null;
    })()""")


def raise_if_visible_delivery_error():
    code=visible_delivery_error()
    if code: raise RuntimeError(f'ChatGPT visible delivery error: {code}')


CLICK_SEND_JS = """(() => {
      const visible=e=>!!e&&!!e.getClientRects().length;
      const running=[...document.querySelectorAll('button')].some(b=>{
        if(!visible(b)) return false;
        const label=(b.getAttribute('aria-label')||'').trim().toLowerCase();
        const title=(b.getAttribute('title')||'').trim().toLowerCase();
        const test=(b.getAttribute('data-testid')||'').trim().toLowerCase();
        return ['stop generating','stop answering','stop response','stop'].includes(label)
          || ['stop generating','stop answering'].includes(title)
          || ['stop-button','stop-generating-button'].includes(test);
      });
      if(running) return false;
      const b=document.querySelector('button[data-testid="send-button"],button[aria-label="Send prompt"],button[aria-label="Send"],form button[type="submit"]');
      if(!b||b.disabled||b.getAttribute('aria-disabled')==='true')return false;
      b.click(); return true;
    })()"""


def click_send_once():
    """One atomic click gate shared by new-turn and FIFO."""
    return js(CLICK_SEND_JS)

def prefilled_submit(prompt, *, send=True):
    """Shared URL-prefilled Send gate; validation never clicks or fills."""
    ready=wait_for_send_ready()
    if not send:
        return {"send_enabled": ready}
    if not ready:
        raise RuntimeError("URL-prefilled Send button was not observed ready")
    clicked=click_send_once()
    if not clicked:
        raise RuntimeError("URL-prefilled Send became unavailable before click")
    try:
        wait_until_stable(
            lambda: {"send_disabled": not send_enabled()},
            lambda state: state["send_disabled"],
            timeout=30, interval=.2, stable_samples=2,
            phase="post-click Send disabled",
        )
    except RuntimeError as exc:
        raise SubmissionVerificationError("Send did not become disabled after click",
              {"reason":"post_submit_send_state_unverified"}) from exc
    return {"verified_by":"send-button-disabled", "turn":{"id":None}}


def wait_for_send_ready():
    """URL prefill readiness via Send-button state only."""
    try:
        wait_until_stable(
            lambda: {"send": send_enabled()},
            lambda state: send_ready(state),
            timeout=15, interval=.25, stable_samples=3,
            phase="prefilled Send readiness",
        )
        return True
    except RuntimeError:
        return False
