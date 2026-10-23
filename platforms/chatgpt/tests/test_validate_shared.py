"""Validation shares target routing and cannot submit."""
import importlib.util
import sys
from pathlib import Path

ACTIONS = Path(__file__).resolve().parents[1] / 'actions'
sys.path.insert(0, str(ACTIONS))
import _lifecycle_common as lifecycle


def test_target_urls_cover_home_project_thread_and_temp():
    url = lifecycle.target_url
    assert url(prompt='probe') == 'https://chatgpt.com/?prompt=probe'
    assert url(project_id='p', prompt='probe') == 'https://chatgpt.com/g/p/project?prompt=probe'
    assert url(thread_id='t', prompt='probe') == 'https://chatgpt.com/c/t?prompt=probe'
    assert url(project_id='p', thread_id='t', prompt='probe') == 'https://chatgpt.com/g/p/c/t?prompt=probe'
    assert url(temporary=True, prompt='probe') == 'https://chatgpt.com/?temporary-chat=true&prompt=probe'


def test_validation_switch_never_fills_or_submits(monkeypatch):
    monkeypatch.setattr(lifecycle, 'send_enabled', lambda: True)
    assert lifecycle.prefilled_submit('probe', send=False) == {'send_enabled': True}


def test_shared_send_gate_matches_temporary_and_lifecycle_states():
    from _readiness import send_ready
    assert send_ready({'send': True})
    assert send_ready({'send': {'enabled': True}, 'text': 'hello', 'attachments': {'names': ['a.txt']}}, prompt='hello', attachments={'a.txt'})
    assert not send_ready({'send': {'enabled': False}, 'text': 'hello'}, prompt='hello')
    assert not send_ready({'send': {'enabled': True}, 'text': 'wrong'}, prompt='hello')
    assert not send_ready({'send': {'enabled': True}, 'text': 'hello', 'attachments': {'names': []}}, prompt='hello', attachments={'a.txt'})


def test_prefilled_validation_never_clicks(monkeypatch):
    monkeypatch.setattr(lifecycle, 'wait_for_send_ready', lambda: True)
    assert lifecycle.prefilled_submit('probe', send=False) == {'send_enabled': True}


def test_prefilled_submit_rechecks_visible_stop_button_before_click(monkeypatch):
    called = []
    monkeypatch.setattr(lifecycle, 'wait_for_send_ready', lambda: True)
    monkeypatch.setattr(lifecycle, 'js', lambda _expression: 'busy', raising=False)
    result = lifecycle.prefilled_submit('probe', before_click=lambda: called.append('boundary'))
    assert result == {'busy': True}
    assert called == ['boundary']


def test_live_actions_use_url_prefill_and_one_shared_submit_path():
    thread=(ACTIONS/'_new_thread.py').read_text()
    turn=(ACTIONS/'_new_turn.py').read_text()
    temp=(ACTIONS/'_temporary_submit.py').read_text()
    for source in (thread, turn):
        assert 'prompt=message' in source
        assert 'submit = lifecycle_common.prefilled_submit' in source
        assert 'receipt=submit(message, before_click=' in source or 'receipt=submit(message)' in source
    assert 'return target_url(temporary=True, prompt=prompt or None)' in temp
