#!/usr/bin/env python3
import ast, atexit, contextvars, io, json, os, secrets, signal, socket, sys, threading, time, traceback
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.environ.setdefault('BH_HOME', str(Path.home()/'.config/browser-workspace/browser-core'))
# Preserve the canonical single Browser Harness daemon socket during migration.
# This is runtime-state compatibility only; Browser Workspace owns the code/venv.
os.environ.setdefault('BH_RUNTIME_DIR', str(Path.home()/'.config/browser-workspace/browser-core-runtime'))
os.environ.setdefault('BU_NAME', 'browser-workspace')
os.environ.setdefault('BH_AGENT_WORKSPACE', str(ROOT/'browser-harness'))
os.environ['BH_WORKSPACE_NAME'] = 'Harness'

from managed_chrome import ensure_managed_chrome
MANAGED_CHROME = ensure_managed_chrome()
from browser_harness.admin import ensure_daemon, _process_start_time
from browser_harness import _ipc as harness_ipc
from browser_harness import helpers as bh

HARNESS_OWNER_TOKEN = secrets.token_hex(24)
HARNESS_OWNER_PID = os.getpid()
HARNESS_OWNER_STARTED = _process_start_time(HARNESS_OWNER_PID)
HARNESS_OWNER_PIPE = None


def stop_owned_harness():
    """Only a harness matching this daemon generation may stop."""
    try:
        conn, token = harness_ipc.connect(os.environ.get('BU_NAME', 'browser-workspace'), timeout=1)
        with conn:
            response = harness_ipc.request(conn, token, {'meta': 'owner_shutdown', 'owner_token': HARNESS_OWNER_TOKEN})
        if isinstance(response, dict) and response.get('ok'):
            # Allow the harness its graceful CDP/IPC cleanup before EOF of
            # our owner pipe forces the crash-only exit path.
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline and harness_ipc.ping(os.environ.get('BU_NAME', 'browser-workspace'), timeout=0.1):
                time.sleep(0.05)
    except (OSError, ValueError, TimeoutError):
        pass

DEFAULT_WORKSPACE = os.environ.get('BH_WORKSPACE_NAME','Harness')
RUNTIME_DIR = Path.home()/'.config/browser-workspace/runtime'
SOCKET_PATH = RUNTIME_DIR / 'session.sock'
OWNER_LOCK_PATH = RUNTIME_DIR/'session.lock'
SESSIONS = {}
SESSIONS_LOCK = threading.Lock()
RETIRING = False
DAEMON_VERSION = 'dev'
try:
    DAEMON_VERSION = (ROOT/'.ready').read_text().strip()
except OSError:
    from session_client import package_version
    DAEMON_VERSION = package_version()
BROWSER_LOCK = threading.RLock()
# A request's default CDP target is local to its executing Session, NOT the
# Browser Harness daemon's mutable default attachment. No changes to action APIs.
_EXECUTION_SESSION = contextvars.ContextVar('webhelm_execution_session', default=None)
_OUTPUT_STREAM = contextvars.ContextVar('webhelm_stdout', default=None)
_ERROR_STREAM = contextvars.ContextVar('webhelm_stderr', default=None)
_EVENT_DRAIN_LOCK = threading.Lock()
_RAW_CDP = bh.cdp
_RAW_SEND = bh._send


class _SessionOutput:
    """Preserve process stdout/stderr while routing each worker's print output."""
    def __init__(self, original, context):
        self.original, self.context = original, context
    def write(self, data):
        return (self.context.get() or self.original).write(data)
    def flush(self):
        return (self.context.get() or self.original).flush()
    def __getattr__(self, name):
        return getattr(self.original, name)


def install_session_output():
    if not isinstance(sys.stdout, _SessionOutput):
        sys.stdout = _SessionOutput(sys.stdout, _OUTPUT_STREAM)
    if not isinstance(sys.stderr, _SessionOutput):
        sys.stderr = _SessionOutput(sys.stderr, _ERROR_STREAM)


