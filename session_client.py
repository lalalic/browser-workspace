#!/usr/bin/env python3
from __future__ import annotations
import fcntl, json, os, shutil, socket, subprocess, sys, time
from pathlib import Path

ROOT=Path(__file__).resolve().parent
RUNTIME_DIR=Path.home()/'.config/browser-workspace/runtime'
SOCKET_PATH=(Path(os.environ['BROWSER_WORKSPACE_SESSION_SOCKET']) if os.environ.get('BROWSER_WORKSPACE_TEST_MODE')=='1' and os.environ.get('BROWSER_WORKSPACE_SESSION_SOCKET') else RUNTIME_DIR/'session.sock')

def package_version():
    try:
        return json.loads((ROOT/'package.json').read_text()).get('version','dev')
    except Exception:
        return 'dev'

def runtime_source():
    configured=os.environ.get('BROWSER_WORKSPACE_RUNTIME_SOURCE')
    if configured: return Path(configured)
    if not (ROOT/'package.json').exists(): return ROOT
    target=RUNTIME_DIR/'packages'/package_version()
    marker=target/'.ready'
    if marker.exists(): return target
    target.parent.mkdir(parents=True,exist_ok=True)
    tmp=target.with_name(target.name+'.tmp')
    shutil.rmtree(tmp,ignore_errors=True)
    tmp.mkdir(parents=True)
    for name in ['pyproject.toml','session_daemon.py','session_client.py','platform_runner.py','managed_chrome.py','src','agent-workspace','interaction-skills','platforms','extension','licenses']:
        source=ROOT/name
        if not source.exists(): continue
        destination=tmp/name
        if source.is_dir(): shutil.copytree(source,destination)
        else: shutil.copy2(source,destination)
    (tmp/'.ready').write_text(package_version())
    shutil.rmtree(target,ignore_errors=True)
    tmp.rename(target)
    return target

SOURCE=runtime_source()
PYTHON=Path(os.environ.get('BROWSER_WORKSPACE_SESSION_PYTHON',RUNTIME_DIR/'venv'/package_version()/'bin/python'))



def ensure_runtime_python():
    if PYTHON.exists():
        return PYTHON
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    lock_path=RUNTIME_DIR/'runtime-bootstrap.lock'
    with open(lock_path,'a+b') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if PYTHON.exists():
            return PYTHON
        uv=shutil.which('uv')
        if uv:
            subprocess.run([uv,'venv','--python','3.11',str(PYTHON.parent.parent)],check=True)
            subprocess.run([uv,'pip','install','--python',str(PYTHON),'-e',str(SOURCE)],check=True)
            return PYTHON
        if sys.version_info < (3,11):
            raise RuntimeError(
                'Browser Workspace needs Python 3.11+ for first-use bootstrap. '
                'Install uv or Python 3.11+, then retry.'
            )
        subprocess.run([sys.executable,'-m','venv',str(PYTHON.parent.parent)],check=True)
        subprocess.run([str(PYTHON),'-m','pip','install','-e',str(SOURCE)],check=True)
        return PYTHON

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
        runtime_python=ensure_runtime_python()
        log=open(RUNTIME_DIR/'session-daemon.log','ab',buffering=0)
        subprocess.Popen([str(runtime_python),str(SOURCE/'session_daemon.py')],stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True,close_fds=True)
        deadline=time.time()+15
        while time.time()<deadline:
            time.sleep(.1); p=ping()
            if p and p.get('ok'): return p
    raise RuntimeError(f'browser-workspace session daemon did not start; see {RUNTIME_DIR / "session-daemon.log"}')
