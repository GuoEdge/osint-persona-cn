const EventQueue = {
  _key: "pendingEvents",
  async enqueue(event) {
    const items = await EventQueue._load();
    items.push({ ...event, ts: Date.now() });
    if (items.length > 500) items.splice(0, items.length - 500);
    await EventQueue._save(items);
    if (items.length >= 20) {
      await EventQueue.flush();
    }
  },
  async pendingCount() {
    const items = await EventQueue._load();
    return items.length;
  },
  async flush() {
    const items = await EventQueue._load();
    if (!items.length) {
      return { accepted: 0, skipped: 0, empty: true, pending: 0 };
    }
    const apiBase = await OSINTConfig.getApiBase();
    try {
      const resp = await fetch(`${apiBase}/api/extension/events`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          events: items,
          version: OSINTConfig.extVersion,
        }),
      });
      if (!resp.ok) {
        let detail = `HTTP ${resp.status}`;
        try {
          const errBody = await resp.json();
          if (errBody.detail) {
            detail = typeof errBody.detail === "string" ? errBody.detail : JSON.stringify(errBody.detail);
          }
        } catch (_) {}
        throw new Error(detail);
      }
      const result = await resp.json();
      await EventQueue._save([]);
      const stats = {
        lastFlush: new Date().toISOString(),
        lastAccepted: result.accepted || 0,
        lastSkipped: result.skipped || 0,
      };
      chrome.storage.local.set({ stats });
      return { ...result, empty: false, pending: 0 };
    } catch (err) {
      return { error: String(err), pending: items.length };
    }
  },
  _load() {
    return new Promise((resolve) => {
      chrome.storage.local.get([EventQueue._key], (data) => {
        resolve(Array.isArray(data[EventQueue._key]) ? data[EventQueue._key] : []);
      });
    });
  },
  _save(items) {
    return new Promise((resolve) => {
      chrome.storage.local.set({ [EventQueue._key]: items }, resolve);
    });
  },
};
