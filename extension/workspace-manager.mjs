const STORAGE_KEY = "browserWorkspaceManager.v1";
const MIN_POOL_SIZE = 1;
const MAX_POOL_SIZE = 64;

export function normalizeWorkspaceName(value) {
  const name = String(value || "").trim();
  if (!name) throw new Error("Workspace name is required");
  if (name.length > 80) throw new Error("Workspace name must be at most 80 characters");
  return name;
}

export function normalizePoolSize(value, fallback = 8) {
  const number = Number(value ?? fallback);
  if (!Number.isInteger(number) || number < MIN_POOL_SIZE || number > MAX_POOL_SIZE) {
    throw new Error(`Pool size must be an integer between ${MIN_POOL_SIZE} and ${MAX_POOL_SIZE}`);
  }
  return number;
}

function queryString(workspace, slot) {
  return new URLSearchParams({ workspace, role: "idle", slot: String(slot) }).toString();
}

export class WorkspaceManager {
  constructor(chromeApi) {
    this.chrome = chromeApi;
  }

  idleUrl(workspace, slot) {
    return this.chrome.runtime.getURL(`workspace.html?${queryString(workspace, slot)}`);
  }

  parseManagedUrl(url) {
    try {
      const parsed = new URL(url);
      const own = new URL(this.chrome.runtime.getURL("workspace.html"));
      if (parsed.origin !== own.origin || parsed.pathname !== own.pathname) return null;
      return {
        workspace: parsed.searchParams.get("workspace") || "",
        role: parsed.searchParams.get("role") || "",
        slot: parsed.searchParams.get("slot") || "",
      };
    } catch {
      return null;
    }
  }

  async loadConfig() {
    const stored = (await this.chrome.storage.local.get(STORAGE_KEY))[STORAGE_KEY];
    return stored && typeof stored === "object" ? stored : { workspaces: {} };
  }

  async saveConfig(config) {
    await this.chrome.storage.local.set({ [STORAGE_KEY]: config });
  }

  async configuredWorkspace(name) {
    const config = await this.loadConfig();
    return { config, entry: config.workspaces[name] || null };
  }

  async setPoolSize(name, poolSize) {
    const { config, entry } = await this.configuredWorkspace(name);
    config.workspaces[name] = { ...(entry || {}), poolSize };
    await this.saveConfig(config);
  }

  async removeConfig(name) {
    const config = await this.loadConfig();
    delete config.workspaces[name];
    await this.saveConfig(config);
  }

  async workspaceGroup(name) {
    const groups = await this.chrome.tabGroups.query({});
    const matches = groups.filter((group) => group.title === name);
    if (matches.length > 1) {
      throw new Error(`Workspace ${name} is ambiguous: ${matches.length} groups have that title`);
    }
    return matches[0] || null;
  }

  async groupTabs(groupId) {
    if (!Number.isInteger(groupId) || groupId < 0) return [];
    return await this.chrome.tabs.query({ groupId });
  }

  async inheritWorkspaceForCreatedTab(tab) {
    const tabId = Number(tab?.id);
    const openerTabId = Number(tab?.openerTabId);
    if (!Number.isInteger(tabId) || !Number.isInteger(openerTabId)) return null;

    const allTabs = await this.chrome.tabs.query({});
    const tabsById = new Map(allTabs.map((candidate) => [candidate.id, candidate]));
    const groups = await this.chrome.tabGroups.query({});
    const groupsById = new Map(groups.map((candidate) => [candidate.id, candidate]));

    let ancestor = tabsById.get(openerTabId);
    const visited = new Set();
    let inherited = null;

    while (ancestor && !visited.has(ancestor.id)) {
      visited.add(ancestor.id);

      if (Number.isInteger(ancestor.groupId) && ancestor.groupId >= 0) {
        const group = groupsById.get(ancestor.groupId);
        if (group?.title) {
          const { entry } = await this.configuredWorkspace(group.title);
          if (entry) {
            inherited = { ancestor, group, entry };
            break;
          }
        }
      }

      const parentId = Number(ancestor.openerTabId);
      ancestor = Number.isInteger(parentId) ? tabsById.get(parentId) : null;
    }

    if (!inherited) return null;

    const { ancestor: workspaceAncestor, group, entry } = inherited;
    await this.chrome.tabs.group({ groupId: group.id, tabIds: [tabId] });

    const tabs = await this.groupTabs(group.id);
    if (tabs.length > entry.poolSize) {
      const { idle } = this.classify(group.title, tabs);
      const removable = idle.find((candidate) => candidate.id !== tabId);
      if (removable) await this.chrome.tabs.remove(removable.id);
    }

    await this.chrome.tabGroups.update(group.id, {
      title: group.title,
      collapsed: true,
    });

    return {
      workspace: group.title,
      groupId: group.id,
      tabId,
      inheritedFromTabId: openerTabId,
      workspaceAncestorTabId: workspaceAncestor.id,
    };
  }

