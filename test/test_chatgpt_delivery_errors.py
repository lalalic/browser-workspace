import json
from pathlib import Path

import chatgpt_delivery_errors as errors
import platform_runner


def test_known_failure_codes():
    cases = {
        'conversation_too_long': 'This conversation is too long to continue. Start a new chat and try again.',
        'thread_load_failed': 'Could not load this ChatGPT conversation',
        'send_not_ready': 'ChatGPT ChatGPT lifecycle continuation readiness was not observed ready',
        'submission_unverified': 'ChatGPT lifecycle submission was not observed',
        'authentication_required': 'Log in to ChatGPT',
        'rate_limited': 'HTTP 429 Too Many Requests',
        'thread_redirect_mismatch': 'ChatGPT thread redirect mismatch',
        'thread_creation_failed': 'ChatGPT did not assign a durable thread id',
    }
    for code, message in cases.items():
        outcome = errors.classify(message, 'new-turn')
        assert outcome['code'] == code
        assert outcome['ok'] is False
        assert set(outcome) == {'ok', 'code', 'message'}


def test_normalization_suppresses_traceback_but_logs_full_error(tmp_path, monkeypatch):
    monkeypatch.setattr(errors, 'LOG', tmp_path / 'trace.jsonl')
    raw = 'Traceback (most recent call last):\nRuntimeError: ChatGPT lifecycle continuation readiness was not observed ready'
    result = errors.normalize_failure({'ok': False, 'stderr': raw}, 'new-turn')
    assert result['code'] == 'send_not_ready'
    assert 'Traceback' not in str(result)
    assert json.loads((tmp_path / 'trace.jsonl').read_text())['error'] == raw
    assert errors.normalize_failure({'ok': True, 'stdout': 'submitted'}, 'new-turn') == {'ok': True, 'stdout': 'submitted'}


def test_platform_runner_failure_uses_compact_json(monkeypatch, tmp_path):
    monkeypatch.setattr(errors, 'LOG', tmp_path / 'errors.jsonl')
    cfg = tmp_path / 'payload.json'
    cfg.write_text(json.dumps({'thread_id': 'thread1', 'message': 'hello'}))
    monkeypatch.setattr(platform_runner, 'request', lambda _payload: {
        'ok': False, 'stdout': '',
        'stderr': 'Traceback (most recent call last):\nRuntimeError: Could not load this ChatGPT conversation'
    })
    result = platform_runner.run_platform_action('chatgpt', 'new-turn', config_path=str(cfg))
    assert result['result']['code'] == 'thread_load_failed'
    assert 'stderr' not in result['result']
    assert 'Traceback' not in json.dumps(result)


def test_new_thread_failure_and_transport_exception(monkeypatch, tmp_path):
    monkeypatch.setattr(errors, 'LOG', tmp_path / 'errors.jsonl')
    cfg = tmp_path / 'payload.json'
    cfg.write_text(json.dumps({'message': 'hello'}))

    def fail(_payload):
        raise TimeoutError('daemon IPC timed out')

    monkeypatch.setattr(platform_runner, 'request', fail)
    output = platform_runner.run_platform_action('chatgpt', 'new-thread', config_path=str(cfg), session_id='s1')
    assert output['result']['code'] == 'execution_timeout'
    assert 'stderr' not in output['result']