def _session_cdp(method, session_id=None, _response_timeout=5.0, **params):
    session = _EXECUTION_SESSION.get()
    if session is not None and method == 'Target.createTarget' and not session.allow_new_target:
        raise RuntimeError('Target.createTarget is disabled in Browser Workspace sessions; use new_tab(url)')
    if session is not None and method == 'Target.closeTarget' and params.get('targetId') not in session.owned_target_ids:
        raise RuntimeError('cannot close a tab outside the active WebHelm Session')
    if session is not None and session_id is None and not method.startswith(
        ('Target.', 'Browser.', 'ServiceWorker.', 'SystemInfo.', 'Schema.')
    ):
        session_id = session.cdp_session_id
        if not session_id and not session.allow_new_target:
            raise RuntimeError('session has no attached CDP target')
    result = _RAW_CDP(method, session_id=session_id, _response_timeout=_response_timeout, **params)
    if session is not None and method == 'Target.createTarget':
        target_id = result.get('targetId')
        if target_id:
            session.owned_target_ids.add(target_id)
    return result


def _pump_session_events(response_timeout):
    """Called with _EVENT_DRAIN_LOCK held; never discard another session's events."""
    fresh = _RAW_SEND({'meta': 'drain_events'}, response_timeout=response_timeout).get('events', [])
    if fresh:
        with SESSIONS_LOCK:
            live = list(SESSIONS.values())
        by_cdp = {attachment: entry for entry in live for attachment in entry.attached_cdp_ids}
        for event in fresh:
            owner = by_cdp.get(event.get('session_id'))
            if owner:
                owner.events.append(event)
                if event.get('method') == 'Page.javascriptDialogOpening':
                    params = event.get('params') or {}
                    owner.dialog = {'type': params.get('type'), 'message': params.get('message', '')}
                elif event.get('method') == 'Page.javascriptDialogClosed':
                    owner.dialog = None


def _session_send(req, response_timeout=5.0):
    session = _EXECUTION_SESSION.get()
    if session is None:
        return _RAW_SEND(req, response_timeout=response_timeout)
    meta = req.get('meta')
    if meta == 'session':
        return {'session_id': session.cdp_session_id}
    if meta in ('current_tab', 'connection_status'):
        info = _RAW_CDP('Target.getTargetInfo', targetId=session.target_id).get('targetInfo', {})
        result = {'targetId': session.target_id, 'url': info.get('url', ''), 'title': info.get('title', '')}
        if meta == 'connection_status':
            return {'target_id': session.target_id, 'session_id': session.cdp_session_id, 'page': result}
        return result
    if meta == 'set_session':
        target = req.get('target_id')
        if target not in session.owned_target_ids and not session.allow_new_target:
            raise RuntimeError('cannot attach to a tab outside the active WebHelm Session')
        session.owned_target_ids.add(target)
        session.target_id = target
        session.cdp_session_id = req.get('session_id')
        if not session.cdp_session_id:
            raise RuntimeError('new browser target has no CDP session')
        session.attached_cdp_ids.add(session.cdp_session_id)
        session.namespace['target_id'] = target
        # Upstream set_session also enables these domains, but mutates a
        # process-global attached target and disables the prior tab's Network.
        # An isolated Session must enable its own domains instead.
        for domain in ('Page', 'DOM', 'Runtime', 'Network'):
            _RAW_CDP(domain + '.enable', session_id=session.cdp_session_id)
        return {'session_id': session.cdp_session_id}
    if meta == 'drain_events':
        # The underlying daemon has a global destructive event buffer, so
        # drain exactly once and route events to their owning Session.
        with _EVENT_DRAIN_LOCK:
            _pump_session_events(response_timeout)
            result = list(session.events)
            session.events.clear()
        return {'events': result}
    if meta == 'pending_dialog':
        # Query the correct tab's dialog without consuming its queued events.
        with _EVENT_DRAIN_LOCK:
            _pump_session_events(response_timeout)
            return {'dialog': session.dialog}
    if meta is not None:
        raise RuntimeError(f'unsupported shared Browser Harness meta during isolated execution: {meta}')
    return _RAW_SEND(req, response_timeout=response_timeout)


