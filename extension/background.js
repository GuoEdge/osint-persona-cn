importScripts("lib/config.js", "lib/platforms.js", "lib/queue.js", "lib/sync.js", "lib/aicu.js", "lib/cookies.js");

const EXT_VERSION = "0.2.9";

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: "osint-save",
    title: "收录到 OSINT 知识库",
    contexts: ["page", "link"],
  });
  chrome.alarms.create("flush-queue", { periodInMinutes: 1 });
  chrome.alarms.create("background-sync", { periodInMinutes: 240 });
  chrome.storage.local.set({
    enabled: true,
    passiveCollect: true,
    backgroundSync: true,
  });
  pingServer();
});

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId !== "osint-save" || !tab) return;
  const url = info.linkUrl || tab.url || "";
  if (!url.startsWith("http")) return;
  await enqueueIfEnabled({
    kind: "save_to_osint",
    url,
    title: tab.title || "",
    platform: OSINTPlatforms.platformFromUrl(url),
    save_knowledge: true,
  });
  await EventQueue.flush();
});

chrome.tabs.onUpdated.addListener((tabId, info, tab) => {
  if (info.status !== "complete" || !tab.url) return;
  chrome.storage.local.get(["enabled", "passiveCollect"], (data) => {
    if (data.enabled === false || data.passiveCollect === false) return;
    if (!OSINTPlatforms.isContentUrl(tab.url)) return;
    enqueueIfEnabled({
      kind: "page_visit",
      url: tab.url,
      title: tab.title || "",
      platform: OSINTPlatforms.platformFromUrl(tab.url),
    });
  });
});

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (!message || !message.kind) return;
  if (message.kind === "get_status") {
    chrome.storage.local.get(["enabled", "passiveCollect", "backgroundSync", "apiBase", "stats"], async (data) => {
      const pending = await EventQueue.pendingCount();
      sendResponse({
        enabled: data.enabled !== false,
        passiveCollect: data.passiveCollect !== false,
        backgroundSync: data.backgroundSync !== false,
        apiBase: data.apiBase || OSINTConfig.defaultApiBase,
        stats: data.stats || {},
        platforms: OSINTPlatforms.domains,
        pendingQueue: pending,
      });
    });
    return true;
  }
  if (message.kind === "set_enabled") {
    chrome.storage.local.set({ enabled: !!message.enabled }, () => sendResponse({ ok: true }));
    return true;
  }
  if (message.kind === "set_passive") {
    chrome.storage.local.set({ passiveCollect: !!message.enabled }, () => sendResponse({ ok: true }));
    return true;
  }
  if (message.kind === "set_background_sync") {
    chrome.storage.local.set({ backgroundSync: !!message.enabled }, () => sendResponse({ ok: true }));
    return true;
  }
  if (message.kind === "flush_now") {
    EventQueue.flush().then((result) => sendResponse(result));
    return true;
  }
  if (message.kind === "sync_aicu") {
    AicuSync.run()
      .then((r) => sendResponse(r))
      .catch((e) => sendResponse({ error: String(e.message || e) }));
    return true;
  }
  if (message.kind === "sync_cookies") {
    CookieBridge.syncToServer()
      .then((r) => sendResponse(r))
      .catch((e) => sendResponse({ error: String(e.message || e) }));
    return true;
  }
  if (message.kind === "sync_now") {
    BackgroundSync.run()
      .then((r) => sendResponse(r))
      .catch((e) => sendResponse({ error: String(e.message || e) }));
    return true;
  }
  enqueueIfEnabled(message);
});

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === "flush-queue") {
    EventQueue.flush();
    pingServer();
    return;
  }
  if (alarm.name === "background-sync") {
    chrome.storage.local.get(["enabled", "backgroundSync"], (data) => {
      if (data.enabled === false || data.backgroundSync === false) return;
      BackgroundSync.run();
    });
  }
});

function enqueueIfEnabled(message) {
  return new Promise((resolve) => {
    chrome.storage.local.get(["enabled", "passiveCollect"], (data) => {
      if (data.enabled === false) {
        resolve();
        return;
      }
      if (message.kind === "page_visit" && data.passiveCollect === false) {
        resolve();
        return;
      }
      EventQueue.enqueue(message).then(resolve);
    });
  });
}

async function pingServer() {
  try {
    const apiBase = await OSINTConfig.getApiBase();
    await fetch(`${apiBase}/api/extension/ping`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ version: EXT_VERSION, enabled: true }),
    });
    try {
      const cfgRes = await fetch(`${apiBase}/api/setup/sync-config`);
      if (cfgRes.ok) {
        const syncConfig = await cfgRes.json();
        await chrome.storage.local.set({ syncConfig });
      }
    } catch (_) {}
  } catch (_) {}
}
