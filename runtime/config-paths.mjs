import os from 'node:os';
import path from 'node:path';
import fs from 'node:fs';

export const CONFIG_ROOT = path.join(os.homedir(), '.config', 'webhelm');
export const LEGACY_ROOT = path.join(os.homedir(), '.config', 'browser-workspace');
export const PROFILE_DIR = path.join(CONFIG_ROOT, 'chrome');
export const RUNTIME_DIR = path.join(CONFIG_ROOT, 'runtime');

// Avoid starting a second FIFO dispatcher or empty Chrome profile against legacy data.
export function requireMigratedConfig() {
  if (fs.existsSync(path.join(LEGACY_ROOT, 'chrome')) && !fs.existsSync(PROFILE_DIR))
    throw Error(`Legacy Chrome profile exists at ${LEGACY_ROOT}. Stop old Chrome and WebHelm daemon, then run webhelm migrate.`);
}
