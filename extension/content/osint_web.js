/** 从情报台 Web 页面同步 API token 到扩展存储 */
(() => {
  const token = document.querySelector('meta[name="osint-token"]')?.content;
  if (token) {
    chrome.storage.local.set({ webToken: token });
  }
})();