  classify(name, tabs) {
    const idle = [];
    const leased = [];
    for (const tab of tabs) {
      const meta = this.parseManagedUrl(tab.url || "");
      if (meta?.workspace === name && ["idle", "marker"].includes(meta.role)) idle.push(tab);
      else leased.push(tab);
    }
    return { idle, leased };
  }

  async waitForIdleTab(tabId, workspace, timeoutMs = 3000) {
    const deadline = Date.now() + timeoutMs;
    for (;;) {
      const tabs = await this.chrome.tabs.query({});
      const tab = tabs.find((candidate) => candidate.id === tabId);
      const meta = this.parseManagedUrl(tab?.url || "");
      if (tab && meta?.workspace === workspace && meta.role === "idle") return tab;
      if (Date.now() >= deadline) {
        throw new Error(`Timed out waiting for workspace ${workspace} idle tab ${tabId}`);
      }
      await new Promise((resolve) => setTimeout(resolve, 25));
    }
  }

  async createGroup(name, poolSize) {
    const created = [];
    for (let slot = 0; slot < poolSize; slot += 1) {
      created.push(await this.chrome.tabs.create({ url: this.idleUrl(name, slot), active: false }));
    }
    const groupId = await this.chrome.tabs.group({ tabIds: created.map((tab) => tab.id) });
    await this.chrome.tabGroups.update(groupId, { title: name, collapsed: true });
    for (const tab of created) await this.waitForIdleTab(tab.id, name);
    return await this.status(name);
  }

  async ensureWorkspace(name, poolSize = null) {
    const normalizedName = normalizeWorkspaceName(name);
    const { entry } = await this.configuredWorkspace(normalizedName);
    const wanted = normalizePoolSize(poolSize, entry?.poolSize ?? 8);
    if (!entry || entry.poolSize !== wanted) await this.setPoolSize(normalizedName, wanted);

    const group = await this.workspaceGroup(normalizedName);
    if (!group) return await this.createGroup(normalizedName, wanted);

    await this.chrome.tabGroups.update(group.id, { title: normalizedName, collapsed: true });
    await this.reconcilePool(normalizedName, group.id, wanted);
    return await this.status(normalizedName);
  }

  async reconcilePool(name, groupId, poolSize) {
    const tabs = await this.groupTabs(groupId);
    const { idle } = this.classify(name, tabs);

    if (tabs.length < poolSize) {
      const added = [];
      for (let slot = tabs.length; slot < poolSize; slot += 1) {
        added.push(await this.chrome.tabs.create({ url: this.idleUrl(name, slot), active: false }));
      }
      if (added.length) {
        await this.chrome.tabs.group({ groupId, tabIds: added.map((tab) => tab.id) });
        for (const tab of added) await this.waitForIdleTab(tab.id, name);
      }
    } else if (tabs.length > poolSize && idle.length) {
      const removable = Math.min(idle.length, tabs.length - poolSize);
      await this.chrome.tabs.remove(idle.slice(0, removable).map((tab) => tab.id));
    }

    await this.chrome.tabGroups.update(groupId, { title: name, collapsed: true });
  }

  async status(name) {
    const normalizedName = normalizeWorkspaceName(name);
    const { entry } = await this.configuredWorkspace(normalizedName);
    if (!entry) return { name: normalizedName, initialized: false };

    const group = await this.workspaceGroup(normalizedName);
    if (!group) {
      return {
        name: normalizedName,
        initialized: false,
        poolSize: entry.poolSize,
        reason: "group-missing",
      };
    }

    const tabs = await this.groupTabs(group.id);
    const { idle, leased } = this.classify(normalizedName, tabs);
    return {
      name: normalizedName,
      initialized: true,
      groupId: group.id,
      poolSize: entry.poolSize,
      tabIds: tabs.map((tab) => tab.id),
      idleTabIds: idle.map((tab) => tab.id),
      leasedTabIds: leased.map((tab) => tab.id),
      tabs: tabs.map((tab) => ({
        tabId: tab.id,
        groupId: tab.groupId,
        title: tab.title || "",
        url: tab.url || "",
        active: Boolean(tab.active),
      })),
      collapsed: Boolean(group.collapsed),
    };
  }

