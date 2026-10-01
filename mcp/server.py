#!/usr/bin/env python3
from __future__ import annotations
import ast, atexit, contextlib, io, json, os, secrets, sys, threading, traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault('BH_HOME', str(Path.home()/'.config/browser-harness'))
os.environ.setdefault('BH_AGENT_WORKSPACE', str(ROOT/'browser-harness'))
os.environ.setdefault('BH_WORKSPACE_NAME', 'Harness')

from browser_harness.admin import ensure_daemon
ensure_daemon()
from browser_harness import helpers as bh

DEFAULT_WORKSPACE = os.environ.get('BH_WORKSPACE_NAME','Harness')
SESSIONS = {}
SESSIONS_LOCK = threading.Lock()
BROWSER_LOCK = threading.RLock()
SEND_LOCK = threading.Lock()

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

def start_session(workspace=None):
    workspace=(workspace or DEFAULT_WORKSPACE).strip()
    if not workspace: raise ValueError('workspace must not be empty')
    sid=secrets.token_hex(8)
    with BROWSER_LOCK, with_workspace(workspace):
        tid=bh.new_tab('about:blank')
    s=Session(sid,workspace,tid)
    with SESSIONS_LOCK: SESSIONS[sid]=s
    return {'session_id':sid,'workspace':workspace,'target_id':tid}

def get_session(sid):
    with SESSIONS_LOCK: s=SESSIONS.get(sid)
    if not s: raise KeyError(f'unknown session_id: {sid}')
    return s

def exec_session(sid,code):
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
atexit.register(cleanup)

TOOLS=[
 {'name':'session.start','description':'Start a persistent Python Browser Harness session and lease one tab from the requested Browser Workspace. Multiple sessions can coexist concurrently.','inputSchema':{'type':'object','properties':{'workspace':{'type':'string','minLength':1,'description':'Workspace/tab-group name. Defaults to Harness.'}},'additionalProperties':False}},
 {'name':'session.exec','description':'Execute arbitrary Python in the persistent session. Globals, imports, variables and the leased tab survive across calls. Browser actions are attached to this session target before each turn.','inputSchema':{'type':'object','properties':{'session_id':{'type':'string'},'code':{'type':'string'}},'required':['session_id','code'],'additionalProperties':False}},
 {'name':'session.stop','description':'Release the session workspace tab and discard its persistent Python namespace.','inputSchema':{'type':'object','properties':{'session_id':{'type':'string'}},'required':['session_id'],'additionalProperties':False}},
]

def tool_result(payload,is_error=False):
    return {'content':[{'type':'text','text':json.dumps(payload,ensure_ascii=False)}],'structuredContent':payload,**({'isError':True} if is_error else {})}

def handle(msg):
    method=msg.get('method'); params=msg.get('params') or {}
    if method=='initialize': return {'protocolVersion':params.get('protocolVersion','2025-06-18'),'capabilities':{'tools':{}},'serverInfo':{'name':'browser-workspace','version':'0.2.0'}}
    if method=='ping': return {}
    if method=='tools/list': return {'tools':TOOLS}
    if method=='tools/call':
        name=params.get('name'); args=params.get('arguments') or {}
        try:
            if name=='session.start': return tool_result(start_session(args.get('workspace')))
            if name=='session.exec':
                r=exec_session(args['session_id'],args['code']); return tool_result(r,is_error=not r.get('ok',False))
            if name=='session.stop': return tool_result(stop_session(args['session_id']))
            return tool_result({'error':f'unknown tool: {name}'},True)
        except Exception as exc: return tool_result({'error':f'{type(exc).__name__}: {exc}'},True)
    return None

def send(x):
    with SEND_LOCK:
        sys.stdout.write(json.dumps(x,ensure_ascii=False)+'\n'); sys.stdout.flush()

def dispatch(msg):
    try:
        r=handle(msg)
        send({'jsonrpc':'2.0','id':msg['id'],**({'result':r} if r is not None else {'error':{'code':-32601,'message':'Method not found'}})})
    except Exception as exc:
        send({'jsonrpc':'2.0','id':msg['id'],'error':{'code':-32603,'message':f'{type(exc).__name__}: {exc}'}})

def main():
    threads=[]
    for line in sys.stdin:
        try: msg=json.loads(line)
        except json.JSONDecodeError: continue
        if 'id' not in msg: continue
        t=threading.Thread(target=dispatch,args=(msg,),daemon=True); t.start(); threads.append(t)
    for t in threads: t.join(timeout=1)
if __name__=='__main__': main()
