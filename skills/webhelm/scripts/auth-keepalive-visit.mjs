#!/usr/bin/env node
/** Read-only login page checks with owned WebHelm sessions and private cookie audit. */
import { spawn } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const DIR=path.dirname(fileURLToPath(import.meta.url));
export const SITES=[
  ['wechat','https://channels.weixin.qq.com/platform/post'],
  ['xiaohongshu','https://www.xiaohongshu.com/explore?channel_id=homefeed_recommend'],
  ['google_store','https://chrome.google.com/webstore/devconsole'],
];
export const READONLY="console.log(JSON.stringify(await page_info()));console.log((await snapshot()).slice(0,2000));console.log((await snapshot()).slice(-1500));";
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
export function classify(site,output){
  const text=String(output).toLowerCase();
  if(site==='wechat'){
    if(output.includes('内容管理')&&output.includes('数据中心'))return ['logged_in','backend_visible'];
    if(output.includes('加载失败，点击重试'))return ['page_error','page_load_failed'];
  }
  if(site==='google_store'&&output.includes('Switch Publisher Account Menu')&&output.includes('Add a new item'))return ['logged_in','backend_visible'];
  if(site==='xiaohongshu'&&['发布','消息','我'].every(x=>output.includes(x)))return ['unknown','feed_only'];
  if(text.includes('signin/confirmidentifier')||text.includes('/login.html'))return ['login_required','login_redirect'];
  return ['unknown','unknown'];
}
function executable(){return process.env.WEBHELM_CLI||'webhelm';}
export async function subprocess(program,args,{input,timeout=25000}={}){
  return new Promise((resolve,reject)=>{
    const child=spawn(program,args,{stdio:['pipe','pipe','pipe']});let stdout='',stderr='';
    const timer=setTimeout(()=>{child.kill('SIGTERM');reject(new Error('CommandTimeout'));},timeout);
    child.stdout.on('data',chunk=>stdout+=chunk);child.stderr.on('data',chunk=>stderr+=chunk);
    child.on('error',error=>{clearTimeout(timer);reject(error);});
    child.on('close',code=>{clearTimeout(timer);if(code===0){try{resolve(JSON.parse(stdout));}catch(error){reject(new Error('Invalid JSON response'));}}else reject(new Error(`CommandFailed:${code}:${stderr.slice(0,160)}`));});
    child.stdin.end(input||'');
  });
}
export async function visit(site,url,run=subprocess,audit=subprocess){
  let sessionId=null,status='unknown',evidence='unknown',retries=0,error=null,cleanup=null;
  try{
    const started=await run(executable(),['session','start','--url',url]);
    sessionId=started.session_id;
    if(!sessionId)throw Error('WebHelm session start returned no session_id');
    for(let i=0;i<3;i++){
      const result=await run(executable(),['session','exec',sessionId],{input:READONLY});
      [status,evidence]=classify(site,result.stdout||'');
      if(status!=='unknown'||evidence!=='unknown')break;
      if(i<2){retries++;await sleep(2000);}
    }
  }catch(e){error=e.message?.split(':')[0]||e.name||'UnknownError';}
  finally{
    if(sessionId){
      for(let i=0;i<3;i++){
        try{const stopped=await run(executable(),['session','stop',sessionId],{timeout:20000});
          cleanup=stopped.release_error==null;if(cleanup)break;
        }catch{cleanup=false;}
      }
    }
    try{await audit(process.execPath,[path.join(DIR,'auth-cookie-audit.mjs'),'--site',site,'--status',status,'--page-evidence',evidence]);}
    catch{error ||= 'AuditFailed';}
  }
  return {site,status,evidence,retries,session_closed:cleanup,error};
}
export async function main({run=subprocess,audit=subprocess}={}){
  try{await audit(process.execPath,[path.join(DIR,'auth-cookie-audit.mjs')]);}catch{}
  const results=[];for(const [site,url] of SITES)results.push(await visit(site,url,run,audit));
  const output={timestamp:Math.floor(Date.now()/1000),results};
  console.log(JSON.stringify(output));
  return results.every(x=>x.session_closed===true)?0:1;
}
if(process.argv[1]===fileURLToPath(import.meta.url))main().then(code=>process.exitCode=code).catch(e=>{console.error(e.message);process.exitCode=1;});
