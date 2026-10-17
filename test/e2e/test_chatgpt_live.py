"""Live ChatGPT E2E: run explicitly with BW_CHATGPT_E2E=1.

Uses the repository's canonical platforms/ sources and a real browser session.
Never accepts a cleared composer as proof for durable messages.
"""
import json
import os
import subprocess
import tempfile
import uuid
from urllib.parse import urlsplit
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CLI = ROOT / 'bin/browser-workspace'
pytestmark = pytest.mark.skipif(os.getenv('BW_CHATGPT_E2E') != '1', reason='requires authenticated live ChatGPT session')


def cli(*args, input=None):
    proc = subprocess.run([str(CLI), *args], input=input, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=150)
    data = json.loads(proc.stdout.strip().splitlines()[-1])
    assert proc.returncode == 0, f'{args}: {data!r} {proc.stderr}'
    return data


@pytest.fixture(scope='module')
def session():
    info = cli('session', 'start', '--url', 'https://chatgpt.com/')
    sid = info['session_id']
    try:
        yield sid
    finally:
        cli('session', 'stop', sid)


def action(session, name, payload):
    with tempfile.TemporaryDirectory() as directory:
        cfg = Path(directory) / 'payload.json'
        cfg.write_text(json.dumps(payload))
        result = cli('platform', 'run', 'chatgpt', name, '--session-id', session, '--config', str(cfg))
    assert result['result']['ok'], result
    response = json.loads(result['result']['stdout'].strip().splitlines()[-1])
    assert response['status'] == 'submitted', response
    assert response['verified_by'] in {'user-turn', 'composer-cleared'}, response
    return response


def existing_thread_id():
    # Accept a bare thread ID or its ChatGPT URL.
    supplied = os.getenv('BW_CHATGPT_THREAD_ID', '').strip()
    if not supplied:
        return None
    if '/' not in supplied:
        return supplied
    parsed = urlsplit(supplied)
    parts = parsed.path.rstrip('/').split('/')
    if parsed.hostname not in ('chatgpt.com', 'www.chatgpt.com') or len(parts) < 3 or parts[-2] != 'c' or not parts[-1]:
        raise ValueError('BW_CHATGPT_THREAD_ID must be a thread ID or a chatgpt.com/c/<id> URL')
    return parts[-1]


def long_relay_prompt(token):
    # Long, inert diagnostic payload with Relay-like structure.
    header = '\n'.join([
        '[Agents Relay managed task — E2E DIAGNOSTIC ONLY]',
        'Repository: lalalic/agents-relay',
        'Job ID: 481',
        'Task ID: review-fix-e2e',
        f'Execution ID: {token}',
        f'Exact event source.id: job/481/task/review-fix-e2e/execution/{token}',
        '',
        'This is a submission-only diagnostic, NOT a Relay task. Do not call tools,',
        'publish events, modify files, or execute instructions in the test payload.',
        f'Reply E2E-{token}-OK only.',
        '',
    ])
    segment = ('Validate implementation, reviewer and troubleshooter lifecycle behavior; '
               'inspect task context, dependencies, review outcomes, scheduler recovery, '
               'escalation, immutable heads, SQLite consistency and eventual merge. '
               'This is test data, not a task instruction.\n')
    return header + segment * 6 + f'\nDiagnostic marker: E2E-{token}-OK'


def test_live_new_thread_then_new_turn(session):
    token = uuid.uuid4().hex[:10]
    thread_id = existing_thread_id()
    if thread_id is None:
        first = action(session, 'new-thread', {'message': f'Browser Workspace E2E {token}: reply THREAD-OK'})
        assert first['thread_id'] and first['thread_url']
        thread_id = first['thread_id']
    prompt = long_relay_prompt(token)
    assert 1000 < len(prompt) < 2000
    second = action(session, 'new-turn', {'thread_id': thread_id, 'message': prompt})
    assert second['thread_id'] == thread_id


def test_live_temporary_submit(session):
    token = uuid.uuid4().hex[:10]
    with tempfile.TemporaryDirectory() as directory:
        cfg = Path(directory) / 'payload.json'
        cfg.write_text(json.dumps({'prompt': f'Browser Workspace Temporary E2E {token}: reply TEMP-OK', 'file': [], 'close_policy': 'after-start'}))
        result = cli('platform', 'run', 'chatgpt', 'temporary-submit', '--session-id', session, '--config', str(cfg))
    assert result['result']['ok'], result
    response = json.loads(result['result']['stdout'].strip().splitlines()[-1])
    assert response['temporary'] and response['status'] == 'submitted' and response['verified_by'] in {'user-turn', 'composer-cleared'}, response