# These replacements are at the shared CDP boundary, not per helper method.
# Upstream helpers and the Workspace overlay resolve these module globals.
bh.cdp = _session_cdp
bh._send = _session_send
CHATGPT_QUEUE = None

SESSION_RECONCILE_SECONDS = 30
# Zero disables idle lease eviction. Never evict an executing Session.
SESSION_IDLE_TTL_SECONDS = max(0, int(os.environ.get('BROWSER_WORKSPACE_SESSION_IDLE_TTL_SECONDS', '7200')))


def is_reclaimed(info):
    url = info.get('url', '')
    if not url.startswith('chrome-extension://'):
        return False
    try:
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(url)
        return parsed.path == '/workspace.html' and parse_qs(parsed.query).get('role') == ['idle']
    except ValueError:
        return False


def reconcile_sessions():
    """Drop records for completely released leases, never release those tabs again."""
    with BROWSER_LOCK:
        try:
            targets = bh.cdp('Target.getTargets')['targetInfos']
        except Exception:
            return []
        pages = {i['targetId']: i for i in targets if i.get('type') == 'page'}
        removed = []
        with SESSIONS_LOCK:
            for sid, session in list(SESSIONS.items()):
                if session.lock.locked():
                    continue
                # A leased root may have opened child tabs: keep any live child.
                if all(tid not in pages or is_reclaimed(pages[tid])
                       for tid in session.owned_target_ids):
                    del SESSIONS[sid]
                    removed.append(sid)
        return removed


def reconciliation_loop():
    while True:
        time.sleep(SESSION_RECONCILE_SECONDS)
        reconcile_sessions()
        collect_idle_sessions()


def collect_idle_sessions(now=None):
    """Close owned tabs for stale leases, never in-flight executions."""
    if not SESSION_IDLE_TTL_SECONDS:
        return []
    current = time.time() if now is None else now
    with SESSIONS_LOCK:
        candidates = [sid for sid, s in SESSIONS.items()
                      if current - s.last_used_at >= SESSION_IDLE_TTL_SECONDS
                      and not s.lock.locked()]
    collected = []
    for sid in candidates:
        with SESSIONS_LOCK:
            session = SESSIONS.get(sid)
        if session is None or session.lock.locked() or current - session.last_used_at < SESSION_IDLE_TTL_SECONDS:
            continue
        try:
            result = stop_session(sid, idle_before=current - SESSION_IDLE_TTL_SECONDS)
            if result is not None:
                collected.append(result)
        except Exception:
            continue
    return collected


def compilable_module_body(body):
    """Return a module body that remains valid after trailing-result extraction.

    Submitted sessions commonly contain ordinary imports before a future import.
    Python accepts that source form, but recompiling an AST after removing the
    trailing result expression requires future imports to be moved first.
    """
    leading = []
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
        leading.append(body.pop(0))
    future = [node for node in body if isinstance(node, ast.ImportFrom) and node.module == '__future__']
    if not future:
        return leading + body
    rest = [node for node in body if node not in future]
    return leading + future + rest


class SessionBrowserProxy:
    def __init__(self, session): self._session=session
    def __getattr__(self, name): return getattr(bh, name)
    def new_tab(self, url='about:blank'): return self._session._new_tab(url)
    def close_tab(self, target=None): return self._session._close_tab(target)
    def cdp(self, method, **kwargs): return self._session._cdp(method, **kwargs)