  async list() {
    const config = await this.loadConfig();
    const result = [];
    for (const name of Object.keys(config.workspaces).sort()) {
      result.push(await this.status(name));
    }
    return { workspaces: result };
  }

  async ensure(name, defaultPoolSize = 8) {
    const normalizedName = normalizeWorkspaceName(name);
    const { entry } = await this.configuredWorkspace(normalizedName);
    if (entry) return await this.ensureWorkspace(normalizedName);
    return await this.ensureWorkspace(
      normalizedName,
      normalizePoolSize(defaultPoolSize),
    );
  }

  async create(name, poolSize = 8) {
    return await this.ensureWorkspace(name, normalizePoolSize(poolSize));
  }

  async resize(name, poolSize) {
    const normalizedName = normalizeWorkspaceName(name);
    const wanted = normalizePoolSize(poolSize);
    await this.setPoolSize(normalizedName, wanted);
    return await this.ensureWorkspace(normalizedName, wanted);
  }

  async acquire(name, url) {
    const normalizedName = normalizeWorkspaceName(name);
    const parsed = new URL(String(url || ""));
    if (!["http:", "https:", "chrome-extension:"].includes(parsed.protocol)) {
      throw new Error("Workspace acquire requires an http(s) or chrome-extension URL");
    }

    const ready = await this.ensureWorkspace(normalizedName);
    const tabs = await this.groupTabs(ready.groupId);
    const { idle } = this.classify(normalizedName, tabs);
    if (!idle.length) {
      throw new Error(`Workspace ${normalizedName} pool is exhausted at size ${ready.poolSize}`);
    }

    const tab = idle[0];
    const updated = await this.chrome.tabs.update(tab.id, { url: parsed.href, active: false });
    await this.chrome.tabGroups.update(ready.groupId, { title: normalizedName, collapsed: true });
    return {
      workspace: normalizedName,
      groupId: ready.groupId,
      tabId: updated.id,
      url: updated.url || parsed.href,
      active: Boolean(updated.active),
    };
  }

  async release(name, tabId) {
    const normalizedName = normalizeWorkspaceName(name);
    const ready = await this.ensureWorkspace(normalizedName);
    const wanted = Number(tabId);
    const tabs = await this.groupTabs(ready.groupId);
    if (!tabs.some((tab) => tab.id === wanted)) {
      throw new Error(`Tab ${wanted} is not owned by workspace ${normalizedName}`);
    }

    if (tabs.length > ready.poolSize) {
      await this.chrome.tabs.remove(wanted);
    } else {
      await this.chrome.tabs.update(wanted, {
        url: this.idleUrl(normalizedName, wanted),
        active: false,
      });
      await this.waitForIdleTab(wanted, normalizedName);
    }
    await this.chrome.tabGroups.update(ready.groupId, { title: normalizedName, collapsed: true });
    return { workspace: normalizedName, tabId: wanted, released: true };
  }

  async delete(name, force = false) {
    const normalizedName = normalizeWorkspaceName(name);
    const state = await this.status(normalizedName);
    if (!state.initialized) {
      await this.removeConfig(normalizedName);
      return { name: normalizedName, deleted: true };
    }
    if (state.leasedTabIds.length && !force) {
      throw new Error(`Workspace ${normalizedName} has ${state.leasedTabIds.length} leased tabs`);
    }

    const tabs = await this.groupTabs(state.groupId);
    if (tabs.length) await this.chrome.tabs.remove(tabs.map((tab) => tab.id));
    await this.removeConfig(normalizedName);
    return { name: normalizedName, deleted: true };
  }

  async rpc(request) {
    const method = String(request?.method || "");
    const args = request?.args || {};
    if (method === "workspace.create") return await this.create(args.name, args.poolSize);
    if (method === "workspace.ensure") return await this.ensure(args.name, args.poolSize);
    if (method === "workspace.status") return await this.status(args.name);
    if (method === "workspace.list") return await this.list();
    if (method === "workspace.acquire") return await this.acquire(args.name, args.url);
    if (method === "workspace.release") return await this.release(args.name, args.tabId);
    if (method === "workspace.resize") return await this.resize(args.name, args.poolSize);
    if (method === "workspace.delete") return await this.delete(args.name, Boolean(args.force));
    throw new Error(`Unknown workspace method: ${method}`);
  }
}
