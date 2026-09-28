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

  // Chrome can assign a newly-created tab to the rightmost tab group only
  // after tabs.onCreated fires. Re-read the live tab shortly afterward so a
  // normal "+" tab cannot become an accidental Browser Workspace lease.
  setTimeout(async () => {
    try {
      const current = await chrome.tabs.get(tab.id);
      await manager.inheritWorkspaceForCreatedTab(current);
    } catch (error) {
      // The tab may already be gone; only surface real Chrome/API failures.
      if (!/No tab with id|Invalid tab ID/i.test(String(error?.message || error))) {
        console.warn("Browser Workspace failed delayed created-tab reconciliation", error);
      }
    }
  }, 150);
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
