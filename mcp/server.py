#!/usr/bin/env python3
from __future__ import annotations
import json, sys, threading
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from session_client import request

SEND_LOCK=threading.Lock()
TOOLS=[
 {'name':'session.start','description':'Start a persistent Python Browser Harness session and lease one tab from the requested Browser Workspace. Multiple sessions can coexist concurrently.','inputSchema':{'type':'object','properties':{'workspace':{'type':'string','minLength':1,'description':'Workspace/tab-group name. Defaults to Harness.'}},'additionalProperties':False}},
 {'name':'session.exec','description':'Execute arbitrary Python in the persistent Browser Harness session. Before using this tool, use/load the `browser-harness` skill to learn the available helper methods, recommended workflow, and interaction rules. Helpers are already preloaded in the Python namespace; globals, imports, variables and the leased tab survive across calls.','inputSchema':{'type':'object','properties':{'session_id':{'type':'string'},'code':{'type':'string'}},'required':['session_id','code'],'additionalProperties':False}},
 {'name':'session.stop','description':'Release the session workspace tab and discard its persistent Python namespace.','inputSchema':{'type':'object','properties':{'session_id':{'type':'string'}},'required':['session_id'],'additionalProperties':False}},
]
def tr(payload,is_error=False): return {'content':[{'type':'text','text':json.dumps(payload,ensure_ascii=False)}],'structuredContent':payload,**({'isError':True} if is_error else {})}
def handle(msg):
    method=msg.get('method'); params=msg.get('params') or {}
    if method=='initialize': return {'protocolVersion':params.get('protocolVersion','2025-06-18'),'capabilities':{'tools':{}},'serverInfo':{'name':'browser-workspace','version':'0.3.0'}}
    if method=='ping': return {}
    if method=='tools/list': return {'tools':TOOLS}
    if method=='tools/call':
        name=params.get('name'); a=params.get('arguments') or {}
        try:
            if name=='session.start': return tr(request({'op':'start','workspace':a.get('workspace')}))
            if name=='session.exec':
                r=request({'op':'exec','session_id':a['session_id'],'code':a['code']}); return tr(r,is_error=not r.get('ok',False))
            if name=='session.stop': return tr(request({'op':'stop','session_id':a['session_id']}))
            return tr({'error':f'unknown tool: {name}'},True)
        except Exception as exc: return tr({'error':f'{type(exc).__name__}: {exc}'},True)
    return None
def send(x):
    with SEND_LOCK: sys.stdout.write(json.dumps(x,ensure_ascii=False)+'\n'); sys.stdout.flush()
def dispatch(msg):
    try:
        r=handle(msg); send({'jsonrpc':'2.0','id':msg['id'],**({'result':r} if r is not None else {'error':{'code':-32601,'message':'Method not found'}})})
    except Exception as exc: send({'jsonrpc':'2.0','id':msg['id'],'error':{'code':-32603,'message':f'{type(exc).__name__}: {exc}'}})
def main():
    for line in sys.stdin:
        try: msg=json.loads(line)
        except json.JSONDecodeError: continue
        if 'id' not in msg: continue
        threading.Thread(target=dispatch,args=(msg,),daemon=True).start()
if __name__=='__main__': main()
