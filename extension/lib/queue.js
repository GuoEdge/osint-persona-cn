const EventQueue = {
  _key: "pendingEvents",
  _maxAttempts: 3,
  _batchSize: 25,
  _maxQueue: 500,
  _maxBodyChars: 120000,
  async enqueue(event) {
    if (event.kind === "page_visit" && EventQueue._shouldSkipVisit(event.url)) {
      return;
    }
    const items = await EventQueue._load();
    items.push(EventQueue._trimEvent({ ...event, ts: Date.now() }));
    if (items.length > EventQueue._maxQueue) items.splice(0, items.length - EventQueue._maxQueue);
    await EventQueue._save(items);
    EventQueue._updateBadge(items.length);
    if (items.length >= 20) {
      await EventQueue.flush();
    }
  },
  _trimEvent(event) {
    const trimmed = { ...event };
    if (trimmed.body == null) return trimmed;
    try {
      const json = JSON.stringify(trimmed.body);
      if (json.length <= EventQueue._maxBodyChars) return trimmed;
      trimmed.body = {
        _truncated: true,
        _original_bytes: json.length,
        _preview: json.slice(0, 2000),
      };
    } catch (_) {
      trimmed.body = { _truncated: true, _error: "unserializable" };
    }
    return trimmed;
  },
  _shouldSkipVisit(url) {
    if (!url) return true;
    const now = Date.now();
    const key = String(url).split("#")[0];
    if (!EventQueue._recentVisits) EventQueue._recentVisits = new Map();
    const prev = EventQueue._recentVisits.get(key);
    if (prev && now - prev < 45000) return true;
    EventQueue._recentVisits.set(key, now);
    if (EventQueue._recentVisits.size > 200) {
      for (const [k, ts] of EventQueue._recentVisits) {
        if (now - ts > 120000) EventQueue._recentVisits.delete(k);
      }
    }
    return false;
  },
  async pendingCount() {
    const items = await EventQueue._load();
    return items.length;
  },
  _sleep(ms) {
    return new Promise((r) => setTimeout(r, ms));
  },
  _updateBadge(pending, hasError = false) {
    try {
      if (hasError && pending > 0) {
        chrome.action.setBadgeText({ text: String(Math.min(pending, 99)) });
        chrome.action.setBadgeBackgroundColor({ color: "#dc2626" });
        return;
      }
      if (pending > 0) {
        chrome.action.setBadgeText({ text: String(Math.min(pending, 99)) });
        chrome.action.setBadgeBackgroundColor({ color: "#d97706" });
        return;
      }
      chrome.action.setBadgeText({ text: "" });
    } catch (_) {}
  },
  async flush() {
    EventQueue._flushChain = (EventQueue._flushChain || Promise.resolve()).then(() => EventQueue._doFlush()).catch((e) => {
      EventQueue._flushChain = null;
      throw e;
    });
    return EventQueue._flushChain;
  },
  async _doFlush() {
    let remaining = await EventQueue._load();
    if (!remaining.length) {
      EventQueue._updateBadge(0);
      return { accepted: 0, skipped: 0, empty: true, pending: 0 };
    }
    const apiBase = await OSINTConfig.getApiBase();
    let lastErr = "";
    let totalAccepted = 0;
    let totalSkipped = 0;
    let totalSaved = 0;
    const started = remaining.length;

    while (remaining.length > 0) {
      const batch = remaining.slice(0, EventQueue._batchSize);
      let batchOk = false;
      for (let attempt = 0; attempt < EventQueue._maxAttempts; attempt += 1) {
        try {
          const headers = await OSINTConfig.authHeaders({ "Content-Type": "application/json" });
          const resp = await fetch(`${apiBase}/api/extension/events`, {
            method: "POST",
            headers,
            credentials: "include",
            body: JSON.stringify({
              events: batch,
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
          totalAccepted += result.accepted || 0;
          totalSkipped += result.skipped || 0;
          totalSaved += result.saved_to_knowledge || 0;
          remaining = remaining.slice(batch.length);
          await EventQueue._save(remaining);
          EventQueue._updateBadge(remaining.length);
          batchOk = true;
          break;
        } catch (err) {
          lastErr = String(err.message || err);
          if (attempt < EventQueue._maxAttempts - 1) {
            await EventQueue._sleep(800 * (attempt + 1));
          }
        }
      }
      if (!batchOk) {
        await EventQueue._setStorage({ lastFlushError: lastErr });
        EventQueue._updateBadge(remaining.length, true);
        return {
          error: lastErr,
          pending: remaining.length,
          accepted: totalAccepted,
          skipped: totalSkipped,
          saved_to_knowledge: totalSaved,
          batches_sent: started - remaining.length,
        };
      }
    }

    const stats = {
      lastFlush: new Date().toISOString(),
      lastAccepted: totalAccepted,
      lastSkipped: totalSkipped,
      lastSavedKnowledge: totalSaved,
    };
    await EventQueue._setStorage({ stats, lastFlushError: "" });
    EventQueue._updateBadge(0);
    return {
      accepted: totalAccepted,
      skipped: totalSkipped,
      saved_to_knowledge: totalSaved,
      empty: false,
      pending: 0,
      batches_sent: Math.ceil(started / EventQueue._batchSize),
    };
  },
  _setStorage(patch) {
    return new Promise((resolve) => {
      chrome.storage.local.set(patch, resolve);
    });
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
