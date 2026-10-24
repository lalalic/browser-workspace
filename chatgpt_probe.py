"""Bounded, read-only ChatGPT page check for a future WebHelm action."""
from __future__ import annotations

from urllib.parse import quote, urlencode, urlsplit


def target_url(project_id: str | None, thread_id: str, message: str) -> str:
    if not thread_id or not message:
        raise ValueError("thread_id and message are required")
    prefix = f"/g/{quote(project_id, safe='')}" if project_id else ""
    return f"https://chatgpt.com{prefix}/c/{quote(thread_id, safe='')}?{urlencode({'prompt': message})}"


PROBE_JS = r"""(() => {
  const visible=e => !!e && !!e.getClientRects().length &&
    getComputedStyle(e).visibility !== 'hidden';
  const body=(document.body?.innerText||'').toLowerCase();
  if (body.includes('could not load this chatgpt conversation'))
    return {state:'BLOCKED',error:'thread_load_failed'};
  if (body.includes('log in to chatgpt'))
    return {state:'BLOCKED',error:'authentication_required'};
  const stop=[...document.querySelectorAll('button')].some(b => {
    if(!visible(b)) return false;
    const label=(b.getAttribute('aria-label')||'').trim().toLowerCase();
    const title=(b.getAttribute('title')||'').trim().toLowerCase();
    const test=(b.getAttribute('data-testid')||'').trim().toLowerCase();
    return ['stop generating','stop answering','stop response','stop'].includes(label)
      || ['stop generating','stop answering'].includes(title)
      || ['stop-button','stop-generating-button'].includes(test);
  });
  if (stop) return {state:'RUNNING',stop_visible:true};
  const composer=document.querySelector('#prompt-textarea, [contenteditable="true"][data-lexical-editor="true"], [role="textbox"][contenteditable="true"], textarea');
  // innerText may synthesize extra layout newlines in Lexical editors.
  const editable=!!composer?.getAttribute && composer.getAttribute('contenteditable')==='true';
  return {
    state:visible(composer) ? 'READY':'NOT_READY',
    stop_visible:false,
    composer_text:composer ? (editable ? (composer.textContent||'') : (composer.value||composer.textContent||composer.innerText||'')) : ''
  };
})()"""


def classify_probe(observed_url: str, expected_url: str, state: dict, message: str) -> str:
    actual, expected = urlsplit(observed_url), urlsplit(expected_url)
    if actual.scheme != "https" or actual.netloc != "chatgpt.com" or actual.path.rstrip("/") != expected.path.rstrip("/"):
        return "BLOCKED"
    if state.get("state") in ("RUNNING", "BLOCKED"):
        return state["state"]
    # ChatGPT consumes ?prompt= asynchronously. A matching composer before
    # navigation normalization is not sufficient proof of a settled page.
    if actual.query:
        return "NOT_READY"
    # A failed or unhydrated prefill must never cause a blind Send click.
    if state.get("state") != "READY" or state.get("composer_text", "").strip() != message.strip():
        return "NOT_READY"
    return "READY"
