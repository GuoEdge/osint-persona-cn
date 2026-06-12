/** 混合同步：优先服务端 Cookie API，轻量滚动补洞 */

const BackgroundSync = {
  async run() {
    const warnings = [];
    const stats = { server: {}, scroll: { pages: 0 } };

    const preferServer = await BackgroundSync._getSyncConfig("prefer_server_api", true);
    if (preferServer) {
      const serverResult = await BackgroundSync._runServerIngest();
      stats.server = serverResult;
      if (serverResult.warnings?.length) {
        warnings.push(...serverResult.warnings);
      }
    }

    const probeEnabled = await BackgroundSync._getSyncConfig("probe_pages_enabled", true);
    const dynamicProbe = probeEnabled ? await BackgroundSync._buildProbePages() : [];
    const scrollPages = [...(OSINTPlatforms.scrollOnlyPages || []), ...dynamicProbe];
    const maxPages = await BackgroundSync._getSyncConfig("max_pages_per_run", 3);
    const tabIds = [];

    for (const page of scrollPages.slice(0, maxPages)) {
      try {
        const tab = await chrome.tabs.create({ url: page.url, active: false });
        tabIds.push(tab.id);
        const initialWait = await BackgroundSync._getSyncConfig("initial_wait_ms", 3000);
        await BackgroundSync._sleep(initialWait);
        if (tab.id) {
          const pageWarn = await BackgroundSync._checkPageError(tab.id);
          if (pageWarn) {
            warnings.push(`${page.label}: ${pageWarn}`);
            break;
          }
          await BackgroundSync._autoscroll(tab.id);
          await BackgroundSync._sleep(4000);
          stats.scroll.pages += 1;
        }
        const gap = await BackgroundSync._getSyncConfig("page_gap_ms", 5000);
        await BackgroundSync._sleep(gap + Math.floor(Math.random() * 3000));
      } catch (err) {
        warnings.push(`${page.label}: ${String(err.message || err)}`);
        break;
      }
    }

    await EventQueue.flush();
    for (const id of tabIds) {
      try {
        await chrome.tabs.remove(id);
      } catch (_) {}
    }

    const result = { stats, warnings, ok: warnings.length === 0 };
    await chrome.storage.local.set({
      lastSyncResult: { at: Date.now(), ...result },
    });
    return result;
  },

  async _runServerIngest() {
    const apiBase = await OSINTConfig.getApiBase();
    const out = { bilibili: null, zhihu: null, warnings: [] };
    try {
      const pre = await fetch(`${apiBase}/api/ingest/preflight`);
      if (pre.ok) {
        const preJson = await pre.json();
        if (!preJson.ready && preJson.hints?.length) {
          out.warnings.push(...preJson.hints);
          return out;
        }
      }
    } catch (e) {
      out.warnings.push(`无法连接本机 Web (${apiBase})：${e.message || e}。请先运行 start-osint-web.bat`);
      return out;
    }
    try {
      const res = await fetch(`${apiBase}/api/ingest/accounts-sync`, {
        method: "POST",
        signal: AbortSignal.timeout(180000),
      });
      const data = await res.json();
      out.bilibili = data.bilibili || null;
      out.zhihu = data.zhihu || null;
      if (!res.ok) {
        out.warnings.push(data.detail || `HTTP ${res.status}`);
      } else if (data.warnings?.length) {
        out.warnings.push(...data.warnings);
      }
      if ((data.count || 0) === 0 && !out.warnings.length) {
        out.warnings.push("拉取 0 条：请到 Web 设置页同步 Cookie（需关闭 Edge）");
      }
    } catch (e) {
      out.warnings.push(`服务端拉取: ${e.message || e}`);
    }
    return out;
  },

  async _buildProbePages() {
    const pages = [];
    let zhihuToken = "";
    let bilibiliMid = "";
    try {
      const res = await fetch("https://www.zhihu.com/api/v4/me", { credentials: "include" });
      if (res.ok) {
        const me = await res.json();
        zhihuToken = me.url_token || "";
      }
    } catch (_) {}
    try {
      const nav = await fetch("https://api.bilibili.com/x/web-interface/nav", { credentials: "include" });
      if (nav.ok) {
        const data = await nav.json();
        if (data?.data?.isLogin) {
          bilibiliMid = String(data.data.mid || "");
        }
      }
    } catch (_) {}
    for (const tpl of OSINTPlatforms.probePageTemplates || []) {
      let url = tpl.url
        .replace("{zhihu_token}", zhihuToken)
        .replace("{bilibili_mid}", bilibiliMid);
      if (url.includes("{")) continue;
      if (tpl.url.includes("{bilibili_mid}") && !bilibiliMid) continue;
      if (tpl.url.includes("{zhihu_token}") && !zhihuToken) continue;
      pages.push({ label: tpl.label, url });
    }
    return pages;
  },

  async _getSyncConfig(key, fallback) {
    return new Promise((resolve) => {
      chrome.storage.local.get(["syncConfig"], (data) => {
        const cfg = data.syncConfig || {};
        resolve(cfg[key] !== undefined ? cfg[key] : fallback);
      });
    });
  },

  async _checkPageError(tabId) {
    try {
      const [{ result }] = await chrome.scripting.executeScript({
        target: { tabId },
        func: () => {
          const title = document.title || "";
          const body = (document.body?.innerText || "").slice(0, 500);
          const text = `${title} ${body}`;
          if (/404|页面不存在|找不到|风控|频繁|412|-412|访问过于频繁/i.test(text)) {
            return text.slice(0, 120);
          }
          return "";
        },
      });
      return result || "";
    } catch (_) {
      return "";
    }
  },

  async _autoscroll(tabId) {
    const rounds = await BackgroundSync._getSyncConfig("scroll_rounds", 4);
    const interval = await BackgroundSync._getSyncConfig("scroll_interval_ms", 1500);
    try {
      await chrome.scripting.executeScript({
        target: { tabId },
        args: [rounds, interval],
        func: (max, ms) => {
          return new Promise((resolve) => {
            let count = 0;
            const timer = setInterval(() => {
              window.scrollBy(0, Math.max(300, window.innerHeight * 0.6));
              count += 1;
              if (count >= max) {
                clearInterval(timer);
                resolve(true);
              }
            }, ms);
          });
        },
      });
    } catch (_) {}
  },

  _sleep(ms) {
    return new Promise((r) => setTimeout(r, ms));
  },
};
