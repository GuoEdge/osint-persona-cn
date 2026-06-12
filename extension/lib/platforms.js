/** 支持的平台与同步页 / Supported platforms and background sync targets */

const OSINTPlatforms = {
  domains: [
    "bilibili.com",
    "zhihu.com",
    "github.com",
    "v2ex.com",
    "juejin.cn",
    "sspai.com",
    "huxiu.com",
    "36kr.com",
    "xiaohongshu.com",
    "weibo.com",
    "douban.com",
    "twitter.com",
    "x.com",
  ],

  hookDomains: ["bilibili.com", "zhihu.com", "github.com"],

  /** 已由服务端 Cookie API 覆盖，不再滚动 */
  syncPages: [],

  /** 自动打开的补洞页：触发页面内 API，由 inject 拦截后上传。 */
  scrollOnlyPages: [],

  /** 由 sync.js 按登录用户动态填充（recent-viewed、主页动态） */
  probePageTemplates: [
    { url: "https://www.zhihu.com/recent-viewed", label: "知乎最近浏览" },
    { url: "https://www.zhihu.com/people/{zhihu_token}", label: "知乎主页动态" },
    { url: "https://space.bilibili.com/{bilibili_mid}/dynamic", label: "B站动态" },
    { url: "https://space.bilibili.com/{bilibili_mid}/", label: "B站主页" },
    { url: "https://www.bilibili.com/account/history", label: "B站观看历史" },
  ],

  platformFromUrl(url) {
    const u = String(url || "").toLowerCase();
    if (u.includes("bilibili.com")) return "bilibili";
    if (u.includes("zhihu.com")) return "zhihu";
    if (u.includes("github.com")) return "github";
    if (u.includes("v2ex.com")) return "v2ex";
    if (u.includes("juejin.cn")) return "juejin";
    if (u.includes("sspai.com")) return "sspai";
    if (u.includes("huxiu.com")) return "huxiu";
    if (u.includes("36kr.com")) return "36kr";
    if (u.includes("xiaohongshu.com")) return "xiaohongshu";
    if (u.includes("weibo.com")) return "weibo";
    if (u.includes("douban.com")) return "douban";
    if (u.includes("twitter.com") || u.includes("x.com")) return "twitter";
    return "web";
  },

  isTrackedUrl(url) {
    if (!url || !url.startsWith("http")) return false;
    const lower = url.toLowerCase();
    if (lower.includes("login") || lower.includes("signin") || lower.includes("passport")) return false;
    return OSINTPlatforms.domains.some((d) => lower.includes(d));
  },

  isContentUrl(url) {
    if (!OSINTPlatforms.isTrackedUrl(url)) return false;
    const lower = url.toLowerCase();
    const noise = ["/search?", "/login", "/signin", "/settings/account", "/notifications"];
    if (noise.some((n) => lower.includes(n))) return false;
    return true;
  },
};
