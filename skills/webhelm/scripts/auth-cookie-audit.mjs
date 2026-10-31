#!/usr/bin/env node
/** Read-only Chrome Cookie metadata audit. No credentials are logged or exported. */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import { DatabaseSync } from 'node:sqlite';
import { fileURLToPath } from 'node:url';

export const SITES = Object.freeze({wechat:['weixin.qq.com'],xiaohongshu:['xiaohongshu.com'],google_store:['google.com','googleusercontent.com']});
const WATCHED = {wechat:new Set(['sessionid','wxuin'])};
const OFFSET = 11644473600;
export function utcCookieTime(micros){return micros ? Math.trunc(Number(micros)/1_000_000 - OFFSET):null;}
export function domainMatches(host,domain){const h=String(host||'').replace(/^\./,'').toLowerCase();return h===domain || h.endsWith(`.${domain}`);}
const hmac=(key,bytes)=>crypto.createHmac('sha256',key).update(bytes).digest('hex').slice(0,24);
export function loadKey(keyPath){
  fs.mkdirSync(path.dirname(keyPath),{recursive:true,mode:0o700});
  const flags=fs.constants.O_NOFOLLOW||0;
  let fd;
  try {fd=fs.openSync(keyPath,fs.constants.O_RDONLY|flags);}
  catch(e){
    if(e.code!=='ENOENT')throw e;
    try{const create=fs.openSync(keyPath,fs.constants.O_CREAT|fs.constants.O_EXCL|fs.constants.O_WRONLY|flags,0o600);
      try{fs.writeSync(create,crypto.randomBytes(32));}finally{fs.closeSync(create);}}
    catch(error){if(error.code!=='EEXIST')throw error;}
    fd=fs.openSync(keyPath,fs.constants.O_RDONLY|flags);
  }
  try{const stat=fs.fstatSync(fd);if(stat.mode&0o077)throw Error('HMAC key must be readable only by owner');
    const bytes=fs.readFileSync(fd);if(bytes.length!==32)throw Error('invalid HMAC key');return bytes;
  }finally{fs.closeSync(fd);}
}
export function collect(databasePath,key){
  const db=new DatabaseSync(databasePath,{readOnly:true,timeout:5000});
  try{
    db.exec('PRAGMA query_only=ON');
    const rows=db.prepare(`SELECT host_key,name,path,top_frame_site_key,encrypted_value,value,
       expires_utc,creation_utc,last_update_utc,last_access_utc,
       is_secure,is_httponly,samesite,is_persistent FROM cookies`).iterate();
    const result=Object.fromEntries(Object.keys(SITES).map(site=>[site,{}]));
    for(const row of rows){
      const sites=Object.entries(SITES).filter(([,domains])=>domains.some(domain=>domainMatches(row.host_key,domain))).map(([name])=>name);
      if(!sites.length)continue;
      const encrypted=row.encrypted_value && row.encrypted_value.length ? row.encrypted_value : Buffer.from(row.value||'');
      const fingerprint=hmac(key,encrypted);
      const identifier=hmac(key,Buffer.from([row.host_key,row.name,row.path,row.top_frame_site_key||''].join('\0')));
      for(const site of sites)result[site][identifier]={
        id:identifier,host:row.host_key,fingerprint,
        expires_at:utcCookieTime(row.expires_utc),created_at:utcCookieTime(row.creation_utc),
        updated_at:utcCookieTime(row.last_update_utc),last_access_at:utcCookieTime(row.last_access_utc),
        persistent:Boolean(row.is_persistent),secure:Boolean(row.is_secure),http_only:Boolean(row.is_httponly),
        same_site:row.samesite,partitioned:Boolean(row.top_frame_site_key),
        watched_name:WATCHED[site]?.has(row.name)?row.name:null,
      };
    }
    return result;
  }finally{db.close();}
}
export function difference(previous,current){
  return Object.fromEntries(Object.entries(current).map(([site,entries])=>{
    const old=previous[site]||{};const before=new Set(Object.keys(old)),after=new Set(Object.keys(entries));
    const changes={added:[...after].filter(x=>!before.has(x)).length,
      removed:[...before].filter(x=>!after.has(x)).length,value_rotated:0,
      expiry_extended:0,expiry_shortened:0,last_update_changed:0};
    for(const id of before){if(!after.has(id))continue;
      const a=old[id],b=entries[id];changes.value_rotated+=Number(a.fingerprint!==b.fingerprint);
      if(a.expires_at!=null&&b.expires_at!=null){changes.expiry_extended+=Number(b.expires_at>a.expires_at);changes.expiry_shortened+=Number(b.expires_at<a.expires_at);}
      changes.last_update_changed+=Number(a.updated_at!==b.updated_at);
    }return [site,changes];
  }));
}
function secureWrite(file,bytes){const fd=fs.openSync(file,fs.constants.O_WRONLY|fs.constants.O_CREAT|fs.constants.O_EXCL,0o600);
  try{fs.writeFileSync(fd,bytes);fs.fsyncSync(fd);}finally{fs.closeSync(fd);}}
