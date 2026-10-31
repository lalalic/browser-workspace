"""Concurrency regression: one Browser Harness socket, explicit per-Session CDP routing."""
import importlib.util
import io
import sys
import threading
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_daemon(monkeypatch):
    admin = types.ModuleType('browser_harness.admin')
    admin.ensure_daemon = lambda **kwargs: None
    admin._process_start_time = lambda pid: 'test-generation'
    ipc = types.ModuleType('browser_harness._ipc')
    ipc.connect = lambda *a, **kw: (_ for _ in ()).throw(FileNotFoundError())
    ipc.ping = lambda *a, **kw: False
    helpers = types.ModuleType('browser_harness.helpers')
    requests = []
    meta = {'current': 'original'}
    def send(req, response_timeout=5.0):
        if req.get('meta') == 'drain_events':
            events = meta.pop('events', [])
            return {'events': events}
        if req.get('meta') == 'session':
            return {'session_id': meta['current']}
        if req.get('meta') == 'set_session':
            meta['current'] = req['session_id']
            return {'session_id': meta['current']}
        raise ValueError(req)
    def cdp(method, session_id=None, _response_timeout=5.0, **params):
        requests.append((method, session_id, params))
        if method == 'Target.getTargetInfo':
            tid = params['targetId']
            return {'targetInfo': {'targetId': tid, 'url': f'https://{tid}.test/', 'title': tid}}
        if method == 'Target.getTargets':
            return {'targetInfos': [{'targetId': 'target-a', 'type': 'page'}, {'targetId': 'target-b', 'type': 'page'}]}
        return {'result': {'value': session_id}}
    helpers.cdp = cdp
    helpers._send = send
    helpers.current_tab = lambda: helpers._send({'meta': 'current_tab'})
    helpers.js = lambda expr, target_id=None: helpers.cdp('Runtime.evaluate', expression=expr, **({'session_id': target_id} if target_id else {}))
    helpers.click = lambda selector: helpers.js(f'click:{selector}')
    helpers.workspace_set_name = lambda *_: None
    helpers.workspace_reset_name = lambda *_: None
    helpers.workspace_set_supported = lambda *_: None
    helpers.workspace_reset_supported = lambda *_: None
    package = types.ModuleType('browser_harness')
    package.helpers = helpers
    package.admin = admin
    package._ipc = ipc
    for name, module in [('browser_harness',package),('browser_harness.admin',admin),('browser_harness._ipc',ipc),('browser_harness.helpers',helpers)]:
        monkeypatch.setitem(sys.modules, name, module)
    spec = importlib.util.spec_from_file_location('isolated_daemon', ROOT / 'src/session_daemon.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, requests, meta


def add_sessions(daemon):
    for sid in ['a', 'b']:
        session = daemon.Session(sid, 'Harness', f'target-{sid}', False)
        session.cdp_session_id = f'cdp-{sid}'
        session.attached_cdp_ids.add(f'cdp-{sid}')
        daemon.SESSIONS[sid] = session


def test_concurrent_exec_routed_by_own_cdp_session_not_global_switch(monkeypatch):
    daemon, requests, meta = load_daemon(monkeypatch)
    add_sessions(daemon)
    barrier = threading.Barrier(2)
    for session in daemon.SESSIONS.values():
        session.namespace['barrier'] = barrier
    monkeypatch.setattr(sys, 'stdout', io.StringIO())
    monkeypatch.setattr(sys, 'stderr', io.StringIO())
    daemon.install_session_output()
    results = {}
    errors = []
    code = "barrier.wait(timeout=3)\nprint(target_id)\nprint(current_tab()['targetId'])\nclick('#send')\njs('document.title')"
    def worker(sid):
        try:
            results[sid] = daemon.exec_session(sid, code)
        except Exception as exc:
            errors.append(exc)
    workers = [threading.Thread(target=worker, args=(sid,)) for sid in ('a', 'b')]
    for worker in workers: worker.start()
    for worker in workers: worker.join(timeout=5)
    assert not errors
    assert all(not worker.is_alive() for worker in workers), 'actions serialized behind global lock'
    assert set(results) == {'a', 'b'}
    for sid in ('a', 'b'):
        result = results[sid]
        assert result['ok'] is True, result
        assert result['stdout'] == f'target-{sid}\ntarget-{sid}\n'
        assert result['value'] == {'result': {'value': f'cdp-{sid}'}}
    assert ('Runtime.evaluate', 'cdp-a', {'expression': 'click:#send'}) in requests
    assert ('Runtime.evaluate', 'cdp-b', {'expression': 'click:#send'}) in requests
    assert meta['current'] == 'original', 'worker exec must not alter daemon default attached tab'


def test_events_are_fanned_out_and_never_stolen(monkeypatch):
    daemon, _, meta = load_daemon(monkeypatch)
    add_sessions(daemon)
    meta['events'] = [{'session_id': 'cdp-a', 'method': 'Network.loadingFinished'}, {'session_id': 'cdp-b', 'method': 'Network.requestWillBeSent'}]
    def drain(sid):
        session = daemon.SESSIONS[sid]
        token = daemon._EXECUTION_SESSION.set(session)
        try:
            return daemon.bh._send({'meta': 'drain_events'})['events']
        finally:
            daemon._EXECUTION_SESSION.reset(token)
    assert drain('a') == [{'session_id': 'cdp-a', 'method': 'Network.loadingFinished'}]
    assert drain('b') == [{'session_id': 'cdp-b', 'method': 'Network.requestWillBeSent'}]
    assert drain('a') == []


def test_session_cannot_switch_to_foreign_target(monkeypatch):
    daemon, _, _ = load_daemon(monkeypatch)
    add_sessions(daemon)
    s = daemon.SESSIONS['a']
    token = daemon._EXECUTION_SESSION.set(s)
    try:
        try:
            daemon.bh._send({'meta': 'set_session', 'target_id': 'target-b', 'session_id': 'cdp-b'})
            assert False, 'cross-session switch must be rejected'
        except RuntimeError as exc:
            assert 'outside' in str(exc)
        assert s.target_id == 'target-a'
    finally:
        daemon._EXECUTION_SESSION.reset(token)


def test_browser_domain_cdp_remains_browser_scoped(monkeypatch):
    daemon, calls, _ = load_daemon(monkeypatch)
    add_sessions(daemon)
    token = daemon._EXECUTION_SESSION.set(daemon.SESSIONS['a'])
    try:
        daemon.bh.cdp('Browser.getVersion')
        daemon.bh.cdp('Target.getTargets')
        daemon.bh.cdp('Runtime.evaluate', expression='42')
    finally:
        daemon._EXECUTION_SESSION.reset(token)
    assert calls[0][1] is None
    assert calls[1][1] is None
    assert calls[2][1] == 'cdp-a'


def test_dialog_does_not_leak_across_sessions(monkeypatch):
    daemon, _, meta = load_daemon(monkeypatch)
    add_sessions(daemon)
    meta['events'] = [{'session_id': 'cdp-a', 'method': 'Page.javascriptDialogOpening',
                       'params': {'type': 'alert', 'message': 'A only'}}]
    a = daemon.SESSIONS['a']
    b = daemon.SESSIONS['b']
    token = daemon._EXECUTION_SESSION.set(b)
    try:
        assert daemon.bh._send({'meta': 'pending_dialog'}) == {'dialog': None}
    finally:
        daemon._EXECUTION_SESSION.reset(token)
    token = daemon._EXECUTION_SESSION.set(a)
    try:
        assert daemon.bh._send({'meta': 'pending_dialog'}) == {'dialog': {'type': 'alert', 'message': 'A only'}}
        assert daemon.bh._send({'meta': 'drain_events'})['events'][0]['method'] == 'Page.javascriptDialogOpening'
    finally:
        daemon._EXECUTION_SESSION.reset(token)


def test_session_start_keeps_harness_default_attachment_untouched(monkeypatch):
    daemon, requests, meta = load_daemon(monkeypatch)
    daemon.bh.workspace_extension_status = lambda: {'supported': False}
    daemon.RETIRING = False
    created = []
    def new_tab(_url):
        tid = f'target-{len(created)}'
        created.append(tid)
        daemon.bh._send({'meta': 'set_session', 'target_id': tid, 'session_id': f'cdp-{tid}'})
        return tid
    daemon.bh.new_tab = new_tab
    a = daemon.start_session()
    b = daemon.start_session()
    assert a['target_id'] != b['target_id']
    assert meta['current'] == 'original'
    assert daemon.SESSIONS[a['session_id']].cdp_session_id == 'cdp-target-0'
    assert daemon.SESSIONS[b['session_id']].cdp_session_id == 'cdp-target-1'
    assert {(method, sid) for method, sid, _ in requests if method.endswith('.enable')} == {
        (f'{domain}.enable', sid) for domain in ('Page','DOM','Runtime','Network')
        for sid in ('cdp-target-0','cdp-target-1')
    }


def test_direct_raw_tab_creation_and_foreign_close_rejected(monkeypatch):
    daemon, calls, _ = load_daemon(monkeypatch)
    add_sessions(daemon)
    context = daemon._EXECUTION_SESSION.set(daemon.SESSIONS['a'])
    try:
        for method, params in [('Target.createTarget', {'url': 'about:blank'}),
                               ('Target.closeTarget', {'targetId': 'target-b'})]:
            try:
                daemon.bh.cdp(method, **params)
                assert False, 'must reject foreign raw tab operation'
            except RuntimeError:
                pass
    finally:
        daemon._EXECUTION_SESSION.reset(context)
    assert not any(c[0] in ('Target.createTarget','Target.closeTarget') for c in calls)
