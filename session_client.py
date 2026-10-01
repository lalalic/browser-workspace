#!/usr/bin/env python3
from __future__ import annotations
import fcntl, json, os, socket, subprocess, time
from pathlib import Path

ROOT=Path(__file__).resolve().parent
RUNTIME_DIR=Path(os.environ.get('BROWSER_WORKSPACE_RUNTIME_DIR',Path.home()/'.config/browser-workspace/runtime'))
SOCKET_PATH=Path(os.environ.get('BROWSER_WORKSPACE_SESSION_SOCKET',RUNTIME_DIR/'session.sock'))
PYTHON=Path(os.environ.get('BROWSER_WORKSPACE_SESSION_PYTHON',ROOT/'.venv/bin/python'))

def request(payload, ensure=True):
    if ensure: ensure_daemon()
    s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
    try: s.connect(str(SOCKET_PATH))
    except Exception:
        s.close(); raise
    with s:
        f=s.makefile('rwb'); f.write((json.dumps(payload,ensure_ascii=False)+'\n').encode()); f.flush(); line=f.readline()
    if not line: raise RuntimeError('browser-workspace session daemon closed without a response')
    return json.loads(line)

def ping():
    try: return request({'op':'ping'},ensure=False)
    except Exception: return None

def ensure_daemon():
    p=ping()
    if p and p.get('ok'): return p
    RUNTIME_DIR.mkdir(parents=True,exist_ok=True)
    lock_path=RUNTIME_DIR/'session-daemon.lock'
    with open(lock_path,'a+b') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        p=ping()
        if p and p.get('ok'): return p
        log=open(RUNTIME_DIR/'session-daemon.log','ab',buffering=0)
        subprocess.Popen([str(PYTHON),str(ROOT/'session_daemon.py')],stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True,close_fds=True)
        deadline=time.time()+15
        while time.time()<deadline:
            time.sleep(.1); p=ping()
            if p and p.get('ok'): return p
    raise RuntimeError(f'browser-workspace session daemon did not start; see {RUNTIME_DIR / "session-daemon.log"}')
