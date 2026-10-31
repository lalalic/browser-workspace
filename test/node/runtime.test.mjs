import test from 'node:test';
import assert from 'node:assert/strict';
import {handle} from '../../src/node-daemon.mjs';

class MockWebSocket extends EventTarget {
  static OPEN=1;
  readyState=0;
  constructor(){super();MockWebSocket.last=this;queueMicrotask(()=>{this.readyState=1;this.dispatchEvent(new Event('open'))})}
  emit(method,params,sessionId){this.dispatchEvent(new MessageEvent('message',{data:JSON.stringify({method,params,sessionId})}))}
  send(raw){const m=JSON.parse(raw);let result={};switch(m.method){
    case'Target.setDiscoverTargets':result={};break;
    case'Target.createTarget':result={targetId:`t${++MockWebSocket.target}`};MockWebSocket.targets.push({targetId:result.targetId,type:'page',url:m.params.url});break;
    case'Target.attachToTarget':result={sessionId:`s${++MockWebSocket.session}`};MockWebSocket.attach.set(result.sessionId,m.params.targetId);break;
    case'Target.detachFromTarget':result={};break;
    case'Target.closeTarget':MockWebSocket.targets=MockWebSocket.targets.filter(t=>t.targetId!==m.params.targetId);result={success:true};break;
    case'Target.getTargets':result={targetInfos:[...MockWebSocket.targets]};break;
    case'Target.getTargetInfo':result={targetInfo:MockWebSocket.targets.find(t=>t.targetId===m.params.targetId)||{}};break;
    case'Runtime.evaluate':{const target=MockWebSocket.attach.get(m.sessionId);const exp=m.params.expression;let value;if(exp==='document.readyState')value='complete';else if(exp.startsWith('({url:location.href'))value={url:`mock://${target}`,title:target,readyState:'complete'};else if(exp.startsWith('!!document.querySelector'))value=true;else value=true;result={result:{type:'object',value}};break}
    default:result={};
  }queueMicrotask(()=>this.dispatchEvent(new MessageEvent('message',{data:JSON.stringify({id:m.id,result})}))) }
  close(){this.readyState=3;this.dispatchEvent(new Event('close'))}
}
MockWebSocket.target=100;MockWebSocket.session=0;MockWebSocket.targets=[{targetId:'preexisting',type:'page',url:'https://keep.example/'}];MockWebSocket.attach=new Map();

test('independent sessions use explicit target attachments and stop preserves unrelated tabs',async()=>{
  globalThis.WebSocket=MockWebSocket;
  globalThis.fetch=async()=>({json:async()=>({webSocketDebuggerUrl:'ws://mock'})});
  const [a,b]=await Promise.all([handle({op:'start',url:'https://a.example'}),handle({op:'start',url:'https://b.example'})]);
  assert.notEqual(a.target_id,b.target_id);
  const sessionA=[...MockWebSocket.attach.entries()].find(([,target])=>target===a.target_id)[0];
  const sessionB=[...MockWebSocket.attach.entries()].find(([,target])=>target===b.target_id)[0];
  MockWebSocket.last.emit('Network.requestWillBeSent',{requestId:'only-a'},sessionA);
  MockWebSocket.last.emit('Network.responseReceived',{requestId:'only-b'},sessionB);
  const [ra,rb]=await Promise.all([handle({op:'exec',session_id:a.session_id,code:'events()'}),handle({op:'exec',session_id:b.session_id,code:'events()'})]);
  assert.deepEqual(ra.value.map(e=>e.params.requestId),['only-a']);
  assert.deepEqual(rb.value.map(e=>e.params.requestId),['only-b']);
  const started=Date.now();
  const slow=handle({op:'exec',session_id:a.session_id,code:"await wait(120); 'slow'"});
  const fast=await handle({op:'exec',session_id:b.session_id,code:"'fast'"});
  assert.equal(fast.value,'fast');assert.ok(Date.now()-started<100,'independent session was serialized behind another session');
  await slow;
  MockWebSocket.targets.push({targetId:'popup-a',type:'page',url:'https://popup.example/',openerId:a.target_id});
  MockWebSocket.last.emit('Target.targetCreated',{targetInfo:MockWebSocket.targets.at(-1)});
  await handle({op:'stop',session_id:a.session_id});
  assert.ok(!MockWebSocket.targets.some(t=>t.targetId==='popup-a'),'session stop left its popup open');
  await handle({op:'stop',session_id:b.session_id});
  assert.ok(MockWebSocket.targets.some(t=>t.targetId==='preexisting'));
  assert.equal(MockWebSocket.targets.length,1);
});

test('same-session declarations persist and session stop is idempotency guarded',async()=>{
  const s=await handle({op:'start'});
  await handle({op:'exec',session_id:s.session_id,code:'let counter = 40'});
  const r=await handle({op:'exec',session_id:s.session_id,code:'counter + 2'});
  assert.equal(r.value,42);
  MockWebSocket.last.close();
  const reconnected=await handle({op:'exec',session_id:s.session_id,code:'await page_info()'});
  assert.equal(reconnected.value.url,`mock://${s.target_id}`);
  await handle({op:'stop',session_id:s.session_id});
  await assert.rejects(handle({op:'exec',session_id:s.session_id,code:'1'}),/unknown session_id/);
});
