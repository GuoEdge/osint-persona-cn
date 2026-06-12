/** 经 chrome.cookies 读取登录态并写入本机 OSINT（绕过 Edge App-Bound 磁盘加密） */

const CookieBridge = {
  targets: ["bilibili.com", "zhihu.com"],

  _listDomain(domain) {
    return new Promise((resolve) => {
      chrome.cookies.getAll({ domain }, (cookies) => resolve(cookies || []));
    });
  },

  _toHeader(cookies) {
    const parts = [];
    const seen = new Set();
    for (const c of cookies) {
      if (!c?.name || c.value == null || seen.has(c.name)) continue;
      seen.add(c.name);
      parts.push(`${c.name}=${c.value}`);
    }
    return parts.join("; ");
  },

  async collect() {
    const domains = {};
    for (const root of CookieBridge.targets) {
      const merged = [];
      const seen = new Set();
      for (const d of [root, `.${root}`]) {
        for (const c of await CookieBridge._listDomain(d)) {
          const key = `${c.name}\0${c.domain}`;
          if (seen.has(key)) continue;
          seen.add(key);
          merged.push(c);
        }
      }
      const header = CookieBridge._toHeader(merged);
      if (header) domains[root] = header;
    }
    return domains;
  },

  async syncToServer() {
    const apiBase = await OSINTConfig.getApiBase();
    const domains = await CookieBridge.collect();
    if (!Object.keys(domains).length) {
      return { error: "未读到 Cookie：请先在 Edge 登录 B站/知乎 并保持扩展已启用" };
    }
    const res = await fetch(`${apiBase}/api/auth/import-cookies`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ browser: "extension", domains }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      return { error: data.detail || `HTTP ${res.status}` };
    }
    return { ok: true, ...data };
  },
};
