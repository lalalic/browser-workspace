#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { randomUUID } from 'node:crypto';
import { ensureDaemon, request, SOCKET } from './node-daemon.mjs';
import { PLATFORMS, listPlatforms, platformProfile, actionPath, validateConfig } from './platforms.mjs';

const ROOT = path.dirname(fileURLToPath(import.meta.url));
const emit = value => console.log(JSON.stringify(value));
const arg = (items, name) => {
  const i = items.indexOf(name);
  return i === -1 ? undefined : items[i + 1];
};
const has = (items, name) => items.includes(name);

function help() {
  console.log(`webhelm — browser automation through one Node.js runtime

Usage:
  webhelm status
  webhelm capacity [--workspace NAME]
  webhelm session start [--url URL]
  webhelm session list
  webhelm session exec SESSION_ID [--code-file FILE]   # JavaScript
  webhelm session stop SESSION_ID|--all
  webhelm platform list
  webhelm platform profile PLATFORM
  webhelm platform source PLATFORM ACTION
  webhelm platform run PLATFORM ACTION [--session-id ID | --auto-session] [--config FILE] [--mode async|sync]

Agent workflows should keep their session_id across browser actions and always stop owned sessions.
`);
}

function loadConfig(args) {
  const file = arg(args, '--config');
  if (!file) return {};
  const cfg = JSON.parse(fs.readFileSync(file, 'utf8'));
  if (!cfg || typeof cfg !== 'object' || Array.isArray(cfg)) throw Error('platform config must be a JSON object');
  return cfg;
}

function validateMode(platform, action, args, config) {
  const isNewTurn = platform === 'chatgpt' && action === 'new-turn';
  const override = arg(args, '--mode');
  if (!isNewTurn && override !== undefined) throw Error('--mode is supported only for chatgpt/new-turn');
  if (!isNewTurn) return null;
  if ('sync' in config) throw Error('legacy sync is not supported; use mode: async or sync');
  if (override !== undefined && 'mode' in config && override !== config.mode) throw Error('--mode conflicts with the new-turn config mode');
  const mode = override ?? config.mode ?? 'async';
  if (typeof mode !== 'string' || !['async', 'sync'].includes(mode)) throw Error('mode must be exactly async or sync');
  if (mode === 'sync' && config.mergeable !== undefined && config.mergeable !== false) {
    throw Error('mergeable is only supported in async mode');
  }
  return mode;
}

async function runPlatform(args) {
  const platform = args[2], action = args[3]?.replaceAll('_', '-');
  if (!platform || !action) throw Error('platform run requires PLATFORM ACTION');
  actionPath(platform, action);
  const config = loadConfig(args);
  const mode = validateMode(platform, action, args, config);
  const sid = arg(args, '--session-id');
  const auto = has(args, '--auto-session');
  validateConfig(platform, action, config);
  if (sid && auto) throw Error('--session-id and --auto-session are mutually exclusive');
  if (platform === 'chatgpt' && action === 'new-turn' && mode === 'async') {
    if (sid || auto) throw Error('async new-turn cannot use browser session options');
    if (!config.thread_id || !config.message) throw Error('thread_id and message required');
    if (typeof config.mergeable !== 'undefined' && typeof config.mergeable !== 'boolean') throw Error('mergeable must be a boolean');
    const receipt = await request({op:'chatgpt-new-turn-enqueue', config: {...config, idempotency_key: config.idempotency_key || randomUUID(), mode}});
    if (!receipt.ok || !receipt.queue_id || receipt.thread_id !== String(config.thread_id)) throw Error('ChatGPT queue returned an invalid acceptance receipt');
    const project = config.project_id || null;
    const prefix = project ? `/g/${encodeURIComponent(project)}` : '';
    return {
      platform, action, session_mode: 'durable_queue', self_heal_capable: false,
      result: {ok:true, status:'submitted', mode:'new-turn', project_id:project,
        thread_id:String(config.thread_id), thread_url:`https://chatgpt.com${prefix}/c/${encodeURIComponent(config.thread_id)}`,
        verified_by:'durable-queue', user_message_id:null, queue_id: receipt.queue_id, state:receipt.state},
    };
  }
  if (mode === 'sync' && (!sid || auto)) throw Error('sync new-turn requires a caller-owned --session-id');
  if (!sid && !auto) throw Error('platform run requires --session-id; use --auto-session only for one-shot actions');
  return request({op:'platform-run', platform, action, config: {...config, ...(mode ? {mode} : {})},
    session_id:sid, auto_session:auto, url:arg(args, '--url')});
}

async function main(args = process.argv.slice(2)) {
  const [group, command] = args;
  if (!group || ['--help', '-h', 'help'].includes(group) || has(args, '--help') || has(args, '-h')) return help();
  if (group === 'status') {
    const daemon = await ensureDaemon();
    return emit({version:'1.0.0', platform_dir:PLATFORMS, root:ROOT,
      cli:fileURLToPath(import.meta.url), admin_helper:path.join(ROOT, 'admin.mjs'),
      managed_chrome:daemon.managed_chrome,
      daemon:{running:true, pid:daemon.pid, session_count:daemon.session_count, queue_paused:daemon.queue_paused, socket:SOCKET}});
  }
  if (group === 'capacity') return emit(await request({op:'capacity',workspace:arg(args,'--workspace')}));
  if (group === 'session') {
    if (command === 'start') return emit(await request({op:'start', workspace:arg(args,'--workspace'), url:arg(args,'--url')}));
    if (command === 'list') return emit(await request({op:'list'}));
    if (command === 'stop') return emit(await request(has(args,'--all') ? {op:'stop-all'} : {op:'stop',session_id:args[2]}));
    if (command === 'exec') {
      if (!args[2]) throw Error('session exec requires SESSION_ID');
      const file = arg(args, '--code-file');
      const code = file ? fs.readFileSync(file, 'utf8') : fs.readFileSync(0, 'utf8');
      const result = await request({op:'exec', session_id:args[2], code});
      emit(result);
      if (!result.ok) process.exitCode = 1;
      return;
    }
  }
  if (group === 'platform') {
    if (command === 'list') return emit(listPlatforms());
    if (command === 'profile') return emit(platformProfile(args[2]));
    if (command === 'source') return console.log(fs.readFileSync(actionPath(args[2],args[3]), 'utf8'));
    if (command === 'run') {
      const result = await runPlatform(args);
      emit(result);
      if (result?.result?.ok === false) process.exitCode = 1;
      return;
    }
  }
  throw Error(`unknown command: ${args.join(' ')}`);
}

main().catch(error => { console.error(JSON.stringify({error:error.message})); process.exitCode=1; });
