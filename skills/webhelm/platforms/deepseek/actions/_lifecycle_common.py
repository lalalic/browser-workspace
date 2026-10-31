import json
import re
import time
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

ANSWER_STATE = """(() => {
  const answers = [...document.querySelectorAll('.ds-assistant-message-main-content')];
  const generating = !!document.querySelector('[role=button].ds-button--primary:not(.ds-button--disabled)');
  const finished = document.querySelectorAll('[aria-label="Read aloud"]').length >= answers.length;
  return {count: answers.length, answer: answers.at(-1)?.innerText.trim() || '', settled: !generating && finished};
})()"""

# Observe the signed-in webpage's own response; never make an API request or
# access credentials. Register before page navigation (the app caches fetch).
STREAM_OBSERVER = r"""(() => {
  if (window.__webhelmDeepseekStream?.version === 2) return;
  const stream = {version: 2, entries: []};
  window.__webhelmDeepseekStream = stream;
  const original = window.fetch;
  window.fetch = function (...args) {
    const url = String(args[0]?.url || args[0] || '');
    const request = original.apply(this, args);
    if (!/\/api\/v0\/chat\/completion(?:\?|$)/.test(url)) return request;
    return request.then(response => {
      const entry = {state: 'reading', http: response.status, body: '', error: ''};
      stream.entries.push(entry);
      response.clone().text().then(body => {
        if (body.length > 2000000) {
          entry.state = 'oversized';
          entry.error = 'Site response exceeded the 2 MB observer limit';
        } else {
          entry.state = 'received';
          entry.body = body;
        }
      }).catch(error => {
        entry.state = 'read_error';
        entry.error = String(error);
      });
      return response;
    });
  };
  // DeepSeek also uses XMLHttpRequest for this endpoint in some page builds.
  const originalOpen = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function (method, url, ...rest) {
    this.__webhelmDeepseekUrl = String(url || '');
    return originalOpen.call(this, method, url, ...rest);
  };
  const originalSend = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.send = function (...args) {
    if (/\/api\/v0\/chat\/completion(?:\?|$)/.test(this.__webhelmDeepseekUrl || '')) {
      const entry = {state: 'reading', http: null, body: '', error: ''};
      stream.entries.push(entry);
      this.addEventListener('loadend', () => {
        entry.http = this.status;
        try {
          const body = this.responseText;
          if (typeof body !== 'string' || body.length > 2000000) {
            entry.state = 'oversized';
            entry.error = 'Site response is not readable text or exceeds 2 MB';
          } else {
            entry.state = 'received';
            entry.body = body;
          }
        } catch (error) {
          entry.state = 'read_error';
          entry.error = String(error);
        }
      }, {once: true});
    }
    return originalSend.apply(this, args);
  };
})()"""

STREAM_STATE = """(() => {
  const entries = window.__webhelmDeepseekStream?.entries || [];
  return {count: entries.length, latest: entries.length ? {
    state: entries.at(-1).state, http: entries.at(-1).http,
    error: entries.at(-1).error
  } : null};
})()"""

STREAM_BODY = """(() => {
  const entries = window.__webhelmDeepseekStream?.entries || [];
  return entries.at(-1)?.body || '';
})()"""


def parse_site_stream(body):
    """Require SSE ready, response FINISHED, close, and nonempty reply fragments."""
    if not isinstance(body, str):
        return None
    ready = finished = closed = False
    fragments = []
    last_path = None
    for block in re.split(r"\r?\n\r?\n", body):
        event_type = ''
        data_lines = []
        for line in block.splitlines():
            if line.startswith('event:'):
                event_type = line[6:].strip()
            elif line.startswith('data:'):
                data_lines.append(line[5:].strip())
        if event_type == 'close':
            closed = True
        if event_type == 'error':
            return None
        if not data_lines:
            continue
        try:
            payload = json.loads('\n'.join(data_lines))
        except ValueError:
            continue
        if event_type == 'ready':
            ready = isinstance(payload, dict) and bool(payload.get('request_message_id') and payload.get('response_message_id'))
            continue
        if not isinstance(payload, dict):
            continue
        value = payload.get('v')
        response = value.get('response') if isinstance(value, dict) else None
        if isinstance(response, dict):
            if response.get('status') == 'FINISHED':
                finished = True
            if isinstance(response.get('fragments'), list):
                fragments = [dict(fragment) for fragment in response['fragments']
                             if isinstance(fragment, dict)]
        path = payload.get('p', last_path)
        if payload.get('p'):
            last_path = path
        if path == 'response/status' and value == 'FINISHED':
            finished = True
        if isinstance(path, str) and re.fullmatch(r'response/fragments/(?:-1|\d+)/content', path):
            if not fragments:
                continue
            idx = int(path.rsplit('/', 2)[1])
            if idx < -len(fragments) or idx >= len(fragments):
                continue
            if isinstance(value, str):
                if payload.get('o', 'APPEND') == 'SET':
                    fragments[idx]['content'] = value
                else:
                    fragments[idx]['content'] = str(fragments[idx].get('content', '')) + value
    answer = ''.join(str(fragment.get('content', '')) for fragment in fragments
                     if fragment.get('type') == 'RESPONSE').strip()
    return answer if ready and finished and closed and answer else None


