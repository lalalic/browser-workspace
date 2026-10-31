import importlib.machinery
import importlib.util
import sys
import types


def load_execute(monkeypatch):
    admin = types.ModuleType("browser_harness.admin")
    admin.ensure_daemon = lambda **kwargs: {"ok": True, "session_count": 0}
    admin._process_start_time = lambda pid: "test-generation"
    ipc = types.ModuleType("browser_harness._ipc")
    ipc.connect = lambda *a, **kw: (_ for _ in ()).throw(FileNotFoundError())
    helpers = types.ModuleType("browser_harness.helpers")
    helpers.cdp = lambda method, **kwargs: {}
    helpers._send = lambda req, **kwargs: {}
    pkg = types.ModuleType("browser_harness")
    pkg.admin = admin
    pkg._ipc = ipc
    pkg.helpers = helpers
    monkeypatch.setitem(sys.modules, "browser_harness", pkg)
    monkeypatch.setitem(sys.modules, "browser_harness._ipc", ipc)
    monkeypatch.setitem(sys.modules, "browser_harness.admin", admin)
    monkeypatch.setitem(sys.modules, "browser_harness.helpers", helpers)

    loader = importlib.machinery.SourceFileLoader("session_daemon_test", "src/session_daemon.py")
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.execute


def test_future_import_after_plain_import_compiles(monkeypatch):
    execute = load_execute(monkeypatch)
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
    execute = load_execute(monkeypatch)
    result = execute("value = 40 + 2\nvalue", {})
    assert result["ok"] is True
    assert result["value"] == 42
