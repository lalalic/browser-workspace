"""Live ChatGPT E2E: run explicitly with BW_CHATGPT_E2E=1.

Uses the repository's canonical platforms/ sources and a real browser session.
Never accepts a cleared composer as proof for durable messages.
"""
import json
import os
import subprocess
import tempfile
import uuid
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
    assert response['verified_by'] == 'user-turn', response
    return response


def test_live_new_thread_then_new_turn(session):
    token = uuid.uuid4().hex[:10]
    first = action(session, 'new-thread', {'message': f'Browser Workspace E2E {token}: reply THREAD-OK'})
    assert first['thread_id'] and first['thread_url']
    second = action(session, 'new-turn', {'thread_id': first['thread_id'], 'message': f'Browser Workspace E2E {token}: reply TURN-OK'})
    assert second['thread_id'] == first['thread_id']


def test_live_temporary_submit(session):
    token = uuid.uuid4().hex[:10]
    with tempfile.TemporaryDirectory() as directory:
        cfg = Path(directory) / 'payload.json'
        cfg.write_text(json.dumps({'prompt': f'Browser Workspace Temporary E2E {token}: reply TEMP-OK', 'file': [], 'close_policy': 'after-start'}))
        result = cli('platform', 'run', 'chatgpt', 'temporary-submit', '--session-id', session, '--config', str(cfg))
    assert result['result']['ok'], result
    response = json.loads(result['result']['stdout'].strip().splitlines()[-1])
    assert response['temporary'] and response['status'] == 'submitted' and response['verified_by'] in {'user-turn', 'composer-cleared'}, response
