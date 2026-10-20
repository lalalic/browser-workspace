import importlib.util
from pathlib import Path


def load_client():
    spec = importlib.util.spec_from_file_location('upgrade_client', Path(__file__).resolve().parents[1] / 'session_client.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_matching_version_never_retires(monkeypatch):
    client = load_client()
    monkeypatch.setattr(client, 'ping', lambda: {'ok': True, 'version': '0.4.12', 'session_count': 0})
    monkeypatch.setattr(client, 'package_version', lambda: '0.4.12')
    monkeypatch.setattr(client, 'request', lambda *a, **k: (_ for _ in ()).throw(AssertionError('retired')))
    assert client.ensure_daemon()['version'] == '0.4.12'


def test_busy_old_daemon_remains_available(monkeypatch):
    client = load_client()
    monkeypatch.setattr(client, 'ping', lambda: {'ok': True, 'version': '0.4.11', 'session_count': 1})
    monkeypatch.setattr(client, 'package_version', lambda: '0.4.12')
    monkeypatch.setattr(client, 'request', lambda *a, **k: (_ for _ in ()).throw(AssertionError('retired busy daemon')))
    assert client.ensure_daemon()['version'] == '0.4.11'


def test_old_daemon_retirement_refused_preserves_owner(monkeypatch):
    client = load_client()
    monkeypatch.setattr(client, 'ping', lambda: {'ok': True, 'version': '0.4.11', 'session_count': 0})
    monkeypatch.setattr(client, 'package_version', lambda: '0.4.12')
    monkeypatch.setattr(client, 'request', lambda *a, **k: {'ok': False, 'reason': 'active_sessions'})
    assert client.ensure_daemon()['version'] == '0.4.11'