class Session:
    def __init__(self, sid, workspace, target_id, workspace_supported):
        self.session_id=sid; self.workspace=workspace; self.target_id=target_id; self.workspace_supported=bool(workspace_supported)
        self.created_at=time.time(); self.last_used_at=self.created_at
        self.owned_target_ids={target_id}
        self.cdp_session_id=None
        self.attached_cdp_ids=set()
        self.allow_new_target=False
        self.events=deque(maxlen=500)
        self.dialog=None
        self.lock=threading.Lock()
        self.browser=SessionBrowserProxy(self)
        self.namespace={'__name__':'__browser_workspace_session__','bh':self.browser,'target_id':target_id}
        for name in dir(bh):
            if not name.startswith('_'): self.namespace[name]=getattr(bh,name)
        self.namespace['new_tab']=self._new_tab
        self.namespace['close_tab']=self._close_tab
        self.namespace['cdp']=self._cdp

    def _remember_target(self, tid):
        if tid:
            self.owned_target_ids.add(tid)
            self.target_id=tid
            self.namespace['target_id']=tid
        return tid

    def _new_tab(self, url='about:blank'):
        with BROWSER_LOCK:
            self.allow_new_target=True
            try:
                return self._remember_target(bh.new_tab(url))
            finally:
                self.allow_new_target=False

    def _close_tab(self, target=None):
        wanted=target
        if isinstance(wanted, dict): wanted=wanted.get('targetId') or wanted.get('target_id')
        if wanted is None: wanted=bh.current_tab().get('targetId')
        result=bh.close_tab(target)
        if wanted: self.owned_target_ids.discard(wanted)
        return result

    def _cdp(self, method, **kwargs):
        if method == 'Target.createTarget':
            raise RuntimeError(
                'Target.createTarget is disabled in Browser Workspace sessions; '
                'use new_tab(url) so the tab is owned by the active session/workspace'
            )
        result=bh.cdp(method, **kwargs)
        if method == 'Target.closeTarget':
            self.owned_target_ids.discard(kwargs.get('targetId'))
        return result

def with_workspace(name, supported=None):
    class Scope:
        def __enter__(self):
            self.name_token=bh.workspace_set_name(name)
            self.support_token=bh.workspace_set_supported(supported) if supported is not None else None
            return self
        def __exit__(self,*_):
            if self.support_token is not None: bh.workspace_reset_supported(self.support_token)
            bh.workspace_reset_name(self.name_token)
    return Scope()

def execute(source, namespace):
    out,err=io.StringIO(),io.StringIO(); value=None
    try:
        tree=ast.parse(source,mode='exec'); body=list(tree.body)
        tail=body.pop() if body and isinstance(body[-1],ast.Expr) else None
        body=compilable_module_body(body)
        out_token = _OUTPUT_STREAM.set(out)
        err_token = _ERROR_STREAM.set(err)
        try:
            if body: exec(compile(ast.Module(body=body,type_ignores=[]),'<browser-workspace-session>','exec'),namespace,namespace)
            if tail is not None:
                value=eval(compile(ast.Expression(tail.value),'<browser-workspace-session>','eval'),namespace,namespace); namespace['_']=value
        finally:
            _ERROR_STREAM.reset(err_token)
            _OUTPUT_STREAM.reset(out_token)
        result={'ok':True,'stdout':out.getvalue(),'stderr':err.getvalue()}
        if value is not None:
            try: json.dumps(value); result['value']=value
            except (TypeError,ValueError): result['value_repr']=repr(value)
        return result
    except BaseException as exc:
        traceback.print_exc(file=err)
        return {'ok':False,'stdout':out.getvalue(),'stderr':err.getvalue(),'error':f'{type(exc).__name__}: {exc}'}

