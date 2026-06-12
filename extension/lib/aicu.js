/** 在 aicu.cc 页面上下文拉取发评（携带页面 Cookie / WAF 会话） */

const AicuSync = {
  async fetchMid(apiBase) {
    const resp = await fetch(`${apiBase}/api/ingest/bilibili-mid`);
    if (!resp.ok) throw new Error(`获取 B 站 UID 失败: ${resp.status}（请先启动本机 Web 并同步 B 站 Cookie）`);
    const data = await resp.json();
    if (!data.mid) throw new Error("B 站未登录：扩展弹窗先点「同步 Cookie 到本机」");
    return data.mid;
  },

  async checkEnabled(apiBase) {
    const resp = await fetch(`${apiBase}/api/ingest/aicu-status`);
    if (!resp.ok) return;
    const data = await resp.json();
    if (!data.enabled) {
      throw new Error(
        "AICU 导入未开启：在 ~/.osint/config.yaml 设置 ingest.aicu_enabled: true 后重启 Web 服务"
      );
    }
  },

  waitForTabComplete(tabId, timeoutMs = 45000) {
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        chrome.tabs.onUpdated.removeListener(onUpdated);
        reject(new Error("打开 aicu.cc 超时，请手动打开 https://www.aicu.cc/ 后重试"));
      }, timeoutMs);
      function onUpdated(id, info) {
        if (id === tabId && info.status === "complete") {
          clearTimeout(timer);
          chrome.tabs.onUpdated.removeListener(onUpdated);
          resolve();
        }
      }
      chrome.tabs.onUpdated.addListener(onUpdated);
    });
  },

  async findOrOpenAicuTab() {
    const patterns = ["*://www.aicu.cc/*", "*://*.aicu.cc/*"];
    const tabs = await chrome.tabs.query({ url: patterns });
    if (tabs.length) return { tabId: tabs[0].id, opened: false };
    const tab = await chrome.tabs.create({ url: "https://www.aicu.cc/", active: true });
    await this.waitForTabComplete(tab.id);
    return { tabId: tab.id, opened: true };
  },

  async fetchPageInTab(tabId, uid, pn, ps = 100) {
    const results = await chrome.scripting.executeScript({
      target: { tabId },
      world: "MAIN",
      func: async (uidArg, pnArg, psArg) => {
        const url = new URL("https://api.aicu.cc/api/v3/search/getreply");
        url.searchParams.set("uid", String(uidArg));
        url.searchParams.set("pn", String(pnArg));
        url.searchParams.set("ps", String(psArg));
        url.searchParams.set("mode", "0");
        url.searchParams.set("keyword", "");
        const resp = await fetch(url.toString(), {
          credentials: "include",
          headers: {
            Accept: "application/json, text/plain, */*",
            Referer: "https://www.aicu.cc/",
          },
        });
        const text = await resp.text();
        return { ok: resp.ok, status: resp.status, text: text.slice(0, 200000) };
      },
      args: [uid, pn, ps],
    });
    const out = results?.[0]?.result;
    if (!out) throw new Error("无法在 aicu.cc 页面执行请求，请重载扩展后重试");
    if (!out.ok) {
      throw new Error(`AICU HTTP ${out.status}：请在 aicu.cc 页面完成人机验证后再点一次`);
    }
    const snippet = (out.text || "").slice(0, 160);
    if (/Just a moment|safeline|cf-browser-verification|challenge-platform/i.test(snippet)) {
      throw new Error("AICU 人机验证未通过：请在已打开的 aicu.cc 标签页手动查一次 UID，再重试扩展按钮");
    }
    try {
      return JSON.parse(out.text);
    } catch (_) {
      throw new Error("AICU 返回非 JSON：请先在 aicu.cc 页面通过验证并能正常查评论后再试");
    }
  },

  async run() {
    const apiBase = await OSINTConfig.getApiBase();
    await this.checkEnabled(apiBase);
    const mid = await this.fetchMid(apiBase);
    const { tabId, opened } = await this.findOrOpenAicuTab();
    if (opened) {
      await new Promise((r) => setTimeout(r, 2000));
    }

    const pages = [];
    let pn = 1;
    let allCount = 0;
    while (pn <= 100) {
      const body = await this.fetchPageInTab(tabId, mid, pn, 100);
      if (body.code !== 0 && body.code != null) {
        throw new Error(`AICU 业务错误 code=${body.code}`);
      }
      const data = body.data || {};
      const cursor = data.cursor || {};
      allCount = cursor.all_count || allCount;
      pages.push(body);
      if (cursor.is_end || !(data.replies || []).length) break;
      pn += 1;
      await new Promise((r) => setTimeout(r, 1500));
    }

    if (!pages.length || !pages.some((p) => (p.data?.replies || []).length)) {
      throw new Error(`AICU 无发评数据（UID=${mid}）。确认 aicu.cc 能查到该 UID 的评论`);
    }

    const resp = await fetch(`${apiBase}/api/ingest/aicu-json`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pages }),
    });
    const result = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      throw new Error(result.detail || result.error || resp.statusText);
    }
    if (result.ok === false) {
      if (result.error === "aicu_disabled") {
        throw new Error("服务端 AICU 未开启：config.yaml 设 ingest.aicu_enabled: true 并重启 Web");
      }
      throw new Error(result.error || "导入失败");
    }
    return { mid, pages: pages.length, all_count: allCount, ...result };
  },
};
