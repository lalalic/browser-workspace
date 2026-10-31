/**
 * Observe the signed-in webpage's own SSE. Do not issue requests, access
 * credentials, or alter response streams consumed by the site.
 */
function installPassiveObserver() {
  if (window.__webhelmDeepseekStream?.version === 3) return;
  const stream = {version:3,entries:[]};
  window.__webhelmDeepseekStream=stream;
  const endpoint = /\/api\/v0\/chat\/(?:completion|resume_stream)(?:\?|$)/;
  const saveChunk = (entry, text) => {
    if (entry.state === 'oversized') return;
    if (entry.body.length + text.length > 2000000) {
      entry.state='oversized';entry.error='DeepSeek SSE exceeded 2 MB';entry.body='';
      return;
    }
    entry.body += text;
  };
  const startEntry = status => {
    const entry={state:'reading',http:status,body:'',error:''};
    stream.entries.push(entry);
    if(stream.entries.length>30)stream.entries.shift();
    return entry;
  };
  const fetchOriginal=window.fetch;
  window.fetch=function(...args) {
    const url=String(args[0]?.url||args[0]||'');
    const request=fetchOriginal.apply(this,args);
    if(!endpoint.test(url))return request;
    return request.then(response=>{
      const entry=startEntry(response.status);
      try {
        const reader=response.clone().body?.getReader();
        if(!reader){entry.state='read_error';entry.error='Unreadable stream';return response;}
        const decoder=new TextDecoder();
        (async()=>{
          try{
            for(;;){
              const {value,done}=await reader.read();
              if(done)break;
              saveChunk(entry,decoder.decode(value,{stream:true}));
              if(entry.state==='oversized'){await reader.cancel();return;}
            }
            saveChunk(entry,decoder.decode());
            if(entry.state==='reading')entry.state='received';
          }catch(error){entry.state='read_error';entry.error=String(error);}
        })();
      }catch(error){entry.state='read_error';entry.error=String(error);}
      return response;
    });
  };
  const open=XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open=function(method,url,...args){
    this.__webhelmDeepseekEndpoint=endpoint.test(String(url||''));
    return open.call(this,method,url,...args);
  };
  const send=XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.send=function(...args){
    if(this.__webhelmDeepseekEndpoint){
      const entry=startEntry(null);
      let size=0;
      this.addEventListener('progress',()=>{
        try{
          const value=this.responseText;
          if(typeof value==='string'&&value.length>size){
            saveChunk(entry,value.slice(size));size=value.length;
          }
        }catch(e){entry.state='read_error';entry.error=String(e);}
      });
      this.addEventListener('loadend',()=>{
        entry.http=this.status;
        try{
          const value=this.responseText;
          if(typeof value==='string'&&value.length>size)saveChunk(entry,value.slice(size));
        }catch(e){entry.state='read_error';entry.error=String(e);}
        if(entry.state==='reading')entry.state='received';
      },{once:true});
    }
    return send.apply(this,args);
  };
}
export const STREAM_OBSERVER='('+installPassiveObserver.toString()+')()';
export const STREAM_STATE='(()=>{const e=window.__webhelmDeepseekStream?.entries||[];return {count:e.length,latest:e.length?{state:e.at(-1).state,http:e.at(-1).http,body:e.at(-1).body,error:e.at(-1).error}:null};})()';

export function parseSiteStream(body) {
  if(typeof body!=='string'||!body)return {ready:false,finished:false,closed:false,answer:''};
  let ready=false,finished=false,closed=false,error=false,fragments=[],lastPath=null;
  for(const block of body.split(/\r?\n\r?\n/)){
    const event=/^event:\s*(.*)$/m.exec(block)?.[1]?.trim() || '';
    const lines=block.split(/\r?\n/).filter(line=>line.startsWith('data:')).map(line=>line.slice(5).trim());
    if(event==='close')closed=true;
    if(event==='error')error=true;
    if(!lines.length)continue;
    let payload;
    try{payload=JSON.parse(lines.join('\n'));}catch{continue;}
    if(event==='ready'){
      ready=!!(payload&&typeof payload==='object'&&payload.request_message_id&&payload.response_message_id);
      continue;
    }
    if(!payload||typeof payload!=='object')continue;
    const value=payload.v;
    const response=value&&typeof value==='object'?value.response:null;
    if(response&&typeof response==='object'){
      if(response.status==='FINISHED')finished=true;
      if(Array.isArray(response.fragments))
        fragments=response.fragments.filter(x=>x&&typeof x==='object').map(x=>({...x}));
    }
    const path=payload.p??lastPath;
    if(payload.p)lastPath=path;
    if(path==='response/status'&&value==='FINISHED')finished=true;
    const match=typeof path==='string'&&/^response\/fragments\/(-1|\d+)\/content$/.exec(path);
    if(match&&fragments.length&&typeof value==='string'){
      const idx=Number(match[1]);
      const real=idx===-1?fragments.length-1:idx;
      if(real>=0&&real<fragments.length)
        fragments[real].content=payload.o==='SET'?value:String(fragments[real].content||'')+value;
    }
  }
  return {ready,finished,closed,error,
    answer:fragments.filter(x=>x.type==='RESPONSE').map(x=>String(x.content||'')).join('').trim()};
}

export async function installResponseObserver(h) {
  if(typeof h.cdp==='function')
    await h.cdp('Page.addScriptToEvaluateOnNewDocument',{source:STREAM_OBSERVER});
  await h.js(STREAM_OBSERVER);
}
export async function readResponseStream(h,before=0){
  const state=await h.js(STREAM_STATE);
  if(!state||state.count<=before||!state.latest)return null;
  const entry=state.latest;
  if(entry.state==='oversized'||entry.state==='read_error')
    throw new Error('DeepSeek webpage SSE observer failed: '+entry.error);
  if(entry.http!==null&&entry.http!==200)
    throw new Error('DeepSeek webpage SSE rejected by HTTP '+entry.http);
  const parsed=parseSiteStream(entry.body);
  if(parsed.error)throw new Error('DeepSeek webpage SSE signalled an error');
  if(entry.state==='received'&&!(parsed.ready&&parsed.finished&&parsed.closed&&parsed.answer))
    return {state:'incomplete',accepted:parsed.ready};
  if(parsed.ready&&parsed.finished&&parsed.closed&&parsed.answer)
    return {state:'completed',accepted:true,answer:parsed.answer};
  return {state:'pending',accepted:parsed.ready};
}