def start_session(workspace=None, url=None):
    workspace=(workspace or DEFAULT_WORKSPACE).strip()
    if not workspace: raise ValueError('workspace must not be empty')
    sid=secrets.token_hex(8)
    start_url=(url or 'about:blank').strip()
    extension=bh.workspace_extension_status()
    supported=bool(extension.get('supported'))
    with BROWSER_LOCK:
        if RETIRING:
            raise RuntimeError('daemon_retiring')
        s=Session(sid,workspace,None,supported)
        s.allow_new_target=True
        context=_EXECUTION_SESSION.set(s)
        try:
            with with_workspace(workspace, supported):
                tid = bh.new_tab(start_url)
            if not s.cdp_session_id or tid != s.target_id:
                raise RuntimeError('new browser tab has no matching CDP attachment')
            s.owned_target_ids.discard(None)
        except BaseException:
            for owned in list(s.owned_target_ids):
                if owned:
                    try:
                        with with_workspace(workspace, supported):
                            bh.close_tab(owned)
                    except Exception:
                        try: _RAW_CDP('Target.closeTarget', targetId=owned)
                        except Exception: pass
            for attachment in s.attached_cdp_ids:
                try: _RAW_CDP('Target.detachFromTarget', sessionId=attachment)
                except Exception: pass
            raise
        finally:
            _EXECUTION_SESSION.reset(context)
            s.allow_new_target=False
        with SESSIONS_LOCK: SESSIONS[sid]=s
    result={'session_id':sid,'workspace':workspace,'target_id':tid,'url':start_url,'workspace_supported':supported}
    if not supported:
        result['warning']='Browser Workspace extension is not installed; workspace grouping/leases are unavailable. Browser automation will continue without workspace isolation.'
        result['extension_url']=extension.get('extensionUrl')
    return result


def absorb_owned_children(session):
    """Adopt popup/child page targets whose opener ancestry belongs to this session."""
    try:
        infos=bh.cdp('Target.getTargets').get('targetInfos', [])
    except Exception:
        return
    pages={i.get('targetId'): i for i in infos if i.get('type') == 'page' and i.get('targetId')}
    changed=True
    while changed:
        changed=False
        for tid, info in pages.items():
            if tid in session.owned_target_ids:
                continue
            opener=info.get('openerId')
            if opener and opener in session.owned_target_ids:
                session.owned_target_ids.add(tid)
                changed=True

def close_owned_tabs(session):
    """Close/release every live tab owned by the session, children before parents."""
    absorb_owned_children(session)
    errors=[]
    # Close descendants/current tabs first. Repeatedly inspect live targets so already
    # closed tabs disappear harmlessly and opener relationships remain usable.
    while session.owned_target_ids:
        try:
            infos=bh.cdp('Target.getTargets').get('targetInfos', [])
        except Exception:
            infos=[]
        live={i.get('targetId'): i for i in infos if i.get('type') == 'page' and i.get('targetId')}
        owned_live=[tid for tid in session.owned_target_ids if tid in live]
        if not owned_live:
            session.owned_target_ids.clear()
            break
        parent_ids={live[tid].get('openerId') for tid in owned_live}
        leaves=[tid for tid in owned_live if tid not in parent_ids]
        targets=leaves or owned_live
        for tid in targets:
            try:
                if session.workspace_supported:
                    try:
                        # Workspace-owned session tabs are leases. Release them back
                        # to the persistent pool instead of destroying the Chrome tab
                        # group when the final leased tab is stopped. Popup/child
                        # targets that are outside the workspace are still closed.
                        bh.close_tab(tid)
                    except RuntimeError as exc:
                        if 'outside workspace' not in str(exc):
                            raise
                        bh.cdp('Target.closeTarget', targetId=tid)
                else:
                    bh.cdp('Target.closeTarget', targetId=tid)
            except Exception as exc:
                errors.append(f'{tid}: {type(exc).__name__}: {exc}')
            finally:
                session.owned_target_ids.discard(tid)
    return errors

def get_session(sid):
    with SESSIONS_LOCK: s=SESSIONS.get(sid)
    if not s: raise KeyError(f'unknown session_id: {sid}')
    return s

def exec_session(sid, code):
    s=get_session(sid)
    s.last_used_at=time.time()
    with s.lock, with_workspace(s.workspace, s.workspace_supported):
        context = _EXECUTION_SESSION.set(s)
        try:
            r=execute(code,s.namespace)
            absorb_owned_children(s)
        finally:
            _EXECUTION_SESSION.reset(context)
    return {'session_id':sid,'workspace':s.workspace,'target_id':s.target_id,**r}

def list_sessions():
    with SESSIONS_LOCK:
        sessions=list(SESSIONS.values())
    return {
        'session_count': len(sessions),
        'sessions': [
            {
                'session_id': s.session_id,
                'workspace': s.workspace,
                'target_id': s.target_id,
                'created_at': s.created_at,
                'last_used_at': s.last_used_at,
            }
            for s in sessions
        ],
    }

