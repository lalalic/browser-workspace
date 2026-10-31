import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import net from 'node:net';
import { CONFIG_ROOT, LEGACY_ROOT } from './config-paths.mjs';

function liveSocket(socketPath) {
  return new Promise(resolve => {
    const socket = net.createConnection(socketPath);
    const finish = result => { socket.destroy(); resolve(result); };
    socket.once('connect', () => finish(true));
    socket.once('error', () => finish(false));
    socket.setTimeout(1200, () => finish(true)); // Fail closed if probing hangs.
  });
}

export async function migrateConfig({ legacyRoot = LEGACY_ROOT, configRoot = CONFIG_ROOT,
  processList = () => execFileSync('ps', ['-axo', 'command='], { encoding: 'utf8' }),
  socketCheck = liveSocket } = {}) {
  const legacy = path.resolve(legacyRoot);
  const target = path.resolve(configRoot);
  if (legacy === target) throw Error('Legacy and new config paths are identical');
  let oldStat;
  try { oldStat = fs.lstatSync(legacy); }
  catch (e) { if (e.code === 'ENOENT') return { status: 'not_needed', config_root: target }; throw e; }
  if (oldStat.isSymbolicLink()) {
    if (fs.existsSync(target) && fs.realpathSync(legacy) === fs.realpathSync(target))
      return { status: 'already_migrated', config_root: target, compatibility_symlink: legacy };
    throw Error(`Legacy path is a different symlink: ${legacy}`);
  }
  if (!oldStat.isDirectory()) throw Error(`Legacy path is not a directory: ${legacy}`);
  if (fs.existsSync(target)) throw Error(`Target already exists; refusing to overwrite: ${target}`);
  const running = processList().split('\n').filter(line =>
    line.includes(`--user-data-dir=${path.join(legacy, 'chrome')}`) ||
    (line.includes('node-daemon.mjs daemon') && !line.includes('migrate.mjs')));
  if (running.length) throw Error('Chrome or WebHelm daemon is still running; stop Sessions, daemon and Chrome before migration');
  const socket = path.join(legacy, 'runtime', 'session-node.sock');
  if (fs.existsSync(socket) && await socketCheck(socket))
    throw Error('Legacy daemon socket is active; refusing migration');
  fs.renameSync(legacy, target); // Same-volume atomic directory move; preserve Chrome data and FIFO WAL.
  try { fs.symlinkSync(target, legacy, 'dir'); }
  catch (error) {
    fs.renameSync(target, legacy);
    throw error;
  }
  return { status: 'migrated', config_root: target, compatibility_symlink: legacy };
}
