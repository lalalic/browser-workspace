import { WorkspaceManager } from "./workspace-manager.mjs";

const manager = new WorkspaceManager(chrome);

globalThis.browserWorkspaceManagerRpc = async (request) => {
  try {
    return { ok: true, result: await manager.rpc(request) };
  } catch (error) {
    return {
      ok: false,
      error: {
        message: error?.message || String(error),
        name: error?.name || "Error",
      },
    };
  }
};

chrome.runtime.onMessage.addListener((request, _sender, sendResponse) => {
  globalThis.browserWorkspaceManagerRpc(request).then(sendResponse);
  return true;
});