def stop_all_sessions():
    with SESSIONS_LOCK:
        ids=list(SESSIONS)
    stopped=[]
    errors=[]
    for sid in ids:
        try:
            stopped.append(stop_session(sid))
        except Exception as exc:
            errors.append({'session_id':sid,'error':f'{type(exc).__name__}: {exc}'})
    return {'stopped_count':len(stopped),'error_count':len(errors),'stopped':stopped,'errors':errors}

def stop_session(sid, idle_before=None):
    with SESSIONS_LOCK:
        s=SESSIONS.get(sid)
    if not s: raise KeyError(f'unknown session_id: {sid}')
    # A stale GC candidate may have become active after the initial scan.
    if idle_before is not None and not s.lock.acquire(blocking=False):
        return None
    elif idle_before is None:
        s.lock.acquire()
    try:
        with SESSIONS_LOCK:
            if SESSIONS.get(sid) is not s:
                raise KeyError(f'unknown session_id: {sid}')
            if idle_before is not None and s.last_used_at > idle_before:
                return None
            SESSIONS.pop(sid)
        release_error=None
        with BROWSER_LOCK, with_workspace(s.workspace, s.workspace_supported):
            absorb_owned_children(s)
            closed_count=len(s.owned_target_ids)
            errors=close_owned_tabs(s)
            for attachment in s.attached_cdp_ids:
                try: _RAW_CDP('Target.detachFromTarget', sessionId=attachment)
                except Exception: pass  # Chrome may detach automatically on tab close
            if errors: release_error='; '.join(errors)
        return {'session_id':sid,'workspace':s.workspace,'target_id':s.target_id,'closed_tabs':closed_count,'release_error':release_error}
    finally:
        s.lock.release()

SOCKET_IDENTITY = None

def remove_owned_socket():
    """Never unlink a socket replaced by another owner."""
    if SOCKET_IDENTITY is None:
        return
    try:
        st = SOCKET_PATH.lstat()
        if (st.st_dev, st.st_ino) == SOCKET_IDENTITY:
            SOCKET_PATH.unlink()
    except FileNotFoundError:
        pass

def cleanup():
    if CHATGPT_QUEUE is not None:
        CHATGPT_QUEUE.close()
    with SESSIONS_LOCK: ids=list(SESSIONS)
    for sid in ids:
        try: stop_session(sid)
        except Exception: pass
    stop_owned_harness()
    # The write end is close-on-exec; its final close also detects SIGKILL
    # and parent re-exec without relying on a recycled numeric PID.
    if HARNESS_OWNER_PIPE is not None:
        try: os.close(HARNESS_OWNER_PIPE)
        except OSError: pass
    try: remove_owned_socket()
    except Exception: pass
atexit.register(cleanup)

def create_workspace(name, pool_size=5):
    if not isinstance(name, str) or not name.strip():
        raise ValueError('workspace name must be a non-empty string')
    size=int(pool_size)
    if size < 1:
        raise ValueError('workspace pool size must be at least 1')
    with BROWSER_LOCK:
        result=bh.workspace_create(name.strip(), size)
    return {
        'name': result.get('name', name.strip()),
        'poolSize': result.get('poolSize', size),
        'maxCapacity': result.get('maxCapacity', result.get('poolSize', size)),
        'initialized': result.get('initialized', True),
        'workspace_supported': True,
    }

def delete_workspace(name, force=False):
    if not isinstance(name, str) or not name.strip():
        raise ValueError('workspace name must be a non-empty string')
    with BROWSER_LOCK:
        return bh.workspace_delete(name.strip(), bool(force))

