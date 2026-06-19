const OSINTConfig = {
  extVersion: "0.3.1",
  defaultApiBase: "http://127.0.0.1:8787",
  async getApiBase() {
    return new Promise((resolve) => {
      chrome.storage.local.get(["apiBase"], (data) => {
        resolve(data.apiBase || OSINTConfig.defaultApiBase);
      });
    });
  },
  async getWebToken() {
    return new Promise((resolve) => {
      chrome.storage.local.get(["webToken"], (data) => {
        resolve(data.webToken || "");
      });
    });
  },
  async authHeaders(extra = {}) {
    const headers = { ...extra };
    const webToken = await OSINTConfig.getWebToken();
    if (webToken) headers["X-Osint-Token"] = webToken;
    return headers;
  },
};
