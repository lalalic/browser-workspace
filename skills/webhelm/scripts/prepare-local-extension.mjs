import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
const [source,root] = process.argv.slice(2);
if(!source||!root)throw Error('Extension source and output directories are required');
const expectedId='kkkpgmhpoeceojalkpfdidffdfnlgdog';
const hash={
  'manifest.json':'37287e1df6f187a5e4e686b7b26f943cc894df1f967a191fc917910ecdaa111b',
  'service-worker.mjs':'aff0a4c4724d1427c5a7a121246144a7ef45b1c2d2989fef59911bf297b1422c',
  'workspace-manager.mjs':'bc3cbe3fd3816933411275fc5349b612b92668560b1617db4b68e683452ad851',
  'workspace.html':'92f7a274a99e6185d047ae3dde57273394c6871fa528735e5c17ebbec9b5164a',
  'workspace-page.mjs':'b6a8a32988fde213e0028364332442dfb654f48288d7c73e2407440a6b54181d',
};
const files=Object.keys(hash);
const actual=fs.readdirSync(source).sort();
if(JSON.stringify(actual)!==JSON.stringify(files.sort()))throw Error('Unexpected or missing extension files');
for(const filename of files){
  const bytes=fs.readFileSync(path.join(source,filename));
  if(crypto.createHash('sha256').update(bytes).digest('hex')!==hash[filename])throw Error(`Extension integrity mismatch: ${filename}`);
}
const manifest=JSON.parse(fs.readFileSync(path.join(source,'manifest.json'),'utf8'));
const digest=crypto.createHash('sha256').update(Buffer.from(manifest.key,'base64')).digest('hex').slice(0,32);
const id=[...digest].map(n=>String.fromCharCode(97+parseInt(n,16))).join('');
if(id!==expectedId)throw Error('Extension public key identity mismatch');
if(manifest.version!=='0.3.1'||'update_url'in manifest)throw Error('Extension version mismatch');
fs.mkdirSync(root,{recursive:true});
const dest=path.join(root,`browser-workspace-${manifest.version}`);
function identical(dir){return fs.existsSync(dir)&&files.every(f=>
  fs.existsSync(path.join(dir,f))&&fs.readFileSync(path.join(dir,f)).equals(fs.readFileSync(path.join(source,f))))&&
  JSON.stringify(fs.readdirSync(dir).sort())===JSON.stringify([...files].sort());}
if(fs.existsSync(dest)){
  if(!identical(dest))throw Error(`Existing staged extension differs: ${dest}`);
}else {
  const stage=fs.mkdtempSync(path.join(root,'.webhelm-extension-'));
  try{
    for(const file of files)fs.copyFileSync(path.join(source,file),path.join(stage,file));
    fs.renameSync(stage,dest);
  }finally{if(fs.existsSync(stage))fs.rmSync(stage,{recursive:true,force:true});}
}
console.log(`Verified local Browser Workspace extension ${manifest.version}`);
console.log(`Extension ID: ${expectedId}`);
console.log(`Unpacked directory: ${dest}`);
console.log('In the managed Chrome window, open chrome://extensions, enable Developer mode,');
console.log('choose Load unpacked and select the directory above. No Chrome changes were made.');
