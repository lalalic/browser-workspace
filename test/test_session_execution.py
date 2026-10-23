import importlib.machinery
import importlib.util
import sys
import threading
import types


def load_execute(monkeypatch):
    managed_chrome = types.ModuleType("managed_chrome")
    managed_chrome.ensure_managed_chrome = lambda: {"enabled": False}
    monkeypatch.setitem(sys.modules, "managed_chrome", managed_chrome)
    admin = types.ModuleType("browser_harness.admin")
    admin.ensure_daemon = lambda **kwargs: {"ok": True, "session_count": 0}
    admin._process_start_time = lambda pid: "test-generation"
    ipc = types.ModuleType("browser_harness._ipc")
    ipc.connect = lambda *a, **kw: (_ for _ in ()).throw(FileNotFoundError())
    helpers = types.ModuleType("browser_harness.helpers")
    helpers.cdp = lambda method, session_id=None, **params: {}
    helpers.current_tab = lambda: {"targetId": "default", "url": "about:blank", "title": ""}
    helpers.switch_tab = lambda target, activate=False: "attached-session"
    helpers.workspace_set_name = lambda _name: None
    helpers.workspace_reset_name = lambda _token: None
    helpers.workspace_set_supported = lambda _supported: None
    helpers.workspace_reset_supported = lambda _token: None
    pkg = types.ModuleType("browser_harness")
    pkg.admin = admin
    pkg._ipc = ipc
    pkg.helpers = helpers
    monkeypatch.setitem(sys.modules, "browser_harness", pkg)
    monkeypatch.setitem(sys.modules, "browser_harness._ipc", ipc)
    monkeypatch.setitem(sys.modules, "browser_harness.admin", admin)
    monkeypatch.setitem(sys.modules, "browser_harness.helpers", helpers)

    loader = importlib.machinery.SourceFileLoader("session_daemon_test", "session_daemon.py")
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_future_import_after_plain_import_compiles(monkeypatch):
    execute = load_execute(monkeypatch).execute
    source = '''import json
from __future__ import annotations

def check(value: Missing) -> Missing:
    return value

{"annotations": check.__annotations__, "json": json.__name__}
'''
    result = execute(source, {})
    assert result["ok"] is True
    assert result["value"] == {"annotations": {"value": "Missing", "return": "Missing"}, "json": "json"}


def test_trailing_result_is_still_returned(monkeypatch):
    execute = load_execute(monkeypatch).execute
    result = execute("value = 40 + 2\nvalue", {})
    assert result["ok"] is True
    assert result["value"] == 42


def test_isolated_sessions_execute_concurrently_on_their_own_cdp_targets(monkeypatch):
    module = load_execute(monkeypatch)
    barrier = threading.Barrier(2)
    observations = []
    module.SESSIONS.update({
        "one": module.Session("one", "Harness", "target-one", True, "cdp-one"),
        "two": module.Session("two", "Harness", "target-two", True, "cdp-two"),
    })

    def fake_cdp(method, session_id=None, **params):
        if method == "Target.getTargets":
            return {"targetInfos": []}
        if method == "Target.getTargetInfo":
            target = params["targetId"]
            return {"targetInfo": {"targetId": target, "url": target, "title": target}}
        observations.append((method, session_id))
        return {}

    module._BROWSER_CDP = fake_cdp

    def run(code, _namespace):
        barrier.wait(timeout=2)
        module.bh.cdp("Runtime.evaluate", expression="1")
        observations.append(("current", module.bh.current_tab()["targetId"]))
        return {"ok": True, "stdout": code, "stderr": ""}

    monkeypatch.setattr(module, "execute", run)
    results = []
    workers = [threading.Thread(target=lambda sid=sid: results.append(module.exec_session(sid, sid, isolated=True)))
               for sid in ("one", "two")]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=3)

    assert all(not worker.is_alive() for worker in workers)
    assert {result["stdout"] for result in results} == {"one", "two"}
    assert set(observations) >= {
        ("Runtime.evaluate", "cdp-one"),
        ("Runtime.evaluate", "cdp-two"),
        ("current", "target-one"),
        ("current", "target-two"),
    }