def activate_background_page(browser):
    """Unfreeze a background page without foregrounding the user's Chrome tab."""
    if 'cdp' in browser:
        try:
            browser['cdp']('Page.setWebLifecycleState', state='active')
        except RuntimeError:
            pass  # Navigation can temporarily detach the page.


def stream_result(browser, minimum_count=0):
    if 'cdp' not in browser:
        return None
    state = browser['js'](STREAM_STATE)
    if state['count'] <= minimum_count or not state['latest']:
        return None
    latest = state['latest']
    if latest['state'] in ('read_error', 'oversized'):
        raise RuntimeError('DeepSeek webpage response observer failed: ' + str(latest['error']))
    if latest['state'] == 'reading':
        return {'state': 'pending'}
    if latest['http'] != 200:
        raise RuntimeError(f"DeepSeek webpage rejected the submission (HTTP {latest['http']})")
    if latest['state'] != 'received':
        return {'state': 'pending'}
    answer = parse_site_stream(browser['js'](STREAM_BODY))
    return {'state': 'completed', 'answer': answer} if answer else {'state': 'incomplete'}


def parse_json_answer(answer):
    fenced = re.search(r"```(?:json)?\s*(.*?)```", answer, re.S)
    try:
        return json.loads(fenced.group(1) if fenced else answer), None
    except ValueError as exc:
        return None, str(exc)


