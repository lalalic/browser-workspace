import { WorkspaceManager } from "./workspace-manager.mjs";

const manager = new WorkspaceManager(chrome);
const RECLAIM_ALARM = "browser-workspace.reclaim-stale";

chrome.alarms.create(RECLAIM_ALARM, { periodInMinutes: 5 });

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

chrome.tabs.onCreated.addListener((tab) => {
  manager.inheritWorkspaceForCreatedTab(tab).catch((error) => {
    console.warn("Browser Workspace failed to inherit child tab group", error);
  });
});

chrome.webNavigation.onCreatedNavigationTarget.addListener((details) => {
  manager.inheritNavigationTarget(details).catch((error) => {
    console.warn("Browser Workspace failed to inherit navigation target", error);
  });
});

chrome.tabs.onUpdated.addListener((_tabId, changeInfo, tab) => {
  if (!Object.prototype.hasOwnProperty.call(changeInfo, "groupId")) return;
  manager.inheritWorkspaceForCreatedTab(tab).catch((error) => {
    console.warn("Browser Workspace failed to reconcile tab group ownership", error);
  });
});

chrome.tabs.onActivated.addListener((activeInfo) => {
  manager.noteActivatedTab(activeInfo).catch((error) => {
    console.warn("Browser Workspace failed to record active tab context", error);
  });
});

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name !== RECLAIM_ALARM) return;
  manager.reclaimStaleTabs().catch((error) => {
    console.warn("Browser Workspace failed to reclaim stale tabs", error);
  });
});
