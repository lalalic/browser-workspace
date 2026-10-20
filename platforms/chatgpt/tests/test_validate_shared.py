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
    monkeypatch.setattr(lifecycle, 'fill_prompt', lambda _: (_ for _ in ()).throw(AssertionError('filled')))
    monkeypatch.setattr(lifecycle, 'send_enabled', lambda: True)
    assert lifecycle.submit('probe', send=False) == {'send_enabled': True}
