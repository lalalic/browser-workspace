import test from 'node:test';
import assert from 'node:assert/strict';
import { run } from '../deepseek/actions/_lifecycle_common.mjs';

const URL='https://chat.deepseek.com';
const THREAD='e1e1e1e1-e1e1-4e1e-a1e1-e1e1e1e1e1e1';
function browser({ userAccepted=false, newAnswer=false, existingAnswers=0 }={}) {
  const b={
    url:URL, clicks:0, waits:0,
    async page_info(){return {url:this.url}},
    async wait_for_load(){},
    async wait_for_element(){return true},
    async wait(t){this.waits++;},
    async goto_url(url){this.url=url},
    async fill_input(){},
    async click(){this.clicks++;this.url=URL+'/a/chat/s/'+THREAD},
    async js(script){
      if(script.includes('const c=document.querySelector(')) return {draft:false,idle:true};
      if(script.includes('.ds-message')) return this.clicks && userAccepted ? 1 : 0;
      if(script.includes('ds-assistant-message-main-content')) {
        return {count:existingAnswers+(this.clicks && newAnswer ? 1 : 0),
          answer:this.clicks && newAnswer?'RECEIPT-TEST-31':'prior reply',
          settled:true};
      }
      if(script.includes("?.value===''")) return this.clicks>0;
      return null;
    },
  };
  return b;
}
test('no user message or new answer: return pending, NOT verified completed or resent',async()=>{
  const h=browser();
  const result=await run({message:'Receipt probe',timeout_seconds:1},'new-thread',h);
  assert.equal(result.status,'pending');
  assert.equal(result.submission_verified,false);
  assert.equal(result.thread_id,THREAD);
  assert.equal(result.answers_before,0);
  assert.equal(h.clicks,1);
  assert.match(result.next_step,/do not resend/i);
});
test('matching user message and a new settled answer: completed',async()=>{
  const h=browser({userAccepted:true,newAnswer:true});
  const result=await run({message:'Receipt probe',timeout_seconds:1},'new-thread',h);
  assert.equal(result.status,'completed');
  assert.equal(result.answer,'RECEIPT-TEST-31');
  assert.equal(result.submission_verified,true);
  assert.equal(h.clicks,1);
});
test('new settled answer alone verifies delivery when selectors drift',async()=>{
  const h=browser({newAnswer:true});
  const result=await run({message:'Receipt probe',timeout_seconds:1},'new-thread',h);
  assert.equal(result.status,'completed');
  assert.equal(result.submission_verified,true);
  assert.equal(result.answer,'RECEIPT-TEST-31');
  assert.equal(h.clicks,1);
});
test('read-only resume refuses to treat an earlier answer as the new reply',async()=>{
  const h=browser({existingAnswers:4});
  h.url=URL+'/a/chat/s/'+THREAD;
  const result=await run({resume:true,thread_id:THREAD,min_answer_count:4,timeout_seconds:1},'new-thread',h);
  assert.equal(result.status,'pending');
  assert.equal(h.clicks,0);
  assert.equal(result.answers_before,4);
});
test('read-only resume completes only on new answer beyond prior count',async()=>{
  const h=browser({existingAnswers:4,newAnswer:true});
  h.url=URL+'/a/chat/s/'+THREAD;
  // Mark the page as already having a new answer, but no new input click.
  h.clicks=1;
  const result=await run({resume:true,thread_id:THREAD,min_answer_count:4,timeout_seconds:1},'new-thread',h);
  assert.equal(result.status,'completed');
  assert.equal(result.answer,'RECEIPT-TEST-31');
});
