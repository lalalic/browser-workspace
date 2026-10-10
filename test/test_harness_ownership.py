"""Ownership regression tests use only local pipes/processes; never launch Chrome."""
import ast
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DAEMON_SOURCE = ROOT / "src/browser_harness/daemon.py"


def isolated_functions(*names):
    source = ast.parse(DAEMON_SOURCE.read_text())
    nodes = [n for n in source.body if isinstance(n, ast.FunctionDef) and n.name in names]
    assert len(nodes) == len(names)
    return compile(ast.Module(body=nodes, type_ignores=[]), str(DAEMON_SOURCE), "exec")


def test_parent_identity_refuses_pid_reuse():
    ns = {
        "OWNER_PID": 123,
        "OWNER_STARTED": "generation-a",
        "_process_start_time": lambda pid: "generation-b",
    }
    exec(isolated_functions("owner_alive"), ns)
    assert ns["owner_alive"]() is False
    ns["_process_start_time"] = lambda pid: "generation-a"
    assert ns["owner_alive"]() is True
    ns["OWNER_STARTED"] = None
    assert ns["owner_alive"]() is False


def test_owner_watchdog_exits_on_pipe_eof(tmp_path):
    """The executable watchdog reacts to a lost parent pipe (including re-exec)."""
    if os.name != "posix":
        return
    code = isolated_functions("monitor_owner")
    import marshal
    watcher = """
import marshal, os, sys, time
OWNER_TOKEN = 'this-runtime'
OWNER_PIPE_FD = int(sys.argv[1])
owner_alive = lambda: True
exec(marshal.loads(bytes.fromhex(sys.argv[2])), globals())
monitor_owner()
"""
    read_fd, write_fd = os.pipe()
    try:
        proc = subprocess.Popen(
            [sys.executable, "-c", watcher, str(read_fd), marshal.dumps(code).hex()],
            pass_fds=(read_fd,), stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
        os.close(read_fd)
        read_fd = None
        assert proc.poll() is None
        os.close(write_fd)  # emulate parent SIGKILL/exec's close-on-exec EOF
        write_fd = None
        assert proc.wait(timeout=4) == 0
    finally:
        if read_fd is not None:
            os.close(read_fd)
        if write_fd is not None:
            os.close(write_fd)
        if "proc" in locals() and proc.poll() is None:
            proc.kill()
            proc.wait()


def test_legacy_unowned_harness_does_not_start_watchdog():
    ns = {"OWNER_TOKEN": None, "threading": None}
    exec(isolated_functions("begin_owner_monitor"), ns)
    ns["begin_owner_monitor"]()  # compatible with canonical pre-ownership runtimes


def test_session_shutdown_uses_token_not_unrelated_pid():
    code = (ROOT / "session_daemon.py").read_text()
    harness = DAEMON_SOURCE.read_text()
    assert "'owner_token': HARNESS_OWNER_TOKEN" in code
    assert 'req.get("owner_token") != OWNER_TOKEN' in harness
    assert '"error": "not harness owner"' in harness
    assert "os.kill(" not in harness[harness.index("def monitor_owner"):harness.index("_MAC_PROFILES")]


def test_spawn_serialization_and_packaged_runtime_match():
    admin = (ROOT / "src/browser_harness/admin.py").read_text()
    assert "with _spawn_lock(name, timeout=startup_wait)" in admin
    assert "if daemon_alive(name):" in admin
    assert 'pass_fds' in admin
    for path in ("session_daemon.py", "src/browser_harness/admin.py", "src/browser_harness/daemon.py"):
        package_path = ROOT / "src/browser_workspace_app" / path
        assert (ROOT / path).read_bytes() == package_path.read_bytes()


def test_actual_sigkill_parent_reaps_its_harness(tmp_path):
    """Run the production watchdog in a child, then SIGKILL its pipe-owning parent."""
    if os.name != "posix":
        return
    import marshal
    child = """
import marshal, os, sys
OWNER_TOKEN = 'owned'
OWNER_PIPE_FD = int(sys.argv[1])
owner_alive = lambda: True
exec(marshal.loads(bytes.fromhex(sys.argv[2])), globals())
monitor_owner()
"""
    parent = """
import os, subprocess, sys, time
fd, writer = os.pipe()
proc = subprocess.Popen([sys.executable, '-c', sys.argv[1], str(fd), sys.argv[2]],
                        pass_fds=(fd,), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
os.close(fd)
with open(sys.argv[3], 'w') as f: f.write(str(proc.pid))
time.sleep(30)
"""
    import marshal
    import pytest
    pid_file = tmp_path / "harness.pid"
    proc = subprocess.Popen(
        [sys.executable, "-c", parent, child,
         marshal.dumps(isolated_functions("monitor_owner")).hex(), str(pid_file)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    child_pid = None
    try:
        for _ in range(100):
            if pid_file.exists():
                child_pid = int(pid_file.read_text())
                break
            time.sleep(0.02)
        assert child_pid is not None
        os.kill(proc.pid, signal.SIGKILL)
        proc.wait(timeout=3)
        for _ in range(100):
            result = subprocess.run(["ps", "-o", "stat=", "-p", str(child_pid)],
                                    capture_output=True, text=True)
            if result.returncode or not result.stdout.strip() or "Z" in result.stdout:
                break
            time.sleep(0.03)
        else:
            pytest.fail("Harness remained alive after SIGKILL of owning parent")
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        if child_pid:
            state = subprocess.run(["ps", "-o", "stat=", "-p", str(child_pid)],
                                   capture_output=True, text=True)
            if state.returncode == 0 and state.stdout.strip() and "Z" not in state.stdout:
                os.kill(child_pid, signal.SIGKILL)


def test_normal_shutdown_sends_owned_only_request(monkeypatch):
    monkeypatch.setenv("BU_NAME", "browser-workspace")
    from contextlib import nullcontext
    node = ast.parse((ROOT / "session_daemon.py").read_text())
    funcs = [n for n in node.body if isinstance(n, ast.FunctionDef)
             and n.name == "stop_owned_harness"]
    assert len(funcs) == 1
    payloads = []

    class IPC:
        def connect(self, *_args, **_kwargs):
            return nullcontext(), None
        def request(self, _connection, _token, request):
            payloads.append(request)
            return {"ok": True}
        def ping(self, *_args, **_kwargs):
            return False

    ns = {"harness_ipc": IPC(), "os": os, "time": time,
          "HARNESS_OWNER_TOKEN": "known-token"}
    exec(compile(ast.Module(body=funcs, type_ignores=[]), "<test>", "exec"), ns)
    ns["stop_owned_harness"]()
    assert payloads == [{"meta": "owner_shutdown", "owner_token": "known-token"}]


def test_pending_explicit_cdp_harness_is_not_spawned_twice(monkeypatch, tmp_path):
    import pytest
    sys.path.insert(0, str(ROOT / "src"))
    from browser_harness import admin
    class Lock:
        fd = 1
        def __enter__(self): return self
        def __exit__(self, *_args): pass

    monkeypatch.setattr(admin, "_spawn_lock", lambda *a, **kw: Lock())
    monkeypatch.setattr(admin, "daemon_alive", lambda *a, **kw: False)
    monkeypatch.setattr(admin, "_starting_daemon_pid", lambda *a, **kw: os.getpid())
    monkeypatch.setattr(admin, "_parked_daemon_pid", lambda *a, **kw: None)
    monkeypatch.setattr(admin, "_pending_pid_record", lambda *a, **kw: os.getpid())
    monkeypatch.setattr(admin, "_log_tail", lambda *a, **kw: "")
    monkeypatch.setattr(admin.ipc, "log_path", lambda *a, **kw: tmp_path / "harness.log")
    monkeypatch.setattr(subprocess, "Popen",
                        lambda *a, **kw: pytest.fail("Duplicate harness spawned"))
    with pytest.raises(RuntimeError, match="didn't come up"):
        admin.ensure_daemon(wait=0.01, env={"BU_CDP_URL": "http://127.0.0.1:1"})
