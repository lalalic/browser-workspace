import json
import re
import time
from urllib.parse import quote, unquote, urlsplit


BASE_URL = "https://chat.z.ai/"
COMPOSER = 'textarea[placeholder="Send a Message"]'
SEND_BUTTON = "#send-message-button"



# Watch the signed-in page's own completion response; never capture request
# payloads or auth headers. Install before navigation (app may cache fetch).
STREAM_OBSERVER = r"""(() => {
 if (window.__webhelmZStream?.version === 1) return;
 const observer = {version: 1, entries: []};
 window.__webhelmZStream = observer;
 const nativeFetch = window.fetch;
 window.fetch = function (...args) {
   const url = String(args[0]?.url || args[0] || '');
   const request = nativeFetch.apply(this, args);
   if (!/\/api(?:\/v2)?\/chat\/(?:completions|continue)(?:\?|$)/.test(url)) return request;
   return request.then(response => {
     const item = {state: 'reading', status: response.status, body: '', error: ''};
     observer.entries.push(item);
     if (observer.entries.length > 8) observer.entries.shift();
     response.clone().text().then(body => {
       if (body.length > 1500000) {item.state = 'oversized'; item.error = 'Z.ai stream exceeds 1.5MB';}
       else {item.state = 'received'; item.body = body;}
     }).catch(err => {item.state = 'read_error'; item.error = String(err);});
     return response;
   });
 };
})()"""
STREAM_STATE = """(() => {
 const entries = window.__webhelmZStream?.entries || [];
 return {count: entries.length, latest: entries.length ? {
   state: entries.at(-1).state, status: entries.at(-1).status,
   error: entries.at(-1).error
 } : null};
})()"""
STREAM_BODY = """(() => window.__webhelmZStream?.entries.at(-1)?.body || '')()"""


def parse_site_stream(body):
    """Require a Z.ai chat:completion event with explicit done and answer."""
    if not isinstance(body, str):
        return None
    content = ''
    finished = False
    for block in re.split(r'\r?\n\r?\n', body):
        lines = [line[5:].strip() for line in block.splitlines() if line.startswith('data:')]
        if not lines:
            continue
        try:
            payload = json.loads('\n'.join(lines))
        except ValueError:
            continue
        if not isinstance(payload, dict):
            continue
        if payload.get('type') == 'error':
            raise RuntimeError('Z.ai returned an error event')
        if payload.get('type') != 'chat:completion':
            continue
        chunk = payload.get('data')
        if not isinstance(chunk, dict) or chunk.get('scope', 'legacy') != 'legacy':
            continue
        if chunk.get('error'):
            raise RuntimeError('Z.ai completion contains an error')
        phase = chunk.get('phase', 'other')
        if phase not in ('analysis', 'thinking', 'reasoning', 'tool_call', 'tool_response'):
            if isinstance(chunk.get('content'), str):
                content = chunk['content']
            elif isinstance(chunk.get('edit_content'), str) and isinstance(chunk.get('edit_index'), int):
                index = chunk['edit_index']
                if 0 <= index <= len(content):
                    content = content[:index] + chunk['edit_content']
            elif isinstance(chunk.get('delta_content'), str):
                content += chunk['delta_content']
        if chunk.get('done') is True:
            finished = True
    return content.strip() if finished and content.strip() else None


def stream_result(browser, baseline=0):
    if 'cdp' not in browser:
        return None
    state = browser['js'](STREAM_STATE)
    if state['count'] <= baseline or not state['latest']:
        return None
    entry = state['latest']
    if entry['state'] in ('read_error', 'oversized'):
        raise RuntimeError('Z.ai webpage stream observer failed: ' + str(entry['error']))
    if entry['status'] != 200:
        raise RuntimeError('Z.ai completion HTTP ' + str(entry['status']))
    if entry['state'] == 'reading':
        return {'state': 'pending'}
    if entry['state'] == 'received':
        answer = parse_site_stream(browser['js'](STREAM_BODY))
        return {'state': 'completed', 'answer': answer} if answer else {'state': 'incomplete'}
    return {'state': 'pending'}


