import importlib.util
import sys
import threading
import types
from pathlib import Path
from types import SimpleNamespace


def load_daemon(monkeypatch):
    admin = types.ModuleType('browser_harness.admin')
    admin.ensure_daemon = lambda **kwargs: None
    admin._process_start_time = lambda pid: 'test-generation'
    helpers = types.ModuleType('browser_harness.helpers')
    ipc = types.ModuleType('browser_harness._ipc')
    ipc.connect = lambda *a, **kw: (_ for _ in ()).throw(FileNotFoundError())
    ipc.request = lambda *a, **kw: {'ok': True}
    ipc.ping = lambda *a, **kw: False
    pkg = types.ModuleType('browser_harness')
    pkg.helpers = helpers
    pkg._ipc = ipc
    monkeypatch.setitem(sys.modules, 'browser_harness', pkg)
    monkeypatch.setitem(sys.modules, 'browser_harness.admin', admin)
    monkeypatch.setitem(sys.modules, 'browser_harness.helpers', helpers)
    monkeypatch.setitem(sys.modules, 'browser_harness._ipc', ipc)
    spec = importlib.util.spec_from_file_location('reconcile_daemon', Path(__file__).resolve().parents[1] / 'src/session_daemon.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def session(*targets):
    return SimpleNamespace(owned_target_ids=set(targets), lock=threading.Lock())


def test_reclaimed_idle_and_closed_targets_are_removed(monkeypatch):
    daemon = load_daemon(monkeypatch)
    daemon.SESSIONS.update({'idle': session('a'), 'closed': session('b')})
    daemon.bh.cdp = lambda *_: {'targetInfos': [
        {'targetId': 'a', 'type': 'page', 'url': 'chrome-extension://xyz/workspace.html?workspace=Harness&role=idle&slot=1'}
    ]}
    assert set(daemon.reconcile_sessions()) == {'idle', 'closed'}
    assert daemon.SESSIONS == {}


def test_live_child_keeps_session(monkeypatch):
    daemon = load_daemon(monkeypatch)
    daemon.SESSIONS['alive'] = session('a', 'b')
    daemon.bh.cdp = lambda *_: {'targetInfos': [
        {'targetId': 'a', 'type': 'page', 'url': 'chrome-extension://xyz/workspace.html?role=idle'},
        {'targetId': 'b', 'type': 'page', 'url': 'https://example.org/'},
    ]}
    assert daemon.reconcile_sessions() == []
    assert 'alive' in daemon.SESSIONS


def test_cdp_failure_fails_closed(monkeypatch):
    daemon = load_daemon(monkeypatch)
    daemon.SESSIONS['alive'] = session('a')
    def fail(*_):
        raise ConnectionError('offline')
    daemon.bh.cdp = fail
    assert daemon.reconcile_sessions() == []
    assert 'alive' in daemon.SESSIONS


def test_busy_session_is_not_reaped(monkeypatch):
    daemon = load_daemon(monkeypatch)
    busy = session('a')
    busy.lock.acquire()
    daemon.SESSIONS['busy'] = busy
    daemon.bh.cdp = lambda *_: {'targetInfos': []}
    assert daemon.reconcile_sessions() == []
    assert 'busy' in daemon.SESSIONS
    busy.lock.release()


def test_unrelated_extension_page_not_reclaimed(monkeypatch):
    daemon = load_daemon(monkeypatch)
    daemon.SESSIONS['alive'] = session('a')
    daemon.bh.cdp = lambda *_: {'targetInfos': [
        {'targetId': 'a', 'type': 'page', 'url': 'chrome-extension://xyz/other.html?role=idle'}
    ]}
    assert daemon.reconcile_sessions() == []


def test_idle_gc_closes_only_stale_nonexecuting_sessions(monkeypatch):
    daemon = load_daemon(monkeypatch)
    daemon.SESSION_IDLE_TTL_SECONDS = 120
    stale = session('a'); stale.last_used_at = 1
    fresh = session('b'); fresh.last_used_at = 190
    busy = session('c'); busy.last_used_at = 1; busy.lock.acquire()
    daemon.SESSIONS.update({'stale': stale, 'fresh': fresh, 'busy': busy})
    closed = []
    def fake_stop(sid, idle_before=None):
        assert idle_before == 80
        closed.append(sid)
        daemon.SESSIONS.pop(sid)
        return {'session_id': sid}
    monkeypatch.setattr(daemon, 'stop_session', fake_stop)
    assert daemon.collect_idle_sessions(now=200) == [{'session_id': 'stale'}]
    assert closed == ['stale']
    assert set(daemon.SESSIONS) == {'fresh', 'busy'}
    busy.lock.release()


def test_gc_is_disableable(monkeypatch):
    daemon = load_daemon(monkeypatch)
    daemon.SESSION_IDLE_TTL_SECONDS = 0
    daemon.SESSIONS['stale'] = session('a')
    assert daemon.collect_idle_sessions(now=100000) == []
    assert 'stale' in daemon.SESSIONS


def test_retire_rejects_active_sessions(monkeypatch):
    daemon = load_daemon(monkeypatch)
    daemon.SESSIONS['active'] = session('a')
    result = daemon.handle({'op': 'retire-if-idle'})
    assert result['reason'] == 'active_sessions'
    assert daemon.RETIRING is False


def test_gc_stop_is_fenced_against_recent_activity(monkeypatch):
    daemon = load_daemon(monkeypatch)
    entry = session('tab')
    entry.workspace = 'Harness'
    entry.workspace_supported = False
    entry.target_id = 'tab'
    entry.last_used_at = 190
    daemon.SESSIONS['lease'] = entry
    assert daemon.stop_session('lease', idle_before=80) is None
    assert daemon.SESSIONS['lease'] is entry


def test_gc_stop_skips_executing_session(monkeypatch):
    daemon = load_daemon(monkeypatch)
    entry = session('tab')
    entry.last_used_at = 1
    daemon.SESSIONS['lease'] = entry
    entry.lock.acquire()
    try:
        assert daemon.stop_session('lease', idle_before=80) is None
        assert daemon.SESSIONS['lease'] is entry
    finally:
        entry.lock.release()
