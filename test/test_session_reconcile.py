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
    spec = importlib.util.spec_from_file_location('reconcile_daemon', Path(__file__).resolve().parents[1] / 'session_daemon.py')
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