def handle(req):
    op=req.get('op')
    if op=='chatgpt-new-turn-enqueue':
        if CHATGPT_QUEUE is None: raise RuntimeError('chatgpt_queue_unavailable')
        return CHATGPT_QUEUE.enqueue(req)
    if op=='chatgpt-new-turn-list':
        return CHATGPT_QUEUE.list_pending()
    if op=='chatgpt-new-turn-reconcile':
        return CHATGPT_QUEUE.reconcile(req)
    if op=='ping': return {'ok':True,'pid':os.getpid(),'version':DAEMON_VERSION,'session_count':len(SESSIONS),'managed_chrome':MANAGED_CHROME}
    if op=='retire-if-idle':
        global RETIRING
        with BROWSER_LOCK, SESSIONS_LOCK:
            if SESSIONS or RETIRING:
                return {'ok':False,'reason':'active_sessions','session_count':len(SESSIONS)}
            RETIRING = True
        threading.Thread(target=lambda: (time.sleep(.2), os.kill(os.getpid(), signal.SIGTERM)), daemon=True).start()
        return {'ok':True,'retiring':True}
    if op=='list': return list_sessions()
    if op=='start':
        if RETIRING: return {'ok':False,'error':'daemon_retiring'}
        return start_session(req.get('workspace'), req.get('url'))
    if op=='exec': return exec_session(req['session_id'],req.get('code',''))
    if op=='stop': return stop_session(req['session_id'])
    if op=='stop-all': return stop_all_sessions()
    if op=='workspace-create': return create_workspace(req['name'], req.get('pool_size', 5))
    if op=='workspace-delete': return delete_workspace(req['name'], req.get('force', False))
    raise ValueError(f'unknown op: {op}')

def serve_conn(conn):
    with conn:
        f=conn.makefile('rwb')
        line=f.readline()
        if not line: return
        try: result=handle(json.loads(line))
        except Exception as exc: result={'error':f'{type(exc).__name__}: {exc}'}
        f.write((json.dumps(result,ensure_ascii=False)+'\n').encode()); f.flush()

def main():
    global SOCKET_IDENTITY, CHATGPT_QUEUE
    RUNTIME_DIR.mkdir(parents=True,exist_ok=True)
    try: os.chmod(RUNTIME_DIR,0o700)
    except Exception: pass
    import fcntl
    owner=open(OWNER_LOCK_PATH,'a+b')
    try:
        fcntl.flock(owner,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:
        owner.close(); return
    global HARNESS_OWNER_PIPE
    read_fd, write_fd = os.pipe() if os.name == 'posix' else (None, None)
    HARNESS_OWNER_PIPE = write_fd
    try:
        owner_env = {
            'BH_OWNER_PID': str(HARNESS_OWNER_PID),
            'BH_OWNER_STARTED': str(HARNESS_OWNER_STARTED or ''),
            'BH_OWNER_TOKEN': HARNESS_OWNER_TOKEN,
        }
        if read_fd is not None:
            owner_env['BH_OWNER_PIPE_FD'] = str(read_fd)
        ensure_daemon(env=owner_env)
    finally:
        if read_fd is not None:
            os.close(read_fd)
    def terminate(_signum, _frame):
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, terminate)
    signal.signal(signal.SIGINT, terminate)
    # Lock ownership is required before changing the shared socket path.
    SOCKET_PATH.unlink(missing_ok=True)
    srv=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM); srv.bind(str(SOCKET_PATH)); os.chmod(SOCKET_PATH,0o600); SOCKET_IDENTITY=(SOCKET_PATH.stat().st_dev, SOCKET_PATH.stat().st_ino); srv.listen(32)
    install_session_output()
    from platform_runner import PLATFORMS
    chatgpt_runtime = PLATFORMS/'chatgpt'/'runtime'
    if chatgpt_runtime.is_dir():
        sys.path.insert(0, str(chatgpt_runtime))
        from chatgpt_queue_runtime import DaemonTurnQueue
        CHATGPT_QUEUE = DaemonTurnQueue(RUNTIME_DIR, start_session, exec_session, stop_session)
    threading.Thread(target=reconciliation_loop, daemon=True).start()
    try:
        while True:
            conn,_=srv.accept(); threading.Thread(target=serve_conn,args=(conn,),daemon=True).start()
    finally:
        srv.close(); owner.close()
if __name__=='__main__': main()
