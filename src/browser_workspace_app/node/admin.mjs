import net from "node:net";
import os from "node:os";
import path from "node:path";

function socketPath() {
  if (process.env.BROWSER_WORKSPACE_TEST_MODE === "1" && process.env.BROWSER_WORKSPACE_SESSION_SOCKET) return process.env.BROWSER_WORKSPACE_SESSION_SOCKET;
  return path.join(os.homedir(), ".config", "browser-workspace", "runtime", "session.sock");
}

function request(payload) {
  return new Promise((resolve, reject) => {
    const socket = net.createConnection({ path: socketPath() });
    let buffer = "";
    let settled = false;
    const fail = (error) => { if (!settled) { settled = true; reject(error); } };
    socket.setEncoding("utf8");
    socket.on("connect", () => socket.write(`${JSON.stringify(payload)}\n`));
    socket.on("data", chunk => {
      buffer += chunk;
      const newline = buffer.indexOf("\n");
      if (newline < 0 || settled) return;
      settled = true;
      socket.end();
      try {
        const result = JSON.parse(buffer.slice(0, newline));
        if (result && result.error) reject(new Error(result.error));
        else resolve(result);
      } catch (error) { reject(error); }
    });
    socket.on("error", fail);
    socket.on("end", () => { if (!settled) fail(new Error("browser-workspace daemon closed without a response")); });
  });
}

export async function ensureWorkspace(name, size = 5) {
  if (typeof name !== "string" || !name.trim()) throw new TypeError("workspace name must be a non-empty string");
  if (!Number.isInteger(size) || size < 1) throw new TypeError("workspace size must be a positive integer");
  return request({ op: "workspace-create", name: name.trim(), pool_size: size });
}

export async function deleteWorkspace(name, { force = false } = {}) {
  if (typeof name !== "string" || !name.trim()) throw new TypeError("workspace name must be a non-empty string");
  return request({ op: "workspace-delete", name: name.trim(), force: Boolean(force) });
}
