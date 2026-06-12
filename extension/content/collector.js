(function () {
  const host = location.hostname || "";
  const hook = OSINTPlatforms.hookDomains.some((d) => host.includes(d));

  if (hook) {
    const script = document.createElement("script");
    script.src = chrome.runtime.getURL("content/inject.js");
    script.async = false;
    (document.head || document.documentElement).appendChild(script);

    window.addEventListener("message", (event) => {
      if (event.source !== window || !event.data || event.data.source !== "osint-capture") return;
      chrome.runtime.sendMessage({
        kind: "api_capture",
        url: event.data.url,
        body: event.data.body,
        transport: event.data.type,
      });
    });
  }

  function reportVisit() {
    if (!OSINTPlatforms.isContentUrl(location.href)) return;
    chrome.runtime.sendMessage({
      kind: "page_visit",
      url: location.href,
      title: document.title,
      platform: OSINTPlatforms.platformFromUrl(location.href),
    });
  }

  setTimeout(reportVisit, 1500);

  const _pushState = history.pushState;
  history.pushState = function (...args) {
    _pushState.apply(this, args);
    setTimeout(reportVisit, 800);
  };
  window.addEventListener("popstate", () => setTimeout(reportVisit, 800));

  let visibleSince = Date.now();

  function flushDwell() {
    const duration_ms = Date.now() - visibleSince;
    if (duration_ms < 3000 || !OSINTPlatforms.isTrackedUrl(location.href)) return;
    chrome.runtime.sendMessage({
      kind: "page_session",
      url: location.href,
      title: document.title,
      duration_ms,
      platform: OSINTPlatforms.platformFromUrl(location.href),
    });
  }

  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") flushDwell();
    else visibleSince = Date.now();
  });
  window.addEventListener("pagehide", flushDwell);
})();
