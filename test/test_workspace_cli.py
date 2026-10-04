import importlib.machinery
import importlib.util
import json
import os
import socket
import subprocess
import sys
import threading
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "bin/browser-workspace"
ADMIN = ROOT / "node/admin.mjs"


def load_cli(monkeypatch, ensure_daemon_impl):
    session_client = types.ModuleType("session_client")
    session_client.SOCKET_PATH = Path("/tmp/browser-workspace-test.sock")
    session_client.ensure_daemon = ensure_daemon_impl
    platform_runner = types.ModuleType("platform_runner")
    platform_runner.run_platform_action = lambda *args, **kwargs: {"result": {"ok": True}}
    monkeypatch.setitem(sys.modules, "session_client", session_client)
    monkeypatch.setitem(sys.modules, "platform_runner", platform_runner)
    loader = importlib.machinery.SourceFileLoader("browser_workspace_cli_test", str(CLI))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_normal_help_exposes_status_session_platform_only():
    result = subprocess.run([sys.executable, str(CLI), "--help"], cwd=ROOT, text=True, capture_output=True)
    assert result.returncode == 0
    assert "{status,session,platform}" in result.stdout
    assert "\n  workspace" not in result.stdout.lower()


@pytest.mark.parametrize("argv", [["workspace", "create", "Relay"], ["workspace", "delete", "Relay"]])
def test_workspace_lifecycle_cli_is_rejected(argv):
    result = subprocess.run([sys.executable, str(CLI), *argv], cwd=ROOT, text=True, capture_output=True)
    assert result.returncode != 0
    assert "invalid choice: 'workspace'" in result.stderr


def test_status_reports_resolved_paths_and_daemon(monkeypatch, capsys):
    cli = load_cli(monkeypatch, lambda: {"ok": True, "pid": 123, "session_count": 2})
    monkeypatch.setattr(sys, "argv", ["browser-workspace", "status"])
    cli.main()
    result = json.loads(capsys.readouterr().out)
    assert Path(result["root"]).is_absolute()
    assert Path(result["admin_helper"]).is_absolute()
    assert Path(result["admin_helper"]).exists()
    assert result["admin_helper"] == str(ADMIN.resolve())
    assert result["daemon"] == {
        "running": True,
        "pid": 123,
        "session_count": 2,
        "socket": "/tmp/browser-workspace-test.sock",
    }


def _serve_once(socket_path, seen, reply):
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(socket_path))
    server.listen(1)
    try:
        conn, _ = server.accept()
        with conn:
            data = b""
            while b"\n" not in data:
                data += conn.recv(4096)
            seen.append(json.loads(data.split(b"\n", 1)[0]))
            conn.sendall((json.dumps(reply) + "\n").encode())
    finally:
        server.close()


def run_admin(tmp_path, expression, reply):
    sock = Path("/tmp") / f"bw-{os.getpid()}-{abs(hash(str(tmp_path))) % 100000}.sock"
    try:
        sock.unlink()
    except FileNotFoundError:
        pass
    seen = []
    thread = threading.Thread(target=_serve_once, args=(sock, seen, reply), daemon=True)
    thread.start()
    env = dict(os.environ)
    env["BROWSER_WORKSPACE_TEST_MODE"] = "1"
    env["BROWSER_WORKSPACE_SESSION_SOCKET"] = str(sock)
    script = f'import {{ ensureWorkspace, deleteWorkspace }} from {json.dumps(ADMIN.as_uri())};\n{expression}'
    result = subprocess.run(["node", "--input-type=module", "-e", script], cwd=ROOT, env=env, text=True, capture_output=True)
    thread.join(timeout=2)
    try:
        sock.unlink()
    except FileNotFoundError:
        pass
    return result, seen


def test_node_admin_helper_ensure_request(tmp_path):
    result, seen = run_admin(tmp_path, 'console.log(JSON.stringify(await ensureWorkspace("Relay", 6)));', {"name": "Relay", "poolSize": 6})
    assert result.returncode == 0, result.stderr
    assert seen == [{"op": "workspace-create", "name": "Relay", "pool_size": 6}]
    assert json.loads(result.stdout)["poolSize"] == 6


def test_node_admin_helper_delete_force_request(tmp_path):
    result, seen = run_admin(tmp_path, 'console.log(JSON.stringify(await deleteWorkspace("Tutor", {force:true})));', {"name": "Tutor", "deleted": True})
    assert result.returncode == 0, result.stderr
    assert seen == [{"op": "workspace-delete", "name": "Tutor", "force": True}]


def test_node_admin_helper_surfaces_daemon_error(tmp_path):
    result, seen = run_admin(tmp_path, 'await deleteWorkspace("Relay");', {"error": "RuntimeError: leased tabs"})
    assert seen == [{"op": "workspace-delete", "name": "Relay", "force": False}]
    assert result.returncode != 0
    assert "RuntimeError: leased tabs" in result.stderr
