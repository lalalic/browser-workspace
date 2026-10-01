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

class Session:
    def __init__(self, sid, workspace, target_id):
        self.session_id=sid; self.workspace=workspace; self.target_id=target_id
        self.lock=threading.Lock()
        self.namespace={'__name__':'__browser_workspace_session__','bh':bh,'target_id':target_id}
        for name in dir(bh):
            if not name.startswith('_'): self.namespace[name]=getattr(bh,name)

def with_workspace(name):
    class Scope:
        def __enter__(self): self.token=bh.workspace_set_name(name); return self
        def __exit__(self,*_): bh.workspace_reset_name(self.token)
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
    with BROWSER_LOCK, with_workspace(workspace): tid=bh.new_tab(start_url)
    s=Session(sid,workspace,tid)
    with SESSIONS_LOCK: SESSIONS[sid]=s
    return {'session_id':sid,'workspace':workspace,'target_id':tid,'url':start_url}

def get_session(sid):
    with SESSIONS_LOCK: s=SESSIONS.get(sid)
    if not s: raise KeyError(f'unknown session_id: {sid}')
    return s

def exec_session(sid, code):
    s=get_session(sid)
    with s.lock, BROWSER_LOCK, with_workspace(s.workspace):
        bh.switch_tab(s.target_id,activate=False)
        r=execute(code,s.namespace)
        try:
            cur=bh.current_tab(); s.target_id=cur.get('targetId') or s.target_id; s.namespace['target_id']=s.target_id
        except Exception: pass
    return {'session_id':sid,'workspace':s.workspace,'target_id':s.target_id,**r}

def stop_session(sid):
    with SESSIONS_LOCK: s=SESSIONS.pop(sid,None)
    if not s: raise KeyError(f'unknown session_id: {sid}')
    release_error=None
    with s.lock, BROWSER_LOCK, with_workspace(s.workspace):
        try: bh.close_tab(s.target_id)
        except Exception as exc: release_error=f'{type(exc).__name__}: {exc}'
    return {'session_id':sid,'workspace':s.workspace,'target_id':s.target_id,'release_error':release_error}

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