def answer_result(receipt, cfg, answer):
    result = {**receipt, 'status': 'completed', 'answer': answer,
              'verified_by': 'Z.ai webpage SSE chat:completion done=true'}
    if cfg.get('response_format') == 'json':
        try:
            result['data'] = json.loads(answer.strip())
        except ValueError as exc:
            result['data'] = None
            result['parse_error'] = str(exc)
    return result


def wait_for_answer(browser, receipt, cfg, deadline, baseline):
    while time.monotonic() < deadline:
        current_id = thread_id_from_url(browser['page_info']().get('url', ''))
        if current_id and (not receipt['thread_id'] or receipt['thread_id'] == current_id):
            receipt['thread_id'] = current_id
            receipt['thread_url'] = target_url(current_id)
        observed = stream_result(browser, baseline)
        if observed and observed['state'] == 'completed' and receipt['thread_id']:
            return answer_result(receipt, cfg, observed['answer'])
        time.sleep(0.2)
    return {**receipt, 'status': 'pending',
            'next_step': 'resume=true in the SAME browser session; never resubmit'}


def resume(cfg, mode, browser, deadline):
    current_id = thread_id_from_url(browser['page_info']().get('url', ''))
    if cfg.get('thread_id') and cfg['thread_id'] != current_id:
        raise RuntimeError('Resume requires original live thread; no resubmission')
    receipt = {'status': 'submitted', 'mode': mode, 'project_id': None,
               'thread_id': current_id,
               'thread_url': target_url(current_id) if current_id else None,
               'source_thread_id': cfg.get('source_thread_id'),
               'user_message_id': None}
    marker = browser['js']('''(() => {
      const o = window.__webhelmZStream;
      const marker = o?.submission;
      const lastMessage = [...document.querySelectorAll('.user-message')].at(-1)?.innerText.trim() || '';
      return marker && {baseline: marker.baseline,
        valid: lastMessage.startsWith(marker.message),
        currentCount: o.entries.length};
    })()''') if 'cdp' in browser else None
    if not marker or not marker['valid']:
        return {**receipt, 'status': 'pending',
                'next_step': 'No matching previous submission in this tab; do not resend'}
    if marker['currentCount'] <= marker['baseline']:
        return {**receipt, 'status': 'pending',
                'next_step': 'Original submission has no complete observed stream; do not resend'}
    return wait_for_answer(browser, receipt, cfg, deadline, marker['baseline'])

def thread_id_from_url(url):
    parsed = urlsplit(url)
    if parsed.hostname != "chat.z.ai" or not parsed.path.startswith("/c/"):
        return None
    candidate = parsed.path[len("/c/"):].split("/", 1)[0]
    return unquote(candidate) or None


def target_url(thread_id=None):
    if thread_id is None:
        return BASE_URL
    return BASE_URL + "c/" + quote(thread_id, safe="")


def page_state(browser):
    return browser["js"]("""(() => {
      const composer=document.querySelector('textarea[placeholder="Send a Message"]');
      return {
        composer: !!composer,
        text: composer?.value || "",
        attachmentCount: [...document.querySelectorAll('input[type="file"]')]
          .reduce((count, input) => count + (input.files?.length || 0), 0)
      };
    })()""")


def message_count(browser, message):
    expression = """(() => {
      const expected = %s;
      return [...document.querySelectorAll('.user-message')].filter(element =>
        (element.innerText.trim() === expected || (element.innerText.trim().startsWith(expected) && /^\\s*Show full message\\s*$/.test(element.innerText.trim().slice(expected.length))))).length;
    })()""" % json.dumps(message)
    return browser["js"](expression)


def reject_unsent_content(state):
    if state["text"].strip() or state["attachmentCount"]:
        raise RuntimeError("Unsent draft or attachment; leave it untouched")