def wait_for_answer(browser, receipt, cfg, min_count, timeout, stream_before=0):
    """Waits for the answer after `min_count` existing answers; never resubmits."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        activate_background_page(browser)
        streamed = stream_result(browser, stream_before)
        state = browser["js"](ANSWER_STATE)
        answer = None
        verified_by = None
        if streamed and streamed['state'] == 'completed':
            answer = streamed['answer']
            verified_by = 'webpage response stream: ready + FINISHED + close'
        elif state["count"] > min_count and state["answer"] and state["settled"]:
            answer = state["answer"]
            verified_by = 'completed assistant message in webpage'
        if answer:
            result = {**receipt, "status": "completed", "answer": answer, "verified_by": verified_by}
            if receipt.get('verified_by') == 'resumed without resubmitting':
                result['verified_by'] = receipt['verified_by']
                result['answer_verified_by'] = verified_by
            if cfg.get("response_format") == "json":
                result["data"], error = parse_json_answer(answer)
                if error:
                    result["parse_error"] = error
            return result
        browser["wait"](1)
    return {**receipt, "status": "pending",
            "next_step": "Keep this session and rerun with resume=true and this thread_id; do not resend"}


def thread_id_from_url(url):
    parsed = urlsplit(url)
    prefix = "/a/chat/s/"
    if parsed.hostname != "chat.deepseek.com" or not parsed.path.startswith(prefix):
        return None
    candidate = parsed.path[len(prefix):].rstrip("/")
    try:
        return str(UUID(candidate)) if candidate == str(UUID(candidate)) else None
    except ValueError:
        return None


def run(cfg, mode, browser):
    timeout = float(cfg.get("timeout_seconds", 120))
    if not 1 <= timeout <= 600:
        raise ValueError("timeout_seconds must be between 1 and 600")
    if cfg.get("response_format", "text") not in {"text", "json"}:
        raise ValueError("response_format must be text or json")
    if cfg.get("resume"):
        return resume(cfg, mode, browser, timeout)
    message = cfg.get("message")
    if not isinstance(message, str) or not message.strip():
        raise ValueError("message is required and must be a non-empty string")
    message = message.strip()
    if cfg.get("project_id") or cfg.get("temporary") or cfg.get("mode", "chat") != "chat":
        raise ValueError("DeepSeek lifecycle actions support ordinary chat only, not Projects or Temporary Chat")
    image = None
    if "image" in cfg:
        image = Path(cfg["image"]).expanduser()
        if not image.is_absolute() or not image.is_file():
            raise ValueError("image must be an existing absolute local file path")
        if image.suffix.lower() not in {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp', '.tif', '.tiff', '.avif'}:
            raise ValueError("Use a PNG, JPEG, WebP, GIF, BMP, TIFF, or AVIF image")
    expected_id = None
    if mode == "new-turn":
        candidate = cfg.get("thread_id", "")
        if not isinstance(candidate, str):
            raise ValueError("thread_id must be a canonical UUID")
        expected_id = thread_id_from_url("https://chat.deepseek.com/a/chat/s/" + candidate)
        if expected_id is None or expected_id != candidate:
            raise ValueError("thread_id must be a canonical UUID")
    js = browser["js"]
    composer = 'textarea[placeholder="Message DeepSeek"]'
    primary = '[role="button"].ds-button--primary'
    if 'cdp' in browser:
        browser['cdp']('Page.addScriptToEvaluateOnNewDocument', source=STREAM_OBSERVER)
    activate_background_page(browser)

    def idle():
        browser["wait_for_element"](composer, timeout=15, visible=True)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            state = js("""(() => {
              const composer = document.querySelector('textarea[placeholder="Message DeepSeek"]');
              const send = document.querySelector('[role="button"].ds-button--primary');
              const attachments = [...document.querySelectorAll('img[alt]')].some(image =>
                image.closest('[role=button]') && !image.closest('.ds-message'));
              return {draft: !!composer?.value || attachments,
                idle: !!composer && !composer.disabled && !!send && send.classList.contains('ds-button--disabled')};
            })()""")
            if state["draft"]:
                raise RuntimeError("Unsent draft or attachment; leave it untouched")
            if state["idle"]:
                return
            browser["wait"](0.2)
        raise RuntimeError("DeepSeek is still generating; nothing was submitted")

    if urlsplit(browser["page_info"]()["url"]).hostname == "chat.deepseek.com":
        idle()
    target = "https://chat.deepseek.com/" + ("a/chat/s/" + expected_id if expected_id else "")
    browser["goto_url"](target)
    browser["wait_for_load"]()
    activate_background_page(browser)
    idle()
    current_id = thread_id_from_url(browser["page_info"]()["url"])
    if current_id != expected_id:
        raise RuntimeError("DeepSeek thread redirect mismatch; nothing was submitted")
    expression = """(() => {
      const message = %s;
      return [...document.querySelectorAll('.ds-message')].filter(element =>
        element.innerText.trim() === message).length;
    })()""" % json.dumps(message)
    before = js(expression)
    answers_before = js(ANSWER_STATE)["count"]
    if image is not None:
        accepted = js("document.querySelector('input[type=file]')?.accept || ''").split(',')
        if image.suffix.lower() not in accepted:
            raise ValueError("DeepSeek's attachment input does not accept this image extension")
        browser["upload_file"]('input[type="file"]', str(image))
    if 'cdp' in browser:
        # Keyboard events can get lost while Chrome suspends a background tab.
        state = js("""(() => {
          const e = document.querySelector('textarea[placeholder="Message DeepSeek"]');
          if (!e || e.disabled) return {ok: false};
          const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
          setter.call(e, %s);
          e.dispatchEvent(new InputEvent('input', {bubbles:true, inputType:'insertText'}));
          return {ok: e.value === %s};
        })()""" % (json.dumps(message), json.dumps(message)))
        if not state['ok']:
            raise RuntimeError('DeepSeek webpage did not accept the draft; nothing was submitted')
    else:
        browser["fill_input"](composer, message)
    browser["wait_for_element"](primary + ':not(.ds-button--disabled)', timeout=60 if image else 15, visible=True)
    if image is not None:
        attached = js("""(() => {
          const name = %s;
          return [...document.querySelectorAll('img[alt]')].some(image =>
            image.alt === name && image.complete && image.naturalWidth > 0);
        })()""" % json.dumps(image.name))
        if not attached:
            raise RuntimeError("Image preview is not ready; nothing was submitted")
    stream_before = js(STREAM_STATE)["count"] if 'cdp' in browser else 0
    browser["click"](primary + ':not(.ds-button--disabled)')
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        activate_background_page(browser)
        current_url = browser["page_info"]()["url"]
        current_id = thread_id_from_url(current_url)
        streamed = stream_result(browser, stream_before)
        accepted = js(expression) > before or bool(streamed)
        cleared = js("document.querySelector('textarea[placeholder=\"Message DeepSeek\"]')?.value === ''")
        if current_id and accepted and cleared and (expected_id is None or current_id == expected_id):
            receipt = {
                "status": "submitted", "mode": mode, "project_id": None,
                "thread_id": current_id,
                "thread_url": "https://chat.deepseek.com/a/chat/s/" + current_id,
                "source_thread_id": cfg.get("source_thread_id"),
                "verified_by": "webpage stream or new matching message, cleared composer, and durable thread URL",
                "user_message_id": None,
            }
            if cfg.get("wait", True) is False:
                return receipt
            return wait_for_answer(browser, receipt, cfg, answers_before, timeout, stream_before)
        browser["wait"](0.2)
    raise RuntimeError("Submission may have succeeded but its receipt was not verified; inspect this session before retrying")


def resume(cfg, mode, browser, timeout):
    thread_id = cfg.get("thread_id") or thread_id_from_url(browser["page_info"]()["url"])
    if not isinstance(thread_id, str) or thread_id_from_url("https://chat.deepseek.com/a/chat/s/" + thread_id) != thread_id:
        raise ValueError("resume needs a canonical thread_id or an open DeepSeek thread")
    url = "https://chat.deepseek.com/a/chat/s/" + thread_id
    if thread_id_from_url(browser["page_info"]()["url"]) != thread_id:
        browser["goto_url"](url)
        browser["wait_for_load"]()
    activate_background_page(browser)
    receipt = {"status": "submitted", "mode": mode, "project_id": None, "thread_id": thread_id,
               "thread_url": url, "source_thread_id": cfg.get("source_thread_id"),
               "verified_by": "resumed without resubmitting", "user_message_id": None}
    return wait_for_answer(browser, receipt, cfg, 0, timeout)