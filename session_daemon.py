#!/usr/bin/env python3
from __future__ import annotations
import ast, atexit, contextlib, io, json, os, secrets, socket, sys, threading, traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT/'src'))
os.environ.setdefault('BH_HOME', str(Path.home()/'.config/browser-workspace/browser-core'))
# Preserve the canonical single Browser Harness daemon socket during migration.
# This is runtime-state compatibility only; Browser Workspace owns the code/venv.
os.environ.setdefault('BH_RUNTIME_DIR', str(Path.home()/'.config/browser-harness/runtime'))
os.environ.setdefault('BH_RUNTIME_DIR_SHARED', '1')
os.environ.setdefault('BH_AGENT_WORKSPACE', str(ROOT/'agent-workspace'))
os.environ.setdefault('BH_WORKSPACE_NAME', 'Harness')

from browser_harness.admin import ensure_daemon
ensure_daemon()
from browser_harness import helpers as bh

DEFAULT_WORKSPACE = os.environ.get('BH_WORKSPACE_NAME','Harness')
RUNTIME_DIR = Path(os.environ.get('BROWSER_WORKSPACE_RUNTIME_DIR', Path.home()/'.config/browser-workspace/runtime'))
SOCKET_PATH = Path(os.environ.get('BROWSER_WORKSPACE_SESSION_SOCKET', RUNTIME_DIR/'session.sock'))
SESSIONS = {}
SESSIONS_LOCK = threading.Lock()
BROWSER_LOCK = threading.RLock()

class SessionBrowserProxy:
    def __init__(self, session): self._session=session
    def __getattr__(self, name): return getattr(bh, name)
    def new_tab(self, url='about:blank'): return self._session._new_tab(url)
    def close_tab(self, target=None): return self._session._close_tab(target)
    def cdp(self, method, **kwargs): return self._session._cdp(method, **kwargs)

class Session:
    def __init__(self, sid, workspace, target_id, workspace_supported):
        self.session_id=sid; self.workspace=workspace; self.target_id=target_id; self.workspace_supported=bool(workspace_supported)
        self.owned_target_ids={target_id}
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
        return self._remember_target(bh.new_tab(url))

    def _close_tab(self, target=None):
        wanted=target
        if isinstance(wanted, dict): wanted=wanted.get('targetId') or wanted.get('target_id')
        if wanted is None: wanted=bh.current_tab().get('targetId')
        result=bh.close_tab(target)
        if wanted: self.owned_target_ids.discard(wanted)
        return result

    def _cdp(self, method, **kwargs):
        result=bh.cdp(method, **kwargs)
        if method == 'Target.createTarget' and isinstance(result, dict):
            self._remember_target(result.get('targetId'))
        elif method == 'Target.closeTarget':
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
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            if body: exec(compile(ast.Module(body=body,type_ignores=[]),'<browser-workspace-session>','exec'),namespace,namespace)
            if tail is not None:
                value=eval(compile(ast.Expression(tail.value),'<browser-workspace-session>','eval'),namespace,namespace); namespace['_']=value
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
    with BROWSER_LOCK, with_workspace(workspace, supported): tid=bh.new_tab(start_url)
    s=Session(sid,workspace,tid,supported)
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
    with s.lock, BROWSER_LOCK, with_workspace(s.workspace, s.workspace_supported):
        bh.switch_tab(s.target_id,activate=False)
        r=execute(code,s.namespace)
        absorb_owned_children(s)
        try:
            cur=bh.current_tab(); s.target_id=cur.get('targetId') or s.target_id; s.namespace['target_id']=s.target_id
        except Exception: pass
    return {'session_id':sid,'workspace':s.workspace,'target_id':s.target_id,**r}

def stop_session(sid):
    with SESSIONS_LOCK: s=SESSIONS.pop(sid,None)
    if not s: raise KeyError(f'unknown session_id: {sid}')
    release_error=None
    with s.lock, BROWSER_LOCK, with_workspace(s.workspace, s.workspace_supported):
        absorb_owned_children(s)
        closed_count=len(s.owned_target_ids)
        errors=close_owned_tabs(s)
        if errors: release_error='; '.join(errors)
    return {'session_id':sid,'workspace':s.workspace,'target_id':s.target_id,'closed_tabs':closed_count,'release_error':release_error}

def cleanup():
    with SESSIONS_LOCK: ids=list(SESSIONS)
    for sid in ids:
        try: stop_session(sid)
        except Exception: pass
    try: SOCKET_PATH.unlink(missing_ok=True)
    except Exception: pass
atexit.register(cleanup)

def handle(req):
    op=req.get('op')
    if op=='ping': return {'ok':True,'pid':os.getpid(),'session_count':len(SESSIONS)}
    if op=='start': return start_session(req.get('workspace'), req.get('url'))
    if op=='exec': return exec_session(req['session_id'],req.get('code',''))
    if op=='stop': return stop_session(req['session_id'])
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
    RUNTIME_DIR.mkdir(parents=True,exist_ok=True)
    try: os.chmod(RUNTIME_DIR,0o700)
    except Exception: pass
    SOCKET_PATH.unlink(missing_ok=True)
    srv=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM); srv.bind(str(SOCKET_PATH)); os.chmod(SOCKET_PATH,0o600); srv.listen(32)
    while True:
        conn,_=srv.accept(); threading.Thread(target=serve_conn,args=(conn,),daemon=True).start()
if __name__=='__main__': main()
