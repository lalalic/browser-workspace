#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {ensureDaemon,request,SOCKET} from './node-daemon.mjs';
const ROOT=path.dirname(fileURLToPath(import.meta.url));
const PLATFORMS=process.env.WEBHELM_PLATFORM_DIR||path.join(ROOT,'..','skills','webhelm','platforms');
const out=x=>console.log(JSON.stringify(x));
function help(){console.log(`webhelm (Node pilot)\n\nUsage:\n  webhelm status\n  webhelm session start [--url URL] [--workspace NAME]\n  webhelm session list\n  webhelm session exec SESSION_ID [--code-file FILE]  # JavaScript from stdin/file\n  webhelm session stop SESSION_ID|--all\n  webhelm platform list|profile NAME|run NAME ACTION [--session-id ID] [--config FILE]\n`)}
function arg(a,name){const i=a.indexOf(name);return i<0?null:a[i+1]}
async function main(){const a=process.argv.slice(2),group=a[0];if(!group||['-h','--help'].includes(group)){help();return}
 if(group==='status'){const d=await ensureDaemon();out({version:'1.0.0-node-pilot',platform_dir:PLATFORMS,root:ROOT,cli:path.join(ROOT,'cli.mjs'),admin_helper:path.join(ROOT,'admin.mjs'),managed_chrome:d.managed_chrome,daemon:{running:true,pid:d.pid,session_count:d.session_count,socket:SOCKET}});return}
 if(group==='session'){const cmd=a[1];if(cmd==='start'){out(await request({op:'start',url:arg(a,'--url'),workspace:arg(a,'--workspace')}));return}if(cmd==='list'){out(await request({op:'list'}));return}if(cmd==='stop'){out(await request(a.includes('--all')?{op:'stop-all'}:{op:'stop',session_id:a[2]}));return}if(cmd==='exec'){const sid=a[2],file=arg(a,'--code-file');const code=file?fs.readFileSync(file,'utf8'):fs.readFileSync(0,'utf8');const r=await request({op:'exec',session_id:sid,code});out(r);if(!r.ok)process.exitCode=1;return}}
 if(group==='platform'){const cmd=a[1];if(cmd==='list'){const names=fs.readdirSync(PLATFORMS,{withFileTypes:true}).filter(x=>x.isDirectory()).map(x=>x.name).sort();out({platforms:names.map(name=>({name,status:'disabled_node_migration',reason:'Python action has not been migrated to the Node runtime',actions:readActions(name)}))});return}if(cmd==='profile'){const name=a[2];const f=path.join(PLATFORMS,name,'manifest.yaml');if(!fs.existsSync(f))throw Error(`unknown platform: ${name}`);out({platform:name,status:'disabled_node_migration',manifest:fs.readFileSync(f,'utf8'),actions:readActions(name)});return}if(cmd==='run'){throw Error('platform actions are disabled in the Node pilot until their Python implementations and runtime dependencies are migrated; use the existing live Python deployment for platform workflows') }}
 throw Error(`unknown command: ${a.join(' ')}`)}
function readActions(name){const f=path.join(PLATFORMS,name,'manifest.yaml');if(!fs.existsSync(f))return[];const text=fs.readFileSync(f,'utf8'),start=text.indexOf('\nactions:');if(start<0)return[];return [...text.slice(start).split('\n').slice(1).filter(l=>/^\s{2}[\w-]+:\s*["']?actions\//.test(l)).map(l=>l.trim().match(/^([\w-]+):\s*["']?([^"']+)/).slice(1))].map(([action,file])=>({action,file,enabled:false,reason:'Node migration pending'}))}
main().catch(e=>{console.error(JSON.stringify({error:e.message}));process.exitCode=1});
