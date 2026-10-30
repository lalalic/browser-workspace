#!/usr/bin/env python3
from __future__ import annotations
import fcntl, json, os, re, shutil, socket, subprocess, sys, time
from pathlib import Path

ROOT=Path(__file__).resolve().parent
RUNTIME_DIR=Path.home()/'.config/browser-workspace/runtime'
SOCKET_PATH = RUNTIME_DIR / 'session.sock'
HARNESS_RUNTIME_SPEC='browser-harness @ git+https://github.com/lalalic/browser-harness.git@80b74e116b9126f5159c84e5e05a750573e5f192'

def package_version():
    match=re.search(r'__version__\s*=\s*"([^"]+)"',(ROOT/'__init__.py').read_text())
    return match.group(1) if match else 'dev'

def runtime_requirements():
    pyproject=ROOT.parent/'pyproject.toml'
    if pyproject.is_file():
        import tomllib
        return tomllib.loads(pyproject.read_text())['project']['dependencies']
    from importlib.metadata import requires
    return [r for r in requires('browser-workspace') or [] if 'extra ==' not in r]

def _same_runtime_files(source: Path, cached: Path) -> bool:
    """A version alone cannot identify an edited local checkout."""
    def relevant(root):
        return {
            p.relative_to(root): p
            for p in root.rglob('*')
            if p.is_file() and p.name != '.ready'
            and '__pycache__' not in p.parts
            and not p.name.endswith('.pyc')
            and not p.name.startswith('.env')
            and p.name != '.DS_Store'
        }
    a, b = relevant(source), relevant(cached)
    return a.keys() == b.keys() and all(a[key].read_bytes() == b[key].read_bytes() for key in a)


def runtime_source():
    """Cache a stable source copy; refresh an idle checkout changed without a version bump."""
    configured = os.environ.get('BROWSER_WORKSPACE_RUNTIME_SOURCE')
    if configured: return Path(configured)
    packages = RUNTIME_DIR / 'packages'
    if packages in ROOT.parents: return ROOT
    packages.mkdir(parents=True, exist_ok=True)
    target = packages / package_version()
    with open(RUNTIME_DIR / 'runtime-source.lock', 'a+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if (target / '.ready').exists() and _same_runtime_files(ROOT, target):
            return target
        if owner_is_running():
            # Never modify source files while another daemon may be importing them.
            raise RuntimeError('browser-workspace daemon owns the runtime; source update deferred until idle')
        import tempfile
        temp = Path(tempfile.mkdtemp(prefix=f'{package_version()}.tmp-', dir=packages))
        backup = target.with_name(f'{target.name}.previous-{os.getpid()}')
        try:
            shutil.copytree(ROOT, temp, dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.DS_Store', '.env', '.env.*'))
            (temp / '.ready').write_text(package_version())
            if target.exists():
                target.rename(backup)
            try:
                temp.rename(target)
            except BaseException:
                if backup.exists():
                    backup.rename(target)
                raise
            if backup.exists():
                shutil.rmtree(backup)
            return target
        finally:
            if temp.exists():
                shutil.rmtree(temp)

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
        requirements=runtime_requirements()
        uv=shutil.which('uv')
        if uv:
            subprocess.run([uv,'venv','--python','3.11',str(PYTHON.parent.parent)],check=True)
            subprocess.run([uv,'pip','install','--python',str(PYTHON),*requirements],check=True)
            subprocess.run([uv,'pip','install','--python',str(PYTHON),'--reinstall',HARNESS_RUNTIME_SPEC],check=True)
            return PYTHON
        if sys.version_info < (3,11):
            raise RuntimeError(
                'Browser Workspace needs Python 3.11+ for first-use bootstrap. '
                'Install uv or Python 3.11+, then retry.'
            )
        subprocess.run([sys.executable,'-m','venv',str(PYTHON.parent.parent)],check=True)
        subprocess.run([str(PYTHON),'-m','pip','install',*requirements],check=True)
        subprocess.run([str(PYTHON),'-m','pip','install','--force-reinstall',HARNESS_RUNTIME_SPEC],check=True)
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

def owner_is_running():
    """An exclusive owner lock means a live daemon already exists."""
    owner_path=RUNTIME_DIR/'session.lock'
    with open(owner_path,'a+b') as owner:
        try:
            fcntl.flock(owner,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        finally:
            try: fcntl.flock(owner,fcntl.LOCK_UN)
            except OSError: pass
    return False

def ensure_daemon():
    p=ping()
    if p and p.get('ok'):
        if p.get('version') == package_version(): return p
        # Never interrupt an active session. Older daemons without a retire
        # protocol remain usable until their owner explicitly stops them.
        if p.get('session_count', 1) != 0 or not p.get('version'):
            return p
        try:
            retired=request({'op':'retire-if-idle'},ensure=False)
        except (OSError, RuntimeError):
            return p
        if not retired.get('retiring'): return p
        deadline=time.monotonic()+8
        while time.monotonic()<deadline:
            if not owner_is_running(): break
            time.sleep(.1)
        else:
            raise RuntimeError('old browser-workspace daemon did not retire safely')
        p=ping()
        if p and p.get('ok'): return p
    RUNTIME_DIR.mkdir(parents=True,exist_ok=True)
    if owner_is_running():
        raise RuntimeError('browser-workspace daemon is alive but its socket is unreachable; refusing duplicate startup')
    runtime_python=ensure_runtime_python()
    from platform_runner import PLATFORMS
    SOURCE=runtime_source()
    env={**os.environ,'WEBHELM_PLATFORM_DIR':str(PLATFORMS)}
    log=open(RUNTIME_DIR/'session-daemon.log','ab',buffering=0)
    subprocess.Popen([str(runtime_python),str(SOURCE/'session_daemon.py')],env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True,close_fds=True)
    deadline=time.time()+15
    while time.time()<deadline:
        time.sleep(.1); p=ping()
        if p and p.get('ok'): return p
    raise RuntimeError(f'browser-workspace session daemon did not start; see {RUNTIME_DIR / "session-daemon.log"}')
