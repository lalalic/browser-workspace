import importlib.util
from pathlib import Path


def load_client():
    spec = importlib.util.spec_from_file_location('upgrade_client', Path(__file__).resolve().parents[1] / 'src/session_client.py')
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


def test_idle_same_version_cache_refreshes_changed_source(tmp_path, monkeypatch):
    client = load_client()
    source = tmp_path / "source"
    source.mkdir()
    (source / "__init__.py").write_text('__version__ = "0.4.22"')
    (source / "session_daemon.py").write_text("old = True")
    monkeypatch.setattr(client, "ROOT", source)
    monkeypatch.setattr(client, "RUNTIME_DIR", tmp_path / "runtime")
    monkeypatch.setattr(client, "package_version", lambda: "0.4.22")
    monkeypatch.setattr(client, "owner_is_running", lambda: False)
    first = client.runtime_source()
    assert (first / "session_daemon.py").read_text() == "old = True"
    (source / "session_daemon.py").write_text("new = True")
    second = client.runtime_source()
    assert second == first
    assert (second / "session_daemon.py").read_text() == "new = True"
    assert not list((tmp_path / "runtime/packages").glob("*.previous-*"))


def test_busy_daemon_prevents_cached_source_replacement(tmp_path, monkeypatch):
    client = load_client()
    source = tmp_path / "source"
    source.mkdir()
    (source / "__init__.py").write_text('__version__ = "0.4.22"')
    monkeypatch.setattr(client, "ROOT", source)
    monkeypatch.setattr(client, "RUNTIME_DIR", tmp_path / "runtime")
    monkeypatch.setattr(client, "package_version", lambda: "0.4.22")
    monkeypatch.setattr(client, "owner_is_running", lambda: False)
    target = client.runtime_source()
    (source / "new.py").write_text("changed")
    monkeypatch.setattr(client, "owner_is_running", lambda: True)
    import pytest
    with pytest.raises(RuntimeError, match="update deferred"):
        client.runtime_source()
    assert not (target / "new.py").exists()
