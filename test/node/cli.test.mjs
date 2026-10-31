import test from 'node:test';
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
const cli=fileURLToPath(new URL('../../src/cli.mjs',import.meta.url));

test('platform inventory clearly disables unmigrated Python actions',()=>{
 const run=spawnSync(process.execPath,[cli,'platform','list'],{encoding:'utf8'});
 assert.equal(run.status,0,run.stderr);
 const result=JSON.parse(run.stdout);
 assert.ok(result.platforms.length>0);
 assert.ok(result.platforms.every(p=>p.status==='disabled_node_migration'));
 assert.ok(result.platforms.flatMap(p=>p.actions).every(a=>!a.enabled));
});

test('platform run refuses actions that have no Node implementation',()=>{
 const run=spawnSync(process.execPath,[cli,'platform','run','chatgpt','new-turn'],{encoding:'utf8'});
 assert.equal(run.status,1);
 assert.match(run.stderr,/disabled in the Node pilot/);
});
