import net from 'node:net';
import os from 'node:os';
import path from 'node:path';
const socketPath=()=>process.env.WEBHELM_SOCKET||path.join(process.env.WEBHELM_RUNTIME_DIR||path.join(os.homedir(),'.config/browser-workspace/runtime'),'session-node.sock');
function request(payload){return new Promise((resolve,reject)=>{const s=net.createConnection(socketPath());let buf='';s.setEncoding('utf8');s.on('connect',()=>s.write(JSON.stringify(payload)+'\n'));s.on('data',d=>{buf+=d;if(!buf.includes('\n'))return;s.end();try{const v=JSON.parse(buf);v.error?reject(Error(v.error)):resolve(v)}catch(e){reject(e)}});s.on('error',reject)})}
export async function ensureWorkspace(name,size=5){if(typeof name!=='string'||!name.trim())throw TypeError('workspace name must be a non-empty string');if(!Number.isInteger(size)||size<1)throw TypeError('workspace size must be a positive integer');return request({op:'workspace-create',name:name.trim(),pool_size:size})}
export async function deleteWorkspace(name,{force=false}={}){if(typeof name!=='string'||!name.trim())throw TypeError('workspace name must be a non-empty string');return request({op:'workspace-delete',name:name.trim(),force:Boolean(force)})}
