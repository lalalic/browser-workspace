"""Stable, non-throwing ChatGPT delivery error protocol. Never expose traceback to callers."""
from __future__ import annotations
import json
import re
import uuid
from pathlib import Path

LOG = Path.home() / '.config/browser-workspace/runtime/chatgpt-delivery-errors.jsonl'


def classify(error: str, action: str) -> dict:
    lower = error.lower()
    patterns = [
        ('conversation_too_long', r'conversation_too_long|conversation is too long to continue|conversation too long'),
        ('thread_load_failed', r'thread_load_failed|could not load this chatgpt conversation|failed to load conversation'),
        ('authentication_required', r'login required|log in to chatgpt|session expired|sign in to chatgpt'),
        ('rate_limited', r'rate.limit|too many requests|http 429|usage limit'),
        ('invalid_thread_id', r'invalid thread.id|thread.id is required|malformed thread'),
        ('thread_redirect_mismatch', r'thread redirect mismatch'),
        ('conversation_busy', r'conversation is busy|turn completion.*not observed ready'),
        ('send_not_ready', r'lifecycle continuation readiness was not observed ready|send button.*disabled'),
        ('composer_not_found', r'composer.*not observed ready|composer.*not found'),
        ('composer_input_failed', r'composer rejected|input failed|prompt.*mismatch'),
        ('send_click_failed', r'send button changed before|send button.*click'),
        ('submission_unverified', r'submission.*not observed|post.submit.*unverified|cleared composer'),
        ('thread_creation_failed', r'did not assign a durable thread id'),
        ('project_not_found', r'project not found'),
        ('project_access_denied', r'project.*access denied|permission.*project'),
        ('attachment_failed', r'attachment.*failed|upload.*failed'),
        ('attachment_processing_timeout', r'attachment.*timeout|attachment.*not observed ready'),
        ('session_unavailable', r'unknown session|session not found|session.*closed'),
        ('browser_unavailable', r'chrome.*unavailable|cdp.*disconnect|daemon.*unreachable'),
        ('execution_timeout', r'timed out|timeout|runtime.evaluate'),
    ]
    code = next((code for code, pattern in patterns if re.search(pattern, lower)), 'delivery_failed')
    messages = {
        'send_not_ready': 'Prompt entered, but Send button did not become ready',
        'thread_load_failed': 'ChatGPT conversation could not be loaded',
        'conversation_too_long': 'Conversation is too long to continue',
        'submission_unverified': 'Submission could not be confirmed',
    }
    return {'ok': False, 'code': code, 'message': messages.get(code, code.replace('_', ' ').capitalize())}


def normalize_failure(result: dict, action: str) -> dict:
    if result.get('ok') is not False:
        return result
    raw = str(result.get('stderr') or result.get('error') or '')
    diagnostic_id = uuid.uuid4().hex
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open('a') as handle:
            handle.write(json.dumps({'diagnostic_id': diagnostic_id, 'action': action, 'error': raw}, ensure_ascii=False) + '\n')
    except OSError:
        pass
    normalized = classify(raw, action)
    if 'cleanup' in result:
        normalized['cleanup'] = result['cleanup']
    return normalized
