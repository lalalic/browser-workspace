import ast
import os
import sys
import time
from contextlib import nullcontext
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SESSION = ROOT / 'session_daemon.py'


def session_functions(*names):
    node = ast.parse(SESSION.read_text())
    funcs = [n for n in node.body if isinstance(n, ast.FunctionDef) and n.name in names]
    assert len(funcs) == len(names)
    return compile(ast.Module(body=funcs, type_ignores=[]), str(SESSION), 'exec')


def test_session_passes_generation_identity_and_pipe_to_external_harness():
    src = SESSION.read_text()
    assert "'BH_OWNER_PID': str(HARNESS_OWNER_PID)" in src
    assert "'BH_OWNER_STARTED': str(HARNESS_OWNER_STARTED or '')" in src
    assert "'BH_OWNER_TOKEN': HARNESS_OWNER_TOKEN" in src
    assert "owner_env['BH_OWNER_PIPE_FD'] = str(read_fd)" in src
    assert 'ensure_daemon(env=owner_env)' in src


def test_normal_shutdown_is_token_scoped():
    payloads=[]
    class IPC:
        def connect(self,*_a,**_kw): return nullcontext(),None
        def request(self,_c,_t,request): payloads.append(request); return {'ok':True}
        def ping(self,*_a,**_kw): return False
    ns={'harness_ipc':IPC(),'os':os,'time':time,'HARNESS_OWNER_TOKEN':'known-token'}
    exec(session_functions('stop_owned_harness'),ns)
    ns['stop_owned_harness']()
    assert payloads == [{'meta':'owner_shutdown','owner_token':'known-token'}]


def test_cleanup_closes_owner_pipe_after_graceful_stop():
    src=SESSION.read_text()
    cleanup=src[src.index('def cleanup():'):src.index('atexit.register(cleanup)')]
    assert cleanup.index('stop_owned_harness()') < cleanup.index('os.close(HARNESS_OWNER_PIPE)')


def test_repository_does_not_vendor_browser_harness():
    assert not (ROOT/'src/browser_harness').exists()
    assert not (ROOT/'src/browser_workspace_app/src/browser_harness').exists()
