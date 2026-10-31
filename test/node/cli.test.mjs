import test from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
const cli=fileURLToPath(new URL('../../skills/webhelm/runtime/cli.mjs', import.meta.url));
const run=(...args)=>spawnSync(process.execPath,[cli,...args],{encoding:'utf8',timeout:10000});

test('all eleven platform manifests are discoverable through the Node CLI',()=>{
  const result=run('platform','list');
  assert.equal(result.status,0,result.stderr);
  const platforms=JSON.parse(result.stdout);
  assert.equal(platforms.length,11);
  assert.ok(platforms.includes('chatgpt'));
  assert.ok(platforms.includes('z'));
});

test('platform profiles and source are native JS with previous public JSON contract',()=>{
  const profile=run('platform','profile','z');
  assert.equal(profile.status,0,profile.stderr);
  assert.equal(JSON.parse(profile.stdout).platform,'z');
  const source=run('platform','source','z','new-turn');
  assert.equal(source.status,0,source.stderr);
  assert.match(source.stdout,/export default async function/);
});

test('invalid ChatGPT queue requests fail before any browser action',()=>{
  const result=run('platform','run','chatgpt','new-turn');
  assert.equal(result.status,1);
  assert.match(result.stderr,/thread_id and message required/);
});
