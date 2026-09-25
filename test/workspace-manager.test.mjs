import assert from "node:assert/strict";
import test from "node:test";

import { WorkspaceManager } from "../extension/workspace-manager.mjs";

function fakeChrome() {
  let nextTabId = 1;
  let nextGroupId = 100;
  const tabs = new Map();
  const groups = new Map();
  const storage = {};

  const clone = (value) =>
    value === undefined ? undefined : JSON.parse(JSON.stringify(value));

  const api = {
    runtime: {
      getURL(path) {
        return `chrome-extension://test-extension/${path}`;
      },
    },
    storage: {
      local: {
        async get(key) {
          return { [key]: clone(storage[key]) };
        },
        async set(values) {
          Object.assign(storage, clone(values));
        },
      },
    },
    tabs: {
      async query(query = {}) {
        let values = [...tabs.values()];
        if (Number.isInteger(query.groupId)) {
          values = values.filter((tab) => tab.groupId === query.groupId);
        }
        return values.map(clone);
      },
      async create(options) {
        const tab = {
          id: nextTabId++,
          groupId: -1,
          title: "Browser Workspace",
          url: options.url || "about:blank",
          active: Boolean(options.active),
          ...(Number.isInteger(options.openerTabId) ? { openerTabId: options.openerTabId } : {}),
        };
        tabs.set(tab.id, tab);
        return clone(tab);
      },
      async group(options) {
        const groupId = Number.isInteger(options.groupId)
          ? options.groupId
          : nextGroupId++;
        if (!groups.has(groupId)) {
          groups.set(groupId, {
            id: groupId,
            title: "",
            collapsed: false,
          });
        }
        for (const tabId of options.tabIds || []) {
          tabs.get(tabId).groupId = groupId;
        }
        return groupId;
      },
      async update(tabId, options) {
        const tab = tabs.get(tabId);
        if (!tab) throw new Error(`Unknown tab ${tabId}`);
        if (options.url !== undefined) tab.url = options.url;
        if (options.active !== undefined) tab.active = Boolean(options.active);
        return clone(tab);
      },
      async remove(tabIds) {
        for (const tabId of Array.isArray(tabIds) ? tabIds : [tabIds]) {
          tabs.delete(tabId);
        }
      },
    },
    tabGroups: {
      async query() {
        return [...groups.values()].map(clone);
      },
      async update(groupId, options) {
        const group = groups.get(groupId) || {
          id: groupId,
          title: "",
          collapsed: false,
        };
        Object.assign(group, options);
        groups.set(groupId, group);
        return clone(group);
      },
    },
    __moveGroup(oldGroupId, newGroupId) {
      const group = groups.get(oldGroupId);
      if (!group) throw new Error("group missing");
      groups.delete(oldGroupId);
      groups.set(newGroupId, { ...group, id: newGroupId });
      for (const tab of tabs.values()) {
        if (tab.groupId === oldGroupId) tab.groupId = newGroupId;
      }
    },
    __duplicateGroupTitle(title) {
      groups.set(nextGroupId++, {
        id: nextGroupId,
        title,
        collapsed: true,
      });
    },
  };

  return api;
}

test("pool size is exactly the Chrome group tab count", async () => {
  const chrome = fakeChrome();
  const manager = new WorkspaceManager(chrome);

  const state = await manager.create("MDB", 4);
  assert.equal(state.poolSize, 4);
  assert.equal(state.tabIds.length, 4);
  assert.equal(state.idleTabIds.length, 4);
  assert.equal(state.leasedTabIds.length, 0);

  const leased = await manager.acquire("MDB", "https://example.com/");
  assert.ok(state.tabIds.includes(leased.tabId));

  const active = await manager.status("MDB");
  assert.equal(active.tabIds.length, 4);
  assert.equal(active.idleTabIds.length, 3);
  assert.equal(active.leasedTabIds.length, 1);

  await manager.release("MDB", leased.tabId);
  const released = await manager.status("MDB");
  assert.equal(released.tabIds.length, 4);
  assert.equal(released.idleTabIds.length, 4);
});

test("multiple workspaces have independent exact pool sizes", async () => {
  const chrome = fakeChrome();
  const manager = new WorkspaceManager(chrome);

  const alpha = await manager.create("Alpha", 2);
  const beta = await manager.create("Beta", 3);

  assert.equal(alpha.tabIds.length, 2);
  assert.equal(beta.tabIds.length, 3);
  assert.notEqual(alpha.groupId, beta.groupId);

  const resized = await manager.resize("Beta", 1);
  assert.equal(resized.poolSize, 1);
  assert.equal(resized.tabIds.length, 1);
});

