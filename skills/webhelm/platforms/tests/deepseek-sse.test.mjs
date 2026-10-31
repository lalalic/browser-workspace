import test from 'node:test';
import assert from 'node:assert/strict';
import {parseSiteStream, readResponseStream, STREAM_OBSERVER, STREAM_STATE} from '../deepseek/actions/_response_stream.mjs';
import {run} from '../deepseek/actions/_lifecycle_common.mjs';

function goodSse(answer='Reply by native stream') {
  const events=[
    ['ready',{request_message_id:'req-1',response_message_id:'resp-1'}],
    ['update',{v:{response:{status:'IN_PROGRESS',fragments:[{type:'RESPONSE',content:''},{type:'THINKING',content:'hidden'}]}}}],
    ['update',{p:'response/fragments/0/content',v:answer,o:'APPEND'}],
    ['update',{p:'response/status',v:'FINISHED'}],
    ['close',{}],
  ];
  return events.map(([event,data])=>'event: '+event+'\ndata: '+JSON.stringify(data)+'\n\n').join('');
}
test('native DeepSeek SSE needs ready + FINISHED + close, not a DOM answer',()=>{
  const full=parseSiteStream(goodSse());
  assert.deepEqual(full,{ready:true,finished:true,closed:true,error:false,answer:'Reply by native stream'});
  const missingClose=parseSiteStream(goodSse().replace('event: close','event: done'));
  assert.equal(missingClose.closed,false);
  const withoutReady=parseSiteStream(goodSse().replace('event: ready','event: unknown'));
  assert.equal(withoutReady.ready,false);
  const withError=parseSiteStream(goodSse()+'event: error\ndata: {}\n\n');
  assert.equal(withError.error,true);
});
test('SSE observer is passive and hookable before navigation',()=>{
  assert.ok(STREAM_OBSERVER.includes('response.clone()'));
  assert.ok(STREAM_OBSERVER.includes('/api'));
  assert.ok(!STREAM_OBSERVER.includes('fetch(')); // only wraps site-owned fetch
  assert.ok(STREAM_STATE.includes('__webhelmDeepseekStream'));
});
test('completed SSE receipt is returned with no DOM user or assistant nodes',async()=>{
  const URL='https://chat.deepseek.com';
  const THREAD='12345678-1234-4123-8123-123456789abc';
  let clicks=0, cdpCalls=[],installed=false;
  const h={
    async page_info(){return {url: clicks?URL+'/a/chat/s/'+THREAD:URL}},
    async cdp(method,args){cdpCalls.push([method,args])},
    async js(source){
      if(source===STREAM_OBSERVER){installed=true;return null;}
      if(source===STREAM_STATE)return {count:clicks?1:0,
        latest:clicks?{state:'received',http:200,body:goodSse(),error:''}:null};
      if(source.includes('const c=document.querySelector('))return {draft:false,idle:true};
      if(source.includes('.ds-assistant-message-main-content'))return {count:0,answer:'',settled:false};
      if(source.includes('.ds-message'))return 0;
      if(source.includes("?.value===''"))return clicks>0;
      return false;
    },
    async wait_for_element(){return true},
    async goto_url(){},
    async wait_for_load(){},
    async fill_input(){},
    async click(){clicks++},
    async wait(){},
  };
  const result=await run({message:'SSE test',timeout_seconds:2},'new-thread',h);
  assert.equal(result.status,'completed');
  assert.equal(result.answer,'Reply by native stream');
  assert.equal(result.submission_verified,true);
  assert.match(result.verified_by,/SSE/);
  assert.equal(clicks,1);
  assert.equal(cdpCalls[0][0],'Page.addScriptToEvaluateOnNewDocument');
  assert.equal(installed,true);
});
test('missing FINISHED produces incomplete, not a false completed reply',async()=>{
  const fake={async js(){return {count:1,latest:{
    state:'received',http:200,body:goodSse().replace('FINISHED','RUNNING'),error:''
  }};}};
  assert.deepEqual(await readResponseStream(fake,0),{state:'incomplete',accepted:true});
});
test('read-only stream state is associated only with a new request after baseline',async()=>{
  const fake={async js(){return {count:1,latest:{state:'received',http:200,body:goodSse(),error:''}}}};
  assert.equal(await readResponseStream(fake,1),null);
  assert.equal((await readResponseStream(fake,0)).answer,'Reply by native stream');
});