def run(cfg, mode, browser):
    try:
        timeout = float(cfg.get('timeout_seconds', 120))
    except (TypeError, ValueError) as exc:
        raise ValueError('timeout_seconds must be between 1 and 600') from exc
    if not 1 <= timeout <= 600:
        raise ValueError('timeout_seconds must be between 1 and 600')
    if cfg.get('response_format', 'text') not in ('text', 'json'):
        raise ValueError('response_format must be text or json')
    if cfg.get('project_id') or cfg.get('temporary') or cfg.get('mode', 'chat') != 'chat':
        raise ValueError('Z.ai lifecycle actions support ordinary chat only')
    deadline = time.monotonic() + timeout
    if cfg.get('resume'):
        return resume(cfg, mode, browser, deadline)

    message = cfg.get('message')
    if not isinstance(message, str) or not message.strip():
        raise ValueError('message is required and must be nonempty')
    message = message.strip()
    expected_id = None
    if mode == 'new-turn':
        candidate = cfg.get('thread_id')
        if not isinstance(candidate, str) or not candidate.strip():
            raise ValueError('thread_id is required')
        expected_id = thread_id_from_url(target_url(candidate.strip()))
        if expected_id != candidate.strip():
            raise ValueError('thread_id must be a single URL path segment')
    elif mode != 'new-thread':
        raise ValueError('mode must be new-thread or new-turn')

    if urlsplit(browser['page_info']().get('url', '')).hostname == 'chat.z.ai':
        reject_unsent_content(page_state(browser))
    if 'cdp' in browser:
        browser['cdp']('Page.addScriptToEvaluateOnNewDocument', source=STREAM_OBSERVER)
    browser['goto_url'](target_url(expected_id))
    browser['wait_for_load']()
    browser['wait_for_element'](COMPOSER, timeout=15, visible=True)
    if 'cdp' in browser:
        # If goto_url reused the same SPA document, the new-document hook
        # has not yet run. Install in the current document as well.
        browser['js'](STREAM_OBSERVER)
    reject_unsent_content(page_state(browser))
    current_id = thread_id_from_url(browser['page_info']().get('url', ''))
    if mode == 'new-turn' and current_id != expected_id:
        raise RuntimeError('Z.ai thread redirect mismatch; nothing was submitted')
    if mode == 'new-thread' and current_id is not None:
        raise RuntimeError('Z.ai did not open a new chat; nothing was submitted')

    before_count = message_count(browser, message)
    stream_baseline = browser['js'](STREAM_STATE)['count'] if 'cdp' in browser else 0
    if 'cdp' in browser:
        # Keep provenance across a pending action. Resume must match this
        # submission, never a previous stream in the same tab.
        browser['js']('''(() => {
          const observer = window.__webhelmZStream;
          if (observer) observer.submission = {baseline: %d, message: %s};
        })()''' % (stream_baseline, json.dumps(message)))
    browser['click'](COMPOSER)
    if 'cdp' in browser:
        browser['cdp']('Input.insertText', text=message)
    else:
        browser['fill_input'](COMPOSER, message)
    browser['wait_for_element'](f'{SEND_BUTTON}:not(:disabled)', timeout=15, visible=True)
    browser['click'](SEND_BUTTON)
    receipt = {'status': 'submitted', 'mode': mode, 'project_id': None,
               'thread_id': None, 'thread_url': None,
               'source_thread_id': cfg.get('source_thread_id') if mode == 'new-thread' else None,
               'user_message_id': None}
    while time.monotonic() < deadline:
        current_id = thread_id_from_url(browser['page_info']().get('url', ''))
        if current_id and expected_id and current_id != expected_id:
            raise RuntimeError('Z.ai unexpected thread after submission')
        state = page_state(browser)
        accepted = message_count(browser, message) > before_count
        observed = stream_result(browser, stream_baseline)
        if current_id and accepted and not state['text']:
            receipt['thread_id'] = current_id
            receipt['thread_url'] = target_url(current_id)
            receipt['verified_by'] = 'matching user message + cleared composer + durable thread URL'
            if cfg.get('wait', True) is False:
                return receipt
            if observed and observed['state'] == 'completed':
                return answer_result(receipt, cfg, observed['answer'])
            return wait_for_answer(browser, receipt, cfg, deadline, stream_baseline)
        time.sleep(0.2)
    return {**receipt, 'status': 'pending',
            'next_step': 'Submission might have succeeded; resume in same session, never resend'}