test("workspace identity survives groupId changes via unique group title", async () => {
  const chrome = fakeChrome();
  const manager = new WorkspaceManager(chrome);

  const before = await manager.create("Research", 2);
  chrome.__moveGroup(before.groupId, 777);

  const after = await manager.status("Research");
  assert.equal(after.initialized, true);
  assert.equal(after.groupId, 777);
  assert.equal(after.tabIds.length, 2);
});

test("duplicate workspace titles fail closed", async () => {
  const chrome = fakeChrome();
  const manager = new WorkspaceManager(chrome);

  await manager.create("Research", 2);
  chrome.__duplicateGroupTitle("Research");

  await assert.rejects(
    () => manager.status("Research"),
    /ambiguous/,
  );
});



test("workspace can lease a chrome-extension page inside the existing group", async () => {
  const chrome = fakeChrome();
  const manager = new WorkspaceManager(chrome);

  const state = await manager.create("Harness", 5);
  const leased = await manager.acquire(
    "Harness",
    "chrome-extension://teammate/main.html",
  );

  assert.equal(leased.groupId, state.groupId);
  const after = await manager.status("Harness");
  assert.equal(after.tabIds.length, 5);
  assert.ok(after.tabs.some((tab) => tab.url === "chrome-extension://teammate/main.html"));
});

test("workspace still rejects unsupported URL schemes", async () => {
  const chrome = fakeChrome();
  const manager = new WorkspaceManager(chrome);

  await manager.create("Harness", 2);
  await assert.rejects(
    () => manager.acquire("Harness", "file:///tmp/test.html"),
    /http\(s\) or chrome-extension/,
  );
});

test("child tab inherits workspace group and consumes an idle pool slot", async () => {
  const chrome = fakeChrome();
  const manager = new WorkspaceManager(chrome);

  const state = await manager.create("Harness", 5);
  const leased = await manager.acquire("Harness", "https://teams.cloud.microsoft/");
  const child = await chrome.tabs.create({
    url: "chrome-extension://teammate/main.html",
    active: false,
    openerTabId: leased.tabId,
  });

  const inherited = await manager.inheritWorkspaceForCreatedTab(child);
  assert.deepEqual(inherited, {
    workspace: "Harness",
    groupId: state.groupId,
    tabId: child.id,
    inheritedFromTabId: leased.tabId,
    workspaceAncestorTabId: leased.tabId,
  });

  const after = await manager.status("Harness");
  assert.equal(after.tabIds.length, 5);
  assert.ok(after.tabIds.includes(child.id));
  assert.equal(after.idleTabIds.length, 3);
  assert.equal(after.leasedTabIds.length, 2);
});


test("ordinary web child tab inherits workspace from its opener", async () => {
  const chrome = fakeChrome();
  const manager = new WorkspaceManager(chrome);

  const state = await manager.create("Harness", 5);
  const leased = await manager.acquire("Harness", "chrome-extension://teammate/main.html");
  const teams = await chrome.tabs.create({
    url: "https://teams.cloud.microsoft/",
    openerTabId: leased.tabId,
  });

  assert.deepEqual(await manager.inheritWorkspaceForCreatedTab(teams), {
    workspace: "Harness",
    groupId: state.groupId,
    tabId: teams.id,
    inheritedFromTabId: leased.tabId,
    workspaceAncestorTabId: leased.tabId,
  });
  const after = await manager.status("Harness");
  assert.ok(after.tabIds.includes(teams.id));
});

test("grandchild inherits workspace through opener ancestry", async () => {
  const chrome = fakeChrome();
  const manager = new WorkspaceManager(chrome);

  const state = await manager.create("Harness", 5);
  const root = await manager.acquire("Harness", "https://example.com/root");
  const child = await chrome.tabs.create({
    url: "https://example.com/child",
    openerTabId: root.tabId,
  });
  const grandchild = await chrome.tabs.create({
    url: "https://example.com/grandchild",
    openerTabId: child.id,
  });

  const inherited = await manager.inheritWorkspaceForCreatedTab(grandchild);
  assert.deepEqual(inherited, {
    workspace: "Harness",
    groupId: state.groupId,
    tabId: grandchild.id,
    inheritedFromTabId: child.id,
    workspaceAncestorTabId: root.tabId,
  });
  const after = await manager.status("Harness");
  assert.ok(after.tabIds.includes(grandchild.id));
});

test("tab opened outside a workspace is not adopted", async () => {
  const chrome = fakeChrome();
  const manager = new WorkspaceManager(chrome);

  await manager.create("Harness", 5);
  const outside = await chrome.tabs.create({ url: "https://example.com/" });
  const child = await chrome.tabs.create({
    url: "chrome-extension://teammate/setup.html",
    openerTabId: outside.id,
  });

  assert.equal(await manager.inheritWorkspaceForCreatedTab(child), null);
  assert.equal(child.groupId, -1);
});