export function sample({profile,dataDir,site,status='unknown',pageEvidence='unknown'}={}){
  profile=profile||path.join(os.homedir(),'.config/browser-workspace/chrome');
  dataDir=dataDir||path.join(os.homedir(),'.config/browser-workspace/auth-audit');
  const db=path.join(profile,'Default','Cookies');
  if(!fs.existsSync(db))throw Error('Chrome Cookie database not found; refusing to start Chrome or change profiles');
  fs.mkdirSync(dataDir,{recursive:true,mode:0o700});
  fs.chmodSync(dataDir,0o700);
  const lock=path.join(dataDir,'collector-node.lock');
  let fd;
  try{fd=fs.openSync(lock,fs.constants.O_CREAT|fs.constants.O_EXCL|fs.constants.O_WRONLY,0o600);fs.writeSync(fd,String(process.pid));}
  catch(error){throw new Error(`cookie audit already running: ${error.code}`);}
  try{
    const key=loadKey(path.join(dataDir,'audit.key'));
    const now=Math.floor(Date.now()/1000),current=collect(db,key);
    let previous={};try{previous=JSON.parse(fs.readFileSync(path.join(dataDir,'latest.json'),'utf8')).sites||{};}catch{}
    const diff=difference(previous,current);
    const summaries={},watched={};
    for(const [name,cookies] of Object.entries(current)){
      const values=Object.values(cookies),future=values.map(x=>x.expires_at).filter(x=>x!=null&&x>now);
      summaries[name]={count:values.length,expired:values.filter(x=>x.expires_at!=null&&x.expires_at<=now).length,
        session_cookies:values.filter(x=>!x.persistent).length,next_expiry_at:future.length?Math.min(...future):null,...diff[name]};
      if(WATCHED[name])watched[name]=Object.fromEntries(values.filter(x=>x.watched_name).map(x=>[x.watched_name,
        {expires_at:x.expires_at,updated_at:x.updated_at,created_at:x.created_at}]));
    }
    const event={schema:2,watched_cookie_metadata:watched,timestamp:now,utc:new Date(now*1000).toISOString(),
      profile,sites:summaries,observed_status:site?{[site]:status}:{},page_evidence:site?{[site]:pageEvidence}:{}};
    const eventFile=path.join(dataDir,'events.jsonl');const logfd=fs.openSync(eventFile,fs.constants.O_WRONLY|fs.constants.O_APPEND|fs.constants.O_CREAT,0o600);
    try{fs.writeSync(logfd,JSON.stringify(event)+'\n');fs.fsyncSync(logfd);}finally{fs.closeSync(logfd);}
    const temp=path.join(dataDir,`.latest-${process.pid}.tmp`);
    try{secureWrite(temp,JSON.stringify({timestamp:now,sites:current}));fs.renameSync(temp,path.join(dataDir,'latest.json'));}
    finally{if(fs.existsSync(temp))fs.unlinkSync(temp);}
    return event;
  }finally{fs.closeSync(fd);try{fs.unlinkSync(lock);}catch{}}
}
function args(argv){const result={};for(let i=0;i<argv.length;i++){
  if(!argv[i].startsWith('--'))throw Error(`Invalid option ${argv[i]}`);
  if(!argv[i+1]||argv[i+1].startsWith('--'))throw Error(`Missing value for ${argv[i]}`);
  result[argv[i].slice(2)]=argv[++i];
}return result;}
export function main(argv=process.argv.slice(2)){
  const opt=args(argv),site=opt.site,status=opt.status||'unknown',pageEvidence=opt['page-evidence']||'unknown';
  if(site&&!SITES[site])throw Error('Invalid site');
  if(!['unknown','logged_in','login_required','page_error'].includes(status))throw Error('Invalid status');
  if(!['backend_visible','login_redirect','page_load_failed','feed_only','unknown'].includes(pageEvidence))throw Error('Invalid page evidence');
  console.log(JSON.stringify(sample({profile:opt.profile,dataDir:opt['data-dir'],site,status,pageEvidence})));
}
if(process.argv[1]===fileURLToPath(import.meta.url)){
  try{main();}catch(error){console.error(error.message);process.exitCode=1;}
}
