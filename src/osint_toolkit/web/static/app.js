/* 全局工具 / Global utilities */

const THEME_STORAGE_KEY = "osint-theme";
const READING_SIZE_KEY = "osint-reading-size";

const searchSession = {
  generation: 0,
  runId: null,
  es: null,
  pollAbort: null,
  streamClosed: false,
};

let sidebarPollTimer = null;
let workspaceProgressUi = null;

const expandSession = { generation: 0 };

const searchTaskRegistry = {
  pollTimer: null,
  lastStatusByRun: new Map(),
  focusedRunId: null,
};

const SEARCH_TASK_STATUS_LABELS = {
  queued: "排队中",
  running: "进行中",
  done: "已完成",
  error: "失败",
  cancelled: "已取消",
};

function beginSearchSession(runId) {
  searchSession.generation += 1;
  searchSession.runId = runId;
  searchSession.streamClosed = false;
  if (searchSession.es) {
    searchSession.streamClosed = true;
    searchSession.es.close();
    searchSession.es = null;
  }
  if (searchSession.pollAbort) {
    searchSession.pollAbort.abort();
    searchSession.pollAbort = null;
  }
  return searchSession.generation;
}

function isActiveSearchSession(gen, runId) {
  return searchSession.generation === gen && searchSession.runId === runId;
}

function cleanupSearchSession() {
  searchSession.streamClosed = true;
  if (searchSession.es) {
    searchSession.es.close();
    searchSession.es = null;
  }
  if (searchSession.pollAbort) {
    searchSession.pollAbort.abort();
    searchSession.pollAbort = null;
  }
}

if (!window._osintPageCleanupBound) {
  window._osintPageCleanupBound = true;
  window.addEventListener("pagehide", () => {
    cleanupSearchSession();
    if (sidebarPollTimer) clearInterval(sidebarPollTimer);
    if (typeof _runsRefreshTimer !== "undefined" && _runsRefreshTimer) clearTimeout(_runsRefreshTimer);
    if (window._runDetailPoll) clearTimeout(window._runDetailPoll);
    stopSearchTaskPolling();
  });
}

function getThemePreference() {
  try {
    return localStorage.getItem(THEME_STORAGE_KEY) || "system";
  } catch (_) {
    return "system";
  }
}

function resolveTheme(pref) {
  if (pref === "dark") return "dark";
  if (pref === "light") return "light";
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function applyTheme(pref) {
  const resolved = resolveTheme(pref);
  document.documentElement.dataset.theme = resolved;
  document.documentElement.dataset.themePref = pref;
}

function setThemePreference(pref) {
  try {
    localStorage.setItem(THEME_STORAGE_KEY, pref);
  } catch (_) {}
  applyTheme(pref);
  document.querySelectorAll("[data-theme-option]").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.themeOption === pref);
  });
}

function initTheme() {
  applyTheme(getThemePreference());
  try {
    const size = localStorage.getItem(READING_SIZE_KEY);
    if (size) document.documentElement.dataset.readingSize = size;
  } catch (_) {}
  if (typeof syncReadingSizeUi === "function") syncReadingSizeUi();
  const mq = window.matchMedia("(prefers-color-scheme: dark)");
  mq.addEventListener("change", () => {
    if (getThemePreference() === "system") applyTheme("system");
  });
}

function initThemeSettings() {
  const host = document.getElementById("theme-appearance-control");
  if (!host) return;
  const pref = getThemePreference();
  host.querySelectorAll("[data-theme-option]").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.themeOption === pref);
    btn.addEventListener("click", () => setThemePreference(btn.dataset.themeOption));
  });
}

function initSegmentedControl(container, { onSelect, attr = "data-segment" } = {}) {
  if (!container) return;
  container.classList.add("ui-segmented");
  const items = container.querySelectorAll("button, .ui-segmented-item, [role='tab']");
  items.forEach((btn) => {
    btn.addEventListener("click", () => {
      const val = btn.dataset.segment || btn.dataset.panel || btn.dataset.tab
        || btn.dataset.knowledgeTab || btn.dataset.workspacePanel || btn.id;
      items.forEach((b) => {
        const active = b === btn;
        b.classList.toggle("active", active);
        if (b.getAttribute("role") === "tab") b.setAttribute("aria-selected", active ? "true" : "false");
      });
      if (onSelect) onSelect(val, btn);
    });
  });
}

function setReadingSize(delta) {
  const steps = ["sm", "", "lg", "xl"];
  let idx = steps.indexOf(document.documentElement.dataset.readingSize || "");
  if (idx < 0) idx = 1;
  idx = Math.max(0, Math.min(steps.length - 1, idx + delta));
  const next = steps[idx];
  if (next) document.documentElement.dataset.readingSize = next;
  else delete document.documentElement.dataset.readingSize;
  try {
    if (next) localStorage.setItem(READING_SIZE_KEY, next);
    else localStorage.removeItem(READING_SIZE_KEY);
  } catch (_) {}
  syncReadingSizeUi();
}

const READING_SIZE_LABELS = { sm: "小", "": "标准", lg: "大", xl: "特大" };

function syncReadingSizeUi() {
  const steps = ["sm", "", "lg", "xl"];
  const size = document.documentElement.dataset.readingSize || "";
  let idx = steps.indexOf(size);
  if (idx < 0) idx = 1;
  const label = READING_SIZE_LABELS[size] ?? "标准";
  const labelEl = document.getElementById("reading-size-label");
  if (labelEl) labelEl.textContent = label;
  const panel = document.getElementById("report-panel");
  if (panel) {
    if (size) panel.dataset.readingSize = size;
    else delete panel.dataset.readingSize;
  }
  const down = document.getElementById("reading-size-down");
  const up = document.getElementById("reading-size-up");
  if (down) down.disabled = idx <= 0;
  if (up) up.disabled = idx >= steps.length - 1;
}

function isWorkspaceSplitWide() {
  return window.matchMedia("(min-width: 1281px)").matches;
}

function isWorkspaceSplitActive() {
  const cb = document.getElementById("workspace-split-view");
  return Boolean(isWorkspaceSplitWide() && cb?.checked);
}

function updateSplitControlState() {
  const cb = document.getElementById("workspace-split-view");
  const splitBtn = document.getElementById("reading-split-btn");
  const wrap = document.getElementById("workspace-split-wrap");
  const statusEl = document.getElementById("reading-split-status");
  const layout = document.querySelector(".results-layout");
  const splitOn = isWorkspaceSplitActive();
  const splitRequested = Boolean(cb?.checked);

  splitBtn?.classList.toggle("active", splitOn);
  splitBtn?.setAttribute("aria-pressed", splitOn ? "true" : "false");
  wrap?.classList.toggle("workspace-split-active", splitOn);
  layout?.classList.toggle("workspace-split-pending", splitRequested && !splitOn);

  if (statusEl) {
    if (splitOn) {
      statusEl.textContent = "对照中";
      statusEl.classList.remove("hidden");
    } else if (splitRequested && !isWorkspaceSplitWide()) {
      statusEl.textContent = "需宽屏";
      statusEl.classList.remove("hidden");
    } else {
      statusEl.textContent = "";
      statusEl.classList.add("hidden");
    }
  }

  document.querySelectorAll('.workspace-panel-tab[data-panel="results"], .workspace-panel-tab[data-panel="report"]').forEach((tab) => {
    tab.classList.toggle("split-active", splitOn);
  });
  updateReportTabSplitHint();
}

function setWorkspaceSplitEnabled(enabled, { persist = true } = {}) {
  const cb = document.getElementById("workspace-split-view");
  if (!cb) return false;
  if (enabled && !isWorkspaceSplitWide()) {
    showToast("对照分屏需要较宽窗口（≥1280px），请拉宽浏览器后重试", "info");
    return false;
  }
  cb.checked = Boolean(enabled);
  if (persist) {
    try {
      localStorage.setItem("workspaceSplit", cb.checked ? "1" : "0");
    } catch (_) {}
  }
  applyWorkspaceSplitLayout();
  return true;
}

function toggleWorkspaceSplit({ persist = true, focusPanel = null } = {}) {
  const cb = document.getElementById("workspace-split-view");
  if (!cb) return;
  const next = !cb.checked;
  if (!setWorkspaceSplitEnabled(next, { persist })) return;
  if (next && focusPanel) switchWorkspacePanel(focusPanel);
}

function buildReportToc(reportEl) {
  if (!reportEl) return;
  const inner = reportEl.querySelector(".markdown-body-inner") || reportEl;
  const headings = [...inner.querySelectorAll("h2, h3")];
  const cites = [...inner.querySelectorAll(".citation-ref")];
  const links = [];
  if (!headings.length && cites.length < 2) {
    ["report-toc", "report-toc-inline"].forEach((id) => {
      const el = document.getElementById(id);
      if (el) {
        el.classList.add("hidden");
        el.innerHTML = "";
      }
    });
    return;
  }
  headings.forEach((h, i) => {
    if (!h.id) h.id = `report-section-${i}`;
    links.push(`<a href="#${h.id}">${escapeHtml(h.textContent.trim().slice(0, 48))}</a>`);
  });
  if (!headings.length && cites.length) {
    const seen = new Set();
    cites.forEach((c) => {
      const t = c.textContent.trim();
      if (seen.has(t)) return;
      seen.add(t);
      links.push(`<a href="#" data-citation-jump="${escapeHtml(c.dataset.citationRef || "")}">${escapeHtml(t)}</a>`);
    });
  }
  const navHtml = links.length ? `<nav aria-label="报告目录">${links.join("")}</nav>` : "";
  ["report-toc", "report-toc-inline"].forEach((id) => {
    const toc = document.getElementById(id);
    if (!toc) return;
    toc.innerHTML = navHtml;
    toc.classList.toggle("hidden", !links.length);
    toc.querySelectorAll("[data-citation-jump]").forEach((a) => {
      a.addEventListener("click", (e) => {
        e.preventDefault();
        const cid = a.dataset.citationJump;
        if (cid) scrollToCitationTarget(cid, { reportEl, resultsRoot: document.getElementById("search-results") });
      });
    });
  });
}

function initReadingToolbar() {
  document.getElementById("reading-size-down")?.addEventListener("click", () => setReadingSize(-1));
  document.getElementById("reading-size-up")?.addEventListener("click", () => setReadingSize(1));
  syncReadingSizeUi();
  document.getElementById("reading-focus-btn")?.addEventListener("click", () => {
    const on = document.body.classList.toggle("focus-reading");
    const wrap = document.querySelector(".report-panel-wrap");
    if (wrap && on) wrap.setAttribute("aria-hidden", "false");
  });
  document.getElementById("reading-split-btn")?.addEventListener("click", () => {
    toggleWorkspaceSplit({ persist: true, focusPanel: "report" });
  });
  document.getElementById("reading-copy-md")?.addEventListener("click", async () => {
    const panel = document.getElementById("report-panel");
    const text = panel?.dataset.rawMarkdown || panel?.innerText || "";
    try {
      await navigator.clipboard.writeText(text);
      showToast("已复制报告 Markdown", "success");
    } catch (_) {
      showToast("复制失败", "error");
    }
  });
}

function wrapReportForReading(reportEl) {
  if (!reportEl || reportEl.dataset.readingWrapped === "1") return;
  reportEl.classList.add("reading-surface");
  if (!reportEl.querySelector(".markdown-body-inner")) {
    const inner = document.createElement("div");
    inner.className = "markdown-body-inner";
    while (reportEl.firstChild) inner.appendChild(reportEl.firstChild);
    reportEl.appendChild(inner);
  }
  reportEl.dataset.readingWrapped = "1";
}

function ensureReadingSurface(el) {
  if (el) el.classList.add("reading-surface");
}

const EMPTY_STATE_SVG = {
  search: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg>`,
  knowledge: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>`,
  persona: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="12" cy="8" r="3.5"/><path d="M5 20c1.5-3 4-4.5 7-4.5s5.5 1.5 7 4.5"/></svg>`,
  runs: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 8v4l2.5 2.5"/><circle cx="12" cy="12" r="9"/></svg>`,
};

function renderEmptyStateRich(variant, title, descHtml, actionsHtml = "") {
  const icon = EMPTY_STATE_SVG[variant] || EMPTY_STATE_SVG.search;
  return `<div class="empty-state-rich empty-state-icon--${escapeHtml(variant)}">
    <div class="empty-state-rich-icon" aria-hidden="true">${icon}</div>
    <div class="empty-state-title">${escapeHtml(title)}</div>
    <p class="empty-state-desc muted">${descHtml}</p>
    ${actionsHtml ? `<div class="empty-state-actions">${actionsHtml}</div>` : ""}
  </div>`;
}

function initGlobalShortcuts() {
  document.addEventListener("keydown", (e) => {
    const tag = (e.target?.tagName || "").toLowerCase();
    const typing = tag === "input" || tag === "textarea" || tag === "select" || e.target?.isContentEditable;
    if ((e.key === "/" || ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k")) && !typing) {
      const q = document.getElementById("search-query");
      if (q) {
        e.preventDefault();
        q.focus();
      }
      return;
    }
    if (typing) return;
    if (e.key === "1") switchWorkspacePanel("results");
    if (e.key === "2") switchWorkspacePanel("report");
    if (e.key === "3") switchWorkspacePanel("research");
    if (e.key === "Escape") {
      document.body.classList.remove("focus-reading");
      document.querySelectorAll("dialog[open]").forEach((d) => d.close());
    }
  });
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function safeHref(url) {
  const raw = String(url || "").trim();
  if (!raw) return "";
  try {
    const parsed = new URL(raw, window.location.origin);
    if (parsed.protocol === "http:" || parsed.protocol === "https:") {
      return parsed.href;
    }
  } catch (_) {}
  return "";
}

function getWebToken() {
  return document.querySelector('meta[name="osint-token"]')?.content || "";
}

function isMacPlatform() {
  return (
    /Mac|iPhone|iPad|iPod/i.test(navigator.platform || "") ||
    navigator.userAgentData?.platform === "macOS"
  );
}

function modKeyLabel() {
  return isMacPlatform() ? "⌘" : "Ctrl";
}

function citationLinkTitle(url) {
  const mod = modKeyLabel();
  if (url) {
    return `单击：定位到结果卡片并展开 · ${mod} 或 Shift+单击：在浏览器打开原文`;
  }
  return `单击：定位到阅读清单或结果卡片 · ${mod} 或 Shift+单击：尝试打开原文`;
}

function reportHasCitations(reportEl) {
  if (!reportEl) return false;
  if (reportEl.querySelector(".citation-ref")) return true;
  return /\[c\d+\]/i.test(reportEl.textContent || "");
}

function mergedCitationMap() {
  return { ...(workspaceSession.citationMap || {}), ...(askSession.citationMap || {}) };
}

function updateReportInteractionHint(reportEl, hasReport) {
  const el = document.getElementById("report-interaction-hint");
  if (!el) return;
  const hasCitations = hasReport && reportHasCitations(reportEl);
  if (!hasCitations) {
    el.classList.add("hidden");
    el.innerHTML = "";
    return;
  }
  const mod = modKeyLabel();
  const splitOn =
    document.querySelector(".results-layout.workspace-split") &&
    window.matchMedia("(min-width: 1281px)").matches;
  const splitNote = splitOn
    ? " 分屏模式下追问请切换到「情报报告」Tab；可用工具栏 <strong>Focus</strong> 沉浸阅读。"
    : " 宽屏可勾选上方「结果/报告分屏」对照阅读，或使用工具栏 <strong>Focus</strong> 沉浸阅读。";
  el.classList.remove("hidden");
  el.innerHTML = `<p class="interaction-hint" role="note"><span class="interaction-hint-kbd">提示</span> 报告内 <code>[cN]</code> 可点击：<strong>单击</strong>跳转到左侧结果卡片并展开；<strong>${escapeHtml(mod)}+单击</strong> 或 <strong>Shift+单击</strong> 在浏览器打开原文。${splitNote}</p>`;
  try {
    if (!sessionStorage.getItem("uxHint.citation")) {
      sessionStorage.setItem("uxHint.citation", "1");
      showToast(`${mod}+点击报告中的 [cN] 可直接打开原文`, "info");
    }
  } catch (_) {}
}

function updateResultsInteractionHint(hasReport, reportEl) {
  const hint = document.querySelector(".results-hint");
  if (!hint) return;
  const hasCitations = hasReport && reportHasCitations(reportEl);
  let extra = "";
  if (hasCitations) {
    const mod = modKeyLabel();
    extra = ` · 角标 <code>cN</code> 与报告引用对应；报告内点 <code>[cN]</code> 会定位到此卡片，${escapeHtml(mod)}+点击打开原文`;
  }
  hint.innerHTML = `卡片默认收起，只显示标题与摘要；点击标题展开后可分块查看原文、热评与模拟${extra}。`;
}

function updateAskInteractionHint(visible) {
  const el = document.getElementById("ask-interaction-hint");
  if (!el) return;
  if (!visible) {
    el.classList.add("hidden");
    return;
  }
  const mod = modKeyLabel();
  el.classList.remove("hidden");
  el.innerHTML = `<p class="interaction-hint interaction-hint-compact" role="note">追问回答中的 <code>[cN]</code> 同样可点击定位；${escapeHtml(mod)}+点击打开原文。</p>`;
}

function initWorkspaceInteractionTips() {
  const tips = document.getElementById("workspace-interaction-tips");
  if (!tips) return;
  const mod = modKeyLabel();
  tips.innerHTML = tips.innerHTML.replace(/Ctrl\/⌘/g, mod);
}

function renderMarkdown(el, text) {
  if (!el || text == null) return;
  el.classList.add("markdown-body");
  const raw = String(text);
  if (typeof marked !== "undefined") {
    if (typeof marked.setOptions === "function") {
      marked.setOptions({ breaks: true, gfm: true });
    }
    const html = marked.parse(raw);
    el.innerHTML =
      typeof DOMPurify !== "undefined" ? DOMPurify.sanitize(html) : html.replace(/<script[\s\S]*?<\/script>/gi, "");
  } else {
    el.textContent = raw;
  }
}

function buildCitationUrlMap(items, citationUrls = {}) {
  const map = {};
  if (citationUrls && typeof citationUrls === "object") {
    for (const [cid, url] of Object.entries(citationUrls)) {
      const safe = safeHref(url);
      if (safe) map[cid] = safe;
    }
  }
  for (const item of items || []) {
    const cid = item?.personal?.citation_id;
    if (!cid) continue;
    const url = safeHref(item.url);
    if (url) map[cid] = url;
  }
  return map;
}

function citationUrlFromCard(card) {
  if (!card) return "";
  const dataUrl = card.getAttribute("data-item-url");
  if (dataUrl) return safeHref(dataUrl);
  const a = card.querySelector(
    ".item-card-quick-actions a[href], .item-card-body .actions a[href][target='_blank']"
  );
  return safeHref(a?.getAttribute("href") || a?.href || "");
}

function resolveCitationUrl(cid, citationMap = {}) {
  const map =
    citationMap && Object.keys(citationMap).length ? citationMap : mergedCitationMap();
  if (map[cid]) return map[cid];
  const item = (workspaceSession.searchItems || []).find(
    (i) => String(i?.personal?.citation_id || "") === cid
  );
  const fromItem = safeHref(item?.url);
  if (fromItem) return fromItem;
  return citationUrlFromCard(findCitationCard(cid));
}

function highlightCitationCard(card) {
  if (!card) return;
  requestAnimationFrame(() => {
    card.scrollIntoView({ behavior: "smooth", block: "center" });
    card.classList.add("is-expanded", "citation-highlight");
    card.classList.remove("is-collapsed");
    const header = card.querySelector(".item-card-header");
    if (header) header.setAttribute("aria-expanded", "true");
    setTimeout(() => card.classList.remove("citation-highlight"), 2200);
  });
}

function anchorReportReadingList(reportEl) {
  if (!reportEl) return;
  reportEl.querySelectorAll("li, p, tr").forEach((el) => {
    if (el.id && el.id.startsWith("citation-")) return;
    const text = el.textContent || "";
    const m = text.match(/\[c(\d+)\]/i);
    if (m) el.id = `citation-c${m[1]}`;
  });
}

function findCitationCard(cid) {
  if (!cid) return null;
  return document.querySelector(`[data-citation-id="${cid}"]`);
}

function ensureResultsVisibleForCitation() {
  const layout = document.querySelector(".results-layout");
  const splitCb = document.getElementById("workspace-split-view");
  if (!layout) return;
  document.body.classList.remove("reading-focus");
  const researchPanel = document.getElementById("workspace-panel-research");
  if (researchPanel && !researchPanel.classList.contains("hidden")) {
    switchWorkspacePanel("results");
  }
  const wide = window.matchMedia("(min-width: 1281px)").matches;
  if (wide && splitCb) {
    if (!splitCb.checked) {
      splitCb.checked = true;
      /* 点击引用时临时分屏对照，不写入 localStorage，刷新后仍默认不分屏 */
    }
    applyWorkspaceSplitLayout();
    return;
  }
  switchWorkspacePanel("results");
}

function revealCitationInResults(cid, resultsRoot) {
  let card = findCitationCard(cid);
  let guard = 0;
  while (!card && guard < 24) {
    const more = resultsRoot?.querySelector("[data-load-more-results]:not(.hidden)");
    if (!more) break;
    more.click();
    card = findCitationCard(cid);
    guard += 1;
  }
  return card;
}

function scrollToCitationTarget(cid, { reportEl, resultsRoot, citationMap = {} } = {}) {
  if (!cid) return { ok: false, mode: "missing" };
  const map =
    citationMap && Object.keys(citationMap).length ? citationMap : mergedCitationMap();
  ensureResultsVisibleForCitation();
  const root = resultsRoot || document.getElementById("search-results");
  const url = resolveCitationUrl(cid, map);

  const card = revealCitationInResults(cid, root);
  if (card) {
    highlightCitationCard(card);
    return { ok: true, mode: "card", url: url || citationUrlFromCard(card) };
  }

  const readingAnchor = reportEl?.querySelector(`#citation-${cid}`);
  if (readingAnchor) {
    readingAnchor.scrollIntoView({ behavior: "smooth", block: "center" });
    readingAnchor.classList.add("citation-highlight");
    setTimeout(() => readingAnchor.classList.remove("citation-highlight"), 2200);
    return { ok: true, mode: "reading_list", url };
  }

  if (url) {
    return { ok: true, mode: "url_only", url };
  }
  return { ok: false, mode: "not_found" };
}

function handleCitationClick(ev) {
  const link = ev.target.closest(".citation-ref");
  if (!link) return;
  const cid = link.dataset.citationRef;
  if (!cid) return;
  ev.preventDefault();
  const map = mergedCitationMap();
  const reportEl = link.closest("#report-panel, .ask-turn") || document.getElementById("report-panel");
  const opts = {
    reportEl,
    resultsRoot: document.getElementById("search-results"),
    citationMap: map,
  };
  const modifier = ev.metaKey || ev.ctrlKey || ev.shiftKey;

  if (modifier) {
    const url = resolveCitationUrl(cid, map);
    if (url) {
      window.open(url, "_blank", "noopener");
      return;
    }
    const result = scrollToCitationTarget(cid, opts);
    if (result.ok) {
      showToast(`已定位到 ${cid}（该条暂无外链）`, "info");
      return;
    }
    showToast(`未找到引用 ${cid} 对应条目或原文`, "warn");
    return;
  }

  const result = scrollToCitationTarget(cid, opts);
  if (!result.ok) {
    showToast(`未找到引用 ${cid} 对应条目或原文`, "warn");
    return;
  }
  if (result.mode === "url_only" && result.url) {
    window.open(result.url, "_blank", "noopener");
  }
}

function wireCitationLinks(reportEl, resultsRoot, citationMap = {}) {
  if (!reportEl) return;
  anchorReportReadingList(reportEl);
  const host = resultsRoot?.querySelector(".item-card-list") || resultsRoot;
  const walker = document.createTreeWalker(reportEl, NodeFilter.SHOW_TEXT);
  const textNodes = [];
  while (walker.nextNode()) textNodes.push(walker.currentNode);
  const pattern = /\[c(\d+)\]/gi;
  for (const node of textNodes) {
    const parent = node.parentElement;
    if (!parent || parent.closest(".citation-ref, a")) continue;
    const raw = node.textContent || "";
    if (!pattern.test(raw)) continue;
    pattern.lastIndex = 0;
    const frag = document.createDocumentFragment();
    let last = 0;
    let match;
    while ((match = pattern.exec(raw)) !== null) {
      if (match.index > last) frag.appendChild(document.createTextNode(raw.slice(last, match.index)));
      const cid = `c${match[1]}`;
      const link = document.createElement("a");
      link.href = `#citation-${cid}`;
      link.className = "citation-ref";
      link.dataset.citationRef = cid;
      const linkUrl = resolveCitationUrl(cid, citationMap);
      link.title = citationLinkTitle(linkUrl);
      link.textContent = match[0];
      link.addEventListener("click", handleCitationClick);
      frag.appendChild(link);
      last = match.index + match[0].length;
    }
    if (last < raw.length) frag.appendChild(document.createTextNode(raw.slice(last)));
    parent.replaceChild(frag, node);
  }
  if (!host) return;
  void host;
}

function showToast(message, kind = "info") {
  let host = document.getElementById("toast-host");
  if (!host) {
    host = document.createElement("div");
    host.id = "toast-host";
    host.className = "toast-host";
    document.body.appendChild(host);
  }
  const el = document.createElement("div");
  el.className = `toast toast-${kind}`;
  el.textContent = message;
  host.appendChild(el);
  requestAnimationFrame(() => el.classList.add("show"));
  setTimeout(() => {
    el.classList.remove("show");
    setTimeout(() => el.remove(), 320);
  }, 3200);
}

function feedbackLabel(base, active) {
  return active ? `${base} ✓` : base;
}

function feedbackBtnClass(active, base = "btn btn-sm btn-ghost") {
  return active ? `${base} is-active` : base;
}

async function loadFeedbackMap(itemIds) {
  if (!itemIds.length) return {};
  try {
    const data = await api(
      "GET",
      `/api/feedback/recent?target_ids=${encodeURIComponent(itemIds.join(","))}`
    );
    return data.feedback || {};
  } catch (_) {
    return {};
  }
}

function setFeedbackActive(card, targetType, rating) {
  const attr = targetType === "simulation" ? "data-sim-feedback" : "data-feedback";
  card.querySelectorAll(`[${attr}]`).forEach((btn) => {
    const val = targetType === "simulation" ? btn.dataset.simFeedback : btn.dataset.feedback;
    const active = val === rating;
    btn.classList.toggle("is-active", active);
    const base = btn.dataset.baseLabel || btn.textContent.replace(/ ✓$/, "");
    btn.dataset.baseLabel = base;
    btn.textContent = feedbackLabel(base, active);
  });
}

function teaserPlain(text, maxLen = 140) {
  const plain = String(text || "")
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/[#>*_\[\]`]/g, "")
    .replace(/\s+/g, " ")
    .trim();
  if (!plain) return "";
  return plain.length > maxLen ? `${plain.slice(0, maxLen - 3)}…` : plain;
}

function itemCardTeaser(item) {
  if (item.summary) {
    const t = teaserPlain(item.summary, 140);
    if (t) return t;
  }
  if (item.layers?.comments_summary) {
    const t = teaserPlain(item.layers.comments_summary, 140);
    if (t) return t;
  }
  const raw = (item.content || item.layers?.subtitle?.text || "").trim();
  if (raw) {
    const oneLine = raw.replace(/\s+/g, " ");
    return oneLine.length > 120 ? `${oneLine.slice(0, 117)}…` : oneLine;
  }
  if (item.key_points?.[0]) {
    return teaserPlain(item.key_points[0], 120);
  }
  if (item.source === "bilibili" && item.type === "video") {
    return "简介较短；展开可查看热评归纳或字幕（需 Cookie / 开启评论挖掘）";
  }
  return "点击展开查看详情";
}

function knowledgeLinkage(item) {
  return item?.personal?.knowledge_linkage || null;
}

function shortKnowledgeProjectLabel(project) {
  const text = String(project || "").trim();
  if (!text) return "";
  return text.length > 10 ? `${text.slice(0, 10)}…` : text;
}

function itemSectionFlags(item, sim) {
  const flags = [];
  if (item.summary || item.key_points?.length) flags.push("摘要");
  if (item.layers?.comments_summary) flags.push("观点");
  const raw = (item.content || item.layers?.subtitle?.text || "").trim();
  if (raw) flags.push("原文");
  if (item.source === "bilibili" && item.type === "video") {
    const subtitleText = String(item.layers?.subtitle?.text || "").trim();
    const subtitleReason = String(item.layers?.subtitle?.reason || "").trim();
    if (subtitleText) {
      flags.push("已识别字幕");
    } else if (subtitleReason === "no_tracks") {
      flags.push("无字幕");
    } else if (subtitleReason) {
      flags.push({ label: "字幕失败", title: formatBilibiliSubtitleReason(subtitleReason) });
    }
  }
  if (item.layers?.comments?.length) flags.push(`热评 ${item.layers.comments.length}`);
  if (sim && !sim.raw) flags.push("模拟");
  const linkage = knowledgeLinkage(item);
  if (linkage?.known_url) flags.push("库中已有");
  else if (linkage?.supplements_existing) flags.push("补充旧知识");
  if (linkage?.project) flags.push({ label: `项目 ${shortKnowledgeProjectLabel(linkage.project)}`, title: linkage.project });
  if (linkage?.persona_overlap?.length) {
    flags.push({ label: "贴合画像", title: linkage.persona_overlap.join("；") });
  }
  return flags;
}

function formatBilibiliSubtitleReason(reason) {
  const value = String(reason || "").trim();
  if (!value) return "字幕抓取失败";
  if (value === "aid_cid_unresolved") return "字幕抓取失败：未能解析该视频的 aid/cid";
  if (value === "no_subtitle_url") return "字幕抓取失败：字幕轨未返回可下载地址";
  if (value === "empty_subtitle_file") return "字幕抓取失败：字幕文件为空";
  if (value === "no_tracks") return "该视频未提供 CC/AI 字幕轨";
  if (value.startsWith("wbi_player_error:")) {
    return `字幕抓取失败：WBI player 接口异常（${value.split(":").slice(1).join(":") || "unknown"}）`;
  }
  if (value.startsWith("player_v2_error:")) {
    return `字幕抓取失败：player_v2 接口异常（${value.split(":").slice(1).join(":") || "unknown"}）`;
  }
  return `字幕抓取失败：${value}`;
}

function formatRelevanceBadge(item) {
  const rel = Number(item.signals?.relevance);
  if (Number.isNaN(rel)) return '<span class="relevance-badge">—</span>';
  const pct = Math.round(Math.max(0, Math.min(1, rel)) * 100);
  let tier = "low";
  if (pct >= 70) tier = "high";
  else if (pct >= 45) tier = "mid";
  return `<span class="relevance-badge relevance-${tier}" title="相关度">${pct}%</span>`;
}

function initItemCardInteractions(container) {
  container.querySelectorAll(".item-card").forEach((card) => {
    const header = card.querySelector(".item-card-header");
    if (!header || header.dataset.bound === "1") return;
    header.dataset.bound = "1";
    const toggle = () => {
      const expanded = card.classList.toggle("is-expanded");
      card.classList.toggle("is-collapsed", !expanded);
      header.setAttribute("aria-expanded", expanded ? "true" : "false");
      if (expanded) {
        const host = card.closest("#search-results") || card.parentElement;
        const item = host?._itemsById?.[card.dataset.itemId];
        hydrateItemCardMarkdown(card, item);
      }
    };
    header.addEventListener("click", (ev) => {
      if (ev.target.closest(".item-card-quick-actions, .item-card-body, a, button")) return;
      toggle();
    });
    header.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter" || ev.key === " ") {
        ev.preventDefault();
        toggle();
      }
    });
  });
}

function bindResultsToolbar(container, runId) {
  const expandBtn = container.querySelector("[data-expand-all]");
  const collapseBtn = container.querySelector("[data-collapse-all]");
  const cardsHost = container.querySelector(".item-card-list");
  if (!cardsHost) return;
  const setAll = (expanded) => {
    cardsHost.querySelectorAll(".item-card").forEach((card) => {
      if (card.style.display === "none") return;
      card.classList.toggle("is-expanded", expanded);
      card.classList.toggle("is-collapsed", !expanded);
      const header = card.querySelector(".item-card-header");
      if (header) header.setAttribute("aria-expanded", expanded ? "true" : "false");
      if (expanded) {
        const item = container._itemsById?.[card.dataset.itemId];
        hydrateItemCardMarkdown(card, item);
      }
    });
  };
  expandBtn?.addEventListener("click", () => setAll(true));
  collapseBtn?.addEventListener("click", () => setAll(false));

  const filterHost = container.querySelector("[data-intel-filter]");
  const sourceFilterHost = container.querySelector("[data-source-filter]");
  const countEl = container.querySelector(".results-toolbar-count");
  let activeIntelFilter = "all";
  let activeSourceFilter = "all";

  const applyResultFilters = () => {
    cardsHost.querySelectorAll(".item-card").forEach((card) => {
      const seen = card.dataset.alreadySeen === "1";
      const src = card.dataset.itemSource || "";
      const intelOk =
        activeIntelFilter === "all"
        || (activeIntelFilter === "new" && !seen)
        || (activeIntelFilter === "seen" && seen);
      const sourceOk = activeSourceFilter === "all" || src === activeSourceFilter;
      card.style.display = intelOk && sourceOk ? "" : "none";
    });
    updateVisibleCount();
  };

  const updateVisibleCount = () => {
    if (!countEl) return;
    const total = cardsHost.querySelectorAll(".item-card").length;
    const visible = [...cardsHost.querySelectorAll(".item-card")].filter((c) => c.style.display !== "none").length;
    const suffix = visible < total ? `（显示 ${visible}/${total}）` : "";
    countEl.textContent = `${total} 条结果${suffix} · 默认收起，点击标题展开`;
  };
  filterHost?.querySelectorAll("[data-filter]").forEach((btn) => {
    btn.addEventListener("click", () => {
      activeIntelFilter = btn.dataset.filter || "all";
      filterHost.querySelectorAll("[data-filter]").forEach((b) => b.classList.toggle("is-active", b === btn));
      applyResultFilters();
    });
  });
  sourceFilterHost?.querySelectorAll("[data-source-filter]").forEach((btn) => {
    btn.addEventListener("click", () => {
      activeSourceFilter = btn.dataset.sourceFilter || "all";
      sourceFilterHost.querySelectorAll("[data-source-filter]").forEach((b) => b.classList.toggle("is-active", b === btn));
      applyResultFilters();
    });
  });
  container._applyResultFilters = applyResultFilters;
  applyResultFilters();

  const saveBtn = container.querySelector("[data-save-run-items]");
  saveBtn?.addEventListener("click", async () => {
    if (!runId) return;
    saveBtn.disabled = true;
    try {
      const data = await api("POST", `/api/search/${encodeURIComponent(runId)}/save-items`, {});
      showToast(`已收录 ${data.saved_count ?? 0} 条到知识库`, "info");
    } catch (err) {
      showToast(err.message || "批量收录失败", "error");
    } finally {
      saveBtn.disabled = false;
    }
  });
}

function countItemsBySource(items) {
  const counts = {};
  for (const item of items || []) {
    const s = item.source || "other";
    counts[s] = (counts[s] || 0) + 1;
  }
  return counts;
}

function renderResultsToolbar(count, intelStats = {}, sourceCounts = {}) {
  const newCount = Number(intelStats.new_count) || 0;
  const seenCount = Number(intelStats.seen_count) || 0;
  const sourceEntries = Object.entries(sourceCounts).sort((a, b) => b[1] - a[1]);
  const sourceChips = sourceEntries.length > 1
    ? `<div class="ui-segmented source-filter-chips" data-source-filter title="按信源筛选结果">
        <button type="button" class="btn btn-sm btn-ghost is-active" data-source-filter="all">全部信源</button>
        ${sourceEntries.map(([sid, n]) => `<button type="button" class="btn btn-sm btn-ghost source-chip-${escapeHtml(sid)}" data-source-filter="${escapeHtml(sid)}" title="${escapeHtml(sourceLabel(sid))}">${escapeHtml(sourceLabel(sid))}${n ? ` (${n})` : ""}</button>`).join("")}
      </div>`
    : "";
  return `<div class="results-toolbar results-toolbar-sticky">
    <span class="muted results-toolbar-count">${count} 条结果 · 默认收起，点击标题展开</span>
    <div class="results-toolbar-actions">
      ${sourceChips}
      <div class="ui-segmented intel-filter-chips" data-intel-filter title="按是否在本话题历史中见过筛选">
        <button type="button" class="btn btn-sm btn-ghost is-active" data-filter="all" title="显示全部结果">全部</button>
        <button type="button" class="btn btn-sm btn-ghost" data-filter="new" title="仅显示本轮首次见到的条目">本轮新增${newCount ? ` (${newCount})` : ""}</button>
        <button type="button" class="btn btn-sm btn-ghost" data-filter="seen" title="仅显示历史中已见过的条目">已见过${seenCount ? ` (${seenCount})` : ""}</button>
      </div>
      <button type="button" class="btn btn-sm btn-secondary" data-save-run-items title="将本轮标记为有用的条目批量写入知识库">收录本轮精选</button>
      <button type="button" class="btn btn-sm btn-ghost" data-expand-all title="展开所有结果卡片正文">全部展开</button>
      <button type="button" class="btn btn-sm btn-ghost" data-collapse-all title="收起所有结果卡片，仅保留标题摘要">全部收起</button>
    </div>
  </div>`;
}

function formatCommentsSection(comments) {
  if (!comments?.length) return "";
  const rows = comments
    .slice(0, 10)
    .map(
      (c) => {
        let html = `<div class="comment-row">
      <div class="comment-meta">${escapeHtml(c.author || "匿名")} · 👍 ${Number(c.likes) || 0}</div>
      <div class="comment-text">${escapeHtml(c.content || "")}</div>`;
        const replies = c.replies;
        if (replies?.length) {
          const top = replies.slice(0, 5);
          html += `<details class="comment-replies"><summary>${replies.length} 条回复</summary>`;
          html += top.map(
            (r) => `<div class="comment-child-row">
          <div class="comment-meta">${escapeHtml(r.author || "匿名")} · 👍 ${Number(r.likes) || 0}</div>
          <div class="comment-text">${escapeHtml(r.content || "")}</div>
        </div>`
          ).join("");
          if (replies.length > 5) {
            html += `<div class="muted" style="padding:4px 0 0 20px">… 还有 ${replies.length - 5} 条回复</div>`;
          }
          html += `</details>`;
        }
        html += `</div>`;
        return html;
      }
    )
    .join("");
  return `<details class="item-section item-section-comments" open>
    <summary class="item-section-summary">原始热评 <span class="muted">(${comments.length})</span></summary>
    <div class="item-section-body">
      <div class="comments-list">${rows}</div>
    </div>
  </details>`;
}

function bilibiliShortRawHint(item, rawText) {
  if (item.source !== "bilibili" || item.type !== "video") return "";
  const short = String(rawText || "").trim().length <= 120 && !String(rawText || "").includes("\n\n");
  if (!short) return "";
  const hasComments = item.layers?.comments?.length || item.layers?.comments_summary;
  const hasSubtitle = Boolean(item.layers?.subtitle?.text);
  if (hasComments || hasSubtitle) return "";
  const reason = item.layers?.subtitle?.reason;
  const reasonHint =
    reason === "no_tracks"
      ? "该视频可能未开启 CC/AI 字幕"
      : reason
        ? `字幕未获取（${reason}）`
        : "未拉取字幕";
  return `<p class="muted section-hint">B 站简介通常较短；${reasonHint}。请勾选「挖掘 B 站热评」并在<a href="/settings">设置</a>同步 B 站 Cookie 后重试。</p>`;
}

function bilibiliRawContent(item) {
  const content = String(item?.content || "").trim();
  const subtitleText = String(item?.layers?.subtitle?.text || "").trim();
  if (item?.source !== "bilibili" || item?.type !== "video") {
    return content || subtitleText;
  }
  if (!subtitleText) return content;
  if (!content) return `[字幕]\n${subtitleText}`;
  if (content.includes(subtitleText)) return content;
  return `${content}\n\n[字幕]\n${subtitleText}`;
}

function hydrateItemCardMarkdown(card, item) {
  if (!item || card.dataset.mdHydrated === "1") return;
  card.dataset.mdHydrated = "1";
  const raw = card.querySelector(".raw-body");
  const rawText = bilibiliRawContent(item).trim();
  if (raw && rawText) renderMarkdown(raw, rawText);
  const summary = card.querySelector(".summary-body");
  if (summary && item.summary) renderMarkdown(summary, item.summary);
  const cs = card.querySelector(".comments-summary-body");
  if (cs && item.layers?.comments_summary) renderMarkdown(cs, item.layers.comments_summary);
}

function hydrateItemCards(container, items) {
  const byId = Object.fromEntries(items.map((i) => [i.id, i]));
  container._itemsById = { ...(container._itemsById || {}), ...byId };
  container.querySelectorAll(".item-card[data-item-id]").forEach((card) => {
    const item = container._itemsById[card.dataset.itemId];
    if (!item) return;
    if (card.classList.contains("is-expanded")) hydrateItemCardMarkdown(card, item);
  });
}

const API_TIMEOUT_MS = 12000;
let _apiPrewarmPromise = null;

async function prewarmApiToken() {
  if (_apiPrewarmPromise) return _apiPrewarmPromise;
  _apiPrewarmPromise = fetch("/api/health", { credentials: "same-origin" })
    .then((res) => res.ok)
    .catch(() => false)
    .finally(() => {
      setTimeout(() => {
        _apiPrewarmPromise = null;
      }, 1500);
    });
  return _apiPrewarmPromise;
}

function friendlyApiError(err, url = "") {
  const msg = String(err?.message || err || "");
  if (err?.name === "AbortError") {
    return new Error("请求超时，后台可能正忙。请稍后重试，或先检查情报台是否仍在运行。");
  }
  if (err instanceof TypeError || /failed to fetch|networkerror|load failed/i.test(msg)) {
    return new Error("无法连接本机情报台服务。请确认“启动情报台.bat”已经运行，并刷新页面重试。");
  }
  if (/forbidden|403/i.test(msg)) {
    return new Error("页面授权还没就绪。请刷新页面；若仍失败，请重新启动情报台。");
  }
  if (url.includes("/knowledge/")) {
    return new Error(msg || "知识库请求失败。请查看知识诊断条里的修复建议。");
  }
  return err instanceof Error ? err : new Error(msg || "请求失败");
}

async function api(method, url, body, options = {}) {
  const timeoutMs = options.timeoutMs ?? API_TIMEOUT_MS;
  const retry = Number(options.retry ?? 0);
  const prewarm = options.prewarm === true;
  if (prewarm) await prewarmApiToken();
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  const headers = { "Content-Type": "application/json" };
  const token = getWebToken();
  if (token) headers["X-Osint-Token"] = token;
  const opts = { method, headers, credentials: "same-origin", signal: controller.signal };
  if (body) opts.body = JSON.stringify(body);
  try {
    const res = await fetch(url, opts);
    const data = await res.json().catch(() => ({}));
    if (res.status === 403 && retry > 0) {
      await prewarmApiToken();
      return api(method, url, body, { ...options, retry: retry - 1, prewarm: false });
    }
    if (!res.ok) throw new Error(data.detail || res.statusText);
    return data;
  } catch (err) {
    if (retry > 0 && err?.name !== "AbortError") {
      await new Promise((resolve) => setTimeout(resolve, 350));
      return api(method, url, body, { ...options, retry: retry - 1, prewarm: false });
    }
    throw friendlyApiError(err, url);
  } finally {
    clearTimeout(timer);
  }
}

let _shellCache = null;
let _shellCacheAt = 0;
const SHELL_CACHE_TTL_MS = 4000;

async function getShellStatus(force = false) {
  if (!force && _shellCache && Date.now() - _shellCacheAt < SHELL_CACHE_TTL_MS) {
    return _shellCache;
  }
  const [extension, setup, jobs] = await Promise.all([
    api("GET", "/api/extension/status?lite=1", null, { timeoutMs: 5000 }).catch(() => ({ connected: false })),
    api("GET", "/api/setup/status", null, { timeoutMs: 8000 }).catch(() => null),
    api("GET", "/api/jobs/active", null, { timeoutMs: 3000 }).catch(() => ({ jobs: [] })),
  ]);
  _shellCache = { extension, setup, jobs };
  _shellCacheAt = Date.now();
  return _shellCache;
}

function invalidateShellCache() {
  _shellCache = null;
}

function showAlert(container, message, type = "warn") {
  const el = document.createElement("div");
  el.className = `alert alert-${type}`;
  el.textContent = message;
  container.prepend(el);
  setTimeout(() => el.remove(), 8000);
}

function showPageNotice(noticeId, message, kind = "success") {
  const el = document.getElementById(noticeId);
  if (!el) return;
  el.className = `alert alert-${kind} page-notice`;
  el.innerHTML = message;
  el.classList.remove("hidden");
  setTimeout(() => el.classList.add("hidden"), 10000);
}

const EVENT_TYPE_LABELS = {
  browser_visit: "浏览",
  ext_page_dwell: "高停留",
  ext_auto_save: "自动收录",
  bilibili_like: "B站点赞",
  bilibili_fav: "B站收藏",
  bilibili_favorite: "B站收藏",
  bilibili_watch: "B站观看",
  bilibili_coin: "B站投币",
  bilibili_comment_post: "B站发评",
  bilibili_comment_like: "B站评论赞",
  zhihu_vote: "知乎赞同",
  zhihu_fav: "知乎收藏",
  zhihu_favorite: "知乎收藏",
  zhihu_browse: "知乎浏览",
  github_star: "GitHub Star",
  extension_flush: "扩展上报",
};

const PERSONA_BEHAVIOR_CATEGORY_LABELS = {
  browse: "浏览发现",
  dwell: "深度阅读",
  watch: "观看",
  endorse: "点赞/赞同",
  save: "收藏/收录",
  publish: "发布/互动",
  inventory: "账号库存",
  other: "其他行为",
};

const CAPABILITY_STATUS_LABELS = {
  supported: "完整支持",
  partial: "需扩展配合",
};

const EXT_EVENT_LABELS = {
  page_view: "页面浏览",
  dwell: "停留",
  bilibili_like: "B站点赞",
  zhihu_vote: "知乎赞同",
};

const AUTH_FIX_LINKS = {
  bilibili: "/settings",
  zhihu: "/settings",
  deepseek: "/settings#deps",
};

function formatEventType(type) {
  return EVENT_TYPE_LABELS[type] || type || "—";
}

function formatBehaviorCategory(category) {
  return PERSONA_BEHAVIOR_CATEGORY_LABELS[category] || category || "其他行为";
}

function formatCapabilityStatus(status) {
  return CAPABILITY_STATUS_LABELS[status] || status;
}

async function refreshMobileStatusBar() {
  const bar = document.getElementById("mobile-status-bar");
  if (!bar || !window.matchMedia("(max-width: 960px)").matches) {
    bar?.classList.add("hidden");
    return;
  }
  const parts = [];
  try {
    const { extension, setup, jobs } = await getShellStatus();
    parts.push(
      extension?.connected
        ? (extension.pending_queue > 0
            ? `扩展待上传 ${extension.pending_queue} 条`
            : "扩展已连接")
        : '<a href="/ingest#extension">扩展未连接</a>',
    );
    const running = jobs?.jobs || [];
    if (running.length) {
      const j = running[0];
      const label =
        j.kind === "search"
          ? `搜罗进行中${j.progress?.percent != null ? ` ${Math.round(j.progress.percent)}%` : ""}`
          : j.kind === "full_sync"
            ? "完整同步中"
            : "后台任务中";
      parts.push(`<a href="${j.kind === "search" ? `/?run=${encodeURIComponent(j.job_id)}` : "/ingest"}">${escapeHtml(label)}</a>`);
    }
    if (setup && !setup.ready && !setup.dismissed) {
      const done = (setup.steps || []).filter((s) => s.done).length;
      parts.push(`<a href="/settings">入门 ${done}/${(setup.steps || []).length}</a>`);
    }
  } catch (_) {
    parts.push("Web 未就绪");
  }
  if (!parts.length) {
    bar.classList.add("hidden");
    return;
  }
  bar.innerHTML = parts.join(" · ");
  bar.classList.remove("hidden");
}

async function initGlobalSidebar() {
  const extChip = document.getElementById("sidebar-extension-chip");
  let extResolved = false;
  const extWatchdog = extChip
    ? setTimeout(() => {
        if (extResolved) return;
        if ((extChip.textContent || "").includes("检测中")) {
          extChip.textContent = "扩展状态超时";
          extChip.classList.add("warn");
        }
      }, 8000)
    : null;
  if (extChip) {
    try {
      const { extension } = await getShellStatus();
      const data = extension || { connected: false };
      if (data.connected) {
        const pending = data.pending_queue || 0;
        extChip.textContent = pending > 0 ? `扩展 ● 待上传 ${pending}` : "扩展 ● 已连接";
        extChip.classList.toggle("warn", pending > 0);
        extChip.classList.toggle("ok", pending === 0);
      } else {
        extChip.innerHTML = `扩展 ○ 未连接 · <a href="/ingest#extension">安装</a>`;
        extChip.classList.add("warn");
      }
    } catch (_) {
      extChip.textContent = "扩展状态未知";
    } finally {
      extResolved = true;
      if (extWatchdog) clearTimeout(extWatchdog);
    }
  }
  const setupChip = document.getElementById("sidebar-setup-chip");
  if (setupChip) {
    try {
      const { setup } = await getShellStatus();
      const data = setup;
      if (!data || data.ready || data.dismissed) {
        setupChip.classList.add("hidden");
      } else {
        const done = (data.steps || []).filter((s) => s.done).length;
        const total = (data.steps || []).length;
        setupChip.classList.remove("hidden");
        setupChip.innerHTML = `入门 <a href="/settings">${done}/${total}</a>`;
      }
    } catch (_) {}
  }
  pollActiveJobs();
  if (sidebarPollTimer) clearInterval(sidebarPollTimer);
  sidebarPollTimer = setInterval(() => {
    void pollSidebarShell();
  }, 5000);
  void refreshMobileStatusBar();
}

async function pollSidebarShell() {
  if (document.visibilityState === "hidden") return;
  invalidateShellCache();
  await pollActiveJobs();
  void refreshMobileStatusBar();
  if (document.getElementById("search-task-list")) {
    void refreshSearchTaskList();
  }
}

function initSidebarPollVisibility() {
  if (window._osintSidebarPollVisibilityBound) return;
  window._osintSidebarPollVisibilityBound = true;
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      if (sidebarPollTimer) {
        clearInterval(sidebarPollTimer);
        sidebarPollTimer = null;
      }
      stopSearchTaskPolling();
    } else {
      void pollSidebarShell();
      if (!sidebarPollTimer) {
        sidebarPollTimer = setInterval(() => {
          void pollSidebarShell();
        }, 5000);
      }
    }
  });
}

function syncSplitPanelAccessibility() {
  const layout = document.querySelector(".results-layout");
  if (!layout) return;
  const activePanel =
    [...layout.classList].find((c) => c.startsWith("panel-"))?.replace("panel-", "") || "results";
  const splitOn = layout.classList.contains("workspace-split");
  const panels = {
    results: layout.querySelector(".results-panel"),
    report: layout.querySelector(".report-panel-wrap"),
    research: layout.querySelector(".research-panel-wrap"),
  };

  if (splitOn && (activePanel === "results" || activePanel === "report")) {
    ["results", "report"].forEach((key) => {
      const el = panels[key];
      if (!el) return;
      el.setAttribute("aria-hidden", "false");
      el.removeAttribute("inert");
    });
    const researchEl = panels.research;
    if (researchEl) {
      researchEl.setAttribute("aria-hidden", "true");
      researchEl.setAttribute("inert", "");
    }
    return;
  }

  Object.entries(panels).forEach(([key, el]) => {
    if (!el) return;
    const hidden = key !== activePanel;
    el.setAttribute("aria-hidden", hidden ? "true" : "false");
    if (hidden) {
      el.setAttribute("inert", "");
    } else {
      el.removeAttribute("inert");
    }
  });
}

function updateReportTabSplitHint() {
  const reportTab = document.querySelector('.workspace-panel-tab[data-panel="report"]');
  const cb = document.getElementById("workspace-split-view");
  if (!reportTab) return;
  const wide = window.matchMedia("(min-width: 1281px)").matches;
  const splitOn = wide && cb?.checked;
  reportTab.title = splitOn
    ? "分屏已显示报告；点此全宽阅读并打开追问"
    : "查看 AI 情报报告与追问";
}

function switchWorkspacePanel(panel) {
  const layout = document.querySelector(".results-layout");
  const tabs = document.querySelector(".workspace-panel-tabs");
  if (!layout || !tabs) return;
  const name = panel || "results";
  layout.classList.remove("panel-results", "panel-report", "panel-research");
  layout.classList.add(`panel-${name}`);
  tabs.querySelectorAll(".workspace-panel-tab").forEach((btn) => {
    const active = btn.dataset.panel === name;
    btn.classList.toggle("active", active);
    btn.setAttribute("aria-selected", active ? "true" : "false");
  });
  try {
    localStorage.setItem("workspacePanel", name);
  } catch (_) {}
  applyWorkspaceSplitLayout();
}

function applyWorkspaceSplitLayout() {
  const layout = document.querySelector(".results-layout");
  const cb = document.getElementById("workspace-split-view");
  if (!layout || !cb) return;
  const splitOn = isWorkspaceSplitActive();
  layout.classList.toggle("workspace-split", splitOn);
  syncSplitPanelAccessibility();
  updateSplitControlState();
  const reportEl = document.getElementById("report-panel");
  if (reportEl?.dataset?.rawMarkdown) {
    updateReportInteractionHint(reportEl, true);
  }
}

function initWorkspaceSplitToggle() {
  const cb = document.getElementById("workspace-split-view");
  const wrap = document.getElementById("workspace-split-wrap");
  if (!cb) return;
  try {
    /* 默认不分屏；仅用户曾勾选并保存 workspaceSplit=1 时恢复 */
    cb.checked = localStorage.getItem("workspaceSplit") === "1";
  } catch (_) {
    cb.checked = false;
  }
  const mq = window.matchMedia("(min-width: 1281px)");
  function onChange() {
    if (wrap) wrap.style.display = mq.matches ? "" : "none";
    applyWorkspaceSplitLayout();
  }
  cb.addEventListener("change", () => {
    if (cb.checked && !isWorkspaceSplitWide()) {
      cb.checked = false;
      showToast("对照分屏需要较宽窗口（≥1280px）", "info");
      applyWorkspaceSplitLayout();
      return;
    }
    try {
      localStorage.setItem("workspaceSplit", cb.checked ? "1" : "0");
    } catch (_) {}
    applyWorkspaceSplitLayout();
  });
  mq.addEventListener("change", onChange);
  onChange();
}

function initWorkspacePanelTabs() {
  const tabs = document.querySelector(".workspace-panel-tabs");
  if (!tabs) return;

  const segmented = tabs.querySelector(".ui-segmented") || tabs;
  const panelIds = { results: "workspace-panel-results", report: "workspace-panel-report", research: "workspace-panel-research" };
  const tabButtons = [...tabs.querySelectorAll(".workspace-panel-tab")];
  tabButtons.forEach((btn, idx) => {
    const panelId = panelIds[btn.dataset.panel];
    if (panelId) btn.setAttribute("aria-controls", panelId);
    if (!btn.hasAttribute("role")) btn.setAttribute("role", "tab");
    btn.setAttribute("tabindex", btn.classList.contains("active") ? "0" : "-1");
    btn.addEventListener("keydown", (ev) => {
      if (ev.key !== "ArrowLeft" && ev.key !== "ArrowRight") return;
      ev.preventDefault();
      const next =
        ev.key === "ArrowRight" ? (idx + 1) % tabButtons.length : (idx - 1 + tabButtons.length) % tabButtons.length;
      tabButtons[next].focus();
      switchWorkspacePanel(tabButtons[next].dataset.panel);
    });
  });
  initSegmentedControl(segmented, {
    onSelect: (name) => {
      switchWorkspacePanel(name);
      tabButtons.forEach((btn) => {
        const active = btn.dataset.panel === name;
        btn.setAttribute("tabindex", active ? "0" : "-1");
      });
    },
  });

  let saved = "results";
  try {
    saved = localStorage.getItem("workspacePanel") || "results";
  } catch (_) {}
  switchWorkspacePanel(saved);
}

const workspaceSession = {
  treeId: sessionStorage.getItem("researchTreeId") || null,
  parentNodeId: loadStoredParentNodeId(sessionStorage.getItem("researchTreeId")),
  selectedNodeId: null,
  selectedRunId: sessionStorage.getItem("workspaceCurrentRunId") || null,
  activeRunId: sessionStorage.getItem("activeSearchRunId") || null,
  forkFromRunId: null,
  currentRunId: sessionStorage.getItem("workspaceCurrentRunId") || null,
  currentTree: null,
  citationMap: {},
  citationUrlExtras: {},
  searchItems: [],
};

function parentNodeStorageKey(treeId) {
  return `researchParentNode:${treeId || ""}`;
}

function loadStoredParentNodeId(treeId) {
  if (!treeId) return null;
  try {
    return sessionStorage.getItem(parentNodeStorageKey(treeId));
  } catch (_) {
    return null;
  }
}

function storeParentNodeId(treeId, nodeId) {
  if (!treeId) return;
  try {
    if (nodeId) sessionStorage.setItem(parentNodeStorageKey(treeId), nodeId);
    else sessionStorage.removeItem(parentNodeStorageKey(treeId));
  } catch (_) {}
}

function setWorkspaceParentNodeId(nodeId) {
  workspaceSession.parentNodeId = nodeId || null;
  storeParentNodeId(workspaceSession.treeId, nodeId);
}

function setCurrentRunId(runId) {
  workspaceSession.currentRunId = runId || null;
  if (runId) {
    workspaceSession.selectedRunId = runId;
    sessionStorage.setItem("workspaceCurrentRunId", runId);
  }
}

function getActiveResearchRunId() {
  return workspaceSession.selectedRunId || workspaceSession.currentRunId || "";
}

function pickLatestSearchRunId(tree) {
  const nodes = (tree?.nodes || []).filter(
    (n) => n.kind === "search" && n.run_id && n.meta?.status !== "running",
  );
  if (!nodes.length) return null;
  return nodes[nodes.length - 1].run_id;
}

function insightParentNodeId(runId) {
  const node = workspaceSession.selectedNodeId
    ? findResearchNode(workspaceSession.currentTree, workspaceSession.selectedNodeId)
    : null;
  if (node?.kind === "search" && node.run_id === runId) return node.id;
  const searchId = findResearchNodeByRunId(workspaceSession.currentTree, runId)?.id;
  return searchId || workspaceSession.parentNodeId || null;
}

function findResearchNodeByRunId(tree, runId) {
  if (!tree || !runId) return null;
  return (tree.nodes || []).find((n) => n.run_id === runId) || null;
}

function renderResearchActions() {
  const actions = document.getElementById("research-actions");
  if (!actions) return;
  const runId = getActiveResearchRunId();
  const hasTree = !!workspaceSession.treeId;
  const selected = workspaceSession.selectedNodeId
    ? findResearchNode(workspaceSession.currentTree, workspaceSession.selectedNodeId)
    : null;
  const hintBar = document.getElementById("research-toolbar-hint");
  if (hintBar) hintBar.classList.toggle("hidden", !!runId);
  const runHint = runId
    ? `<span class="muted research-actions-hint">当前轮次：${escapeHtml((selected?.title || runId).slice(0, 36))}</span>`
    : `<span class="muted research-actions-hint">请先在研究树中点击一轮搜罗</span>`;
  const canDelete = selected && selected.kind !== "topic";
  const treeSearchCount = (workspaceSession.currentTree?.nodes || []).filter((n) => n.kind === "search").length;
  actions.innerHTML = `
    ${runHint}
    <div class="research-actions-btns">
      <button type="button" class="btn btn-sm btn-secondary" id="btn-research-note" ${hasTree ? "" : "disabled"} title="在当前选中节点下添加笔记">添加笔记</button>
      <button type="button" class="btn btn-sm btn-secondary" id="btn-research-fork" ${runId ? "" : "disabled"} title="继承上轮报告与反馈，细化关键词再搜罗">分叉深挖</button>
      <button type="button" class="btn btn-sm btn-secondary" id="btn-research-insight" ${runId && hasTree ? "" : "disabled"} title="AI 归纳本轮要点（需 DeepSeek）">归纳要点</button>
      <button type="button" class="btn btn-sm btn-ghost" id="btn-research-suggest" ${runId ? "" : "disabled"} title="生成后续搜罗建议（需 DeepSeek）">建议查询</button>
      <button type="button" class="btn btn-sm btn-ghost" id="btn-research-summarize" ${treeSearchCount >= 2 && hasTree ? "" : "disabled"} title="AI 综合多轮搜罗做全树归纳（需 2+ 轮搜罗）">全树归纳</button>
      <button type="button" class="btn btn-sm btn-danger" id="btn-research-delete-node" ${canDelete ? "" : "disabled"} title="删除当前选中节点及其子节点">删除节点</button>
    </div>`;
  document.getElementById("btn-research-note")?.addEventListener("click", () => toggleResearchNoteForm(true));
  document.getElementById("btn-research-fork")?.addEventListener("click", () => forkSearchFromRun(runId));
  document.getElementById("btn-research-insight")?.addEventListener("click", () => void generateResearchInsight(runId));
  document.getElementById("btn-research-suggest")?.addEventListener("click", () => void suggestResearchQueries(runId));
  document.getElementById("btn-research-summarize")?.addEventListener("click", () => {
    if (!workspaceSession.treeId) return;
    const btn = document.getElementById("btn-research-summarize");
    if (btn) { btn.disabled = true; btn.textContent = "归纳中..."; }
    api("POST", `/api/research/trees/${workspaceSession.treeId}/summarize`)
      .then((res) => {
        toast("全树归纳完成");
        return refreshResearchTree(res.node?.id);
      })
      .catch((e) => toast(e.message || "归纳失败", "error"))
      .finally(() => { if (btn) { btn.disabled = false; btn.textContent = "全树归纳"; } });
  });
  document.getElementById("btn-research-delete-node")?.addEventListener("click", () => {
    const nodeId = workspaceSession.selectedNodeId;
    if (!nodeId || !workspaceSession.treeId) return;
    if (!confirm("确认删除该节点及其所有子节点？")) return;
    api("DELETE", `/api/research/trees/${workspaceSession.treeId}/nodes/${nodeId}`)
      .then(() => { workspaceSession.selectedNodeId = null; return refreshResearchTree(); })
      .catch((e) => toast(e.message || "删除失败", "error"));
  });
}

const RUN_STATUS_LABELS = {
  running: "进行中",
  done: "已完成",
  error: "失败",
  cancelled: "已取消",
  interrupted: "已中断",
  unknown: "未知",
};

const COMMAND_LABELS = {
  search: "搜罗",
};

const STEP_LABELS = {
  starting: "准备",
  alias_discover: "关联词发现",
  foreign_expand: "外文拓展",
  ai_query_analyze: "查询分析",
  ai_source_plan: "信源规划",
  collect_all: "多源采集",
  dedup: "去重打分",
  relevance_refine: "相关度辅助",
  mine_comments: "评论挖掘",
  ai_summarize: "AI 摘要",
  persona_simulate: "画像模拟",
  ai_report: "情报报告",
};

const workspaceSourceOverrides = { force: [], block: [] };

const DEPTH_LABELS = { serp: "SERP", native: "原生", hybrid: "混合" };

const SOURCE_CATALOG_META = {};

const SOURCE_UI_STATUS = {
  ready: { label: "已就绪", chipClass: "source-auth-ready" },
  serp_fallback: { label: "摘要模式", chipClass: "source-auth-serp" },
  serp_only: { label: "检索", chipClass: "source-auth-serp" },
  needs_login: { label: "需登录", chipClass: "source-auth-warn" },
  needs_auth: { label: "需登录/Key", chipClass: "source-auth-warn" },
  none: { label: "", chipClass: "" },
};

const SOURCE_CHIP_STATUS_CLASSES = ["source-auth-ready", "source-auth-serp", "source-auth-warn"];

let workspaceSerpFallbackAccepted = [];
try {
  const raw = sessionStorage.getItem("workspaceSerpFallbackAccepted");
  if (raw) workspaceSerpFallbackAccepted = JSON.parse(raw);
} catch (_) {
  workspaceSerpFallbackAccepted = [];
}

function saveSerpFallbackAccepted() {
  try {
    sessionStorage.setItem("workspaceSerpFallbackAccepted", JSON.stringify(workspaceSerpFallbackAccepted));
  } catch (_) {}
}

function sourceAuthCanUseSerpFallback(check) {
  if (!check) return false;
  if (check.serp_fallback) return true;
  return check.mode === "cookie_required";
}

function sourceNeedsAuthPrompt(check, sourceId) {
  if (!check) return false;
  if (check.mode === "none" || check.mode === "serp_only") return false;
  if (check.ui_status === "ready") return false;
  if (workspaceSerpFallbackAccepted.includes(sourceId)) return false;
  return ["needs_login", "needs_auth", "serp_fallback"].includes(check.ui_status);
}

function applySourceChipStatus(chip, check) {
  if (!chip || !check) return;
  const statusEl = chip.querySelector(".source-chip-status");
  const spec = SOURCE_UI_STATUS[check.ui_status] || SOURCE_UI_STATUS.none;
  chip.classList.remove(...SOURCE_CHIP_STATUS_CLASSES);
  if (spec.chipClass) chip.classList.add(spec.chipClass);
  if (statusEl) {
    statusEl.textContent = spec.label;
    const hint = [check.reason, check.login_hint].filter(Boolean).join(" · ");
    statusEl.title = hint;
  }
  chip.dataset.uiStatus = check.ui_status || "";
}

async function fetchSourceAuthChecks(sourceIds) {
  if (!sourceIds.length) return [];
  const data = await api("GET", `/api/sources/auth-check?sources=${encodeURIComponent(sourceIds.join(","))}`);
  return data.checks || [];
}

async function refreshSourceChipStatuses() {
  const chips = [...document.querySelectorAll(".source-chip[data-source-id]")];
  if (!chips.length) return;
  const ids = chips.map((c) => c.dataset.sourceId).filter(Boolean);
  try {
    const checks = await fetchSourceAuthChecks(ids);
    const byId = Object.fromEntries(checks.map((c) => [c.source, c]));
    chips.forEach((chip) => applySourceChipStatus(chip, byId[chip.dataset.sourceId]));
  } catch (_) {}
}

function showSourceAuthModal(sourceId, check) {
  return new Promise((resolve) => {
    const dialog = document.getElementById("source-auth-modal");
    if (!dialog) {
      resolve("cancel");
      return;
    }
    const label = SOURCE_LABELS[sourceId] || sourceId;
    const title = document.getElementById("source-auth-modal-title");
    const body = document.getElementById("source-auth-modal-body");
    const steps = document.getElementById("source-auth-modal-steps");
    const loginBtn = document.getElementById("source-auth-btn-login");
    const syncBtn = document.getElementById("source-auth-btn-sync");
    const serpBtn = document.getElementById("source-auth-btn-serp");
    if (title) title.textContent = `登录「${label}」以获取完整搜索能力`;
    if (body) body.textContent = check.login_hint || check.reason || "该平台建议登录后由扩展同步 Cookie。";
    if (steps) {
      steps.innerHTML = [
        "<li>点击「打开登录页」，在浏览器中完成登录（可保持本页打开）</li>",
        "<li>登录后点击「我已登录，同步 Cookie」— 需已安装 OSINT 浏览器扩展</li>",
        "<li>芯片标签变为绿色「已就绪」后，即可完整采集该信源</li>",
      ].join("");
    }
    serpBtn?.classList.toggle("hidden", !sourceAuthCanUseSerpFallback(check));
    loginBtn?.classList.toggle("hidden", !check.login_url);
    let settled = false;
    let pendingResult = "cancel";
    const finish = (result) => {
      if (settled) return;
      settled = true;
      dialog.removeEventListener("close", onDialogClose);
      resolve(result);
    };
    const onDialogClose = () => finish(pendingResult);
    dialog.addEventListener("close", onDialogClose);
    loginBtn?.addEventListener(
      "click",
      () => {
        if (check.login_url) window.open(check.login_url, "_blank", "noopener");
      },
      { once: true },
    );
    syncBtn?.addEventListener(
      "click",
      async () => {
        try {
          const data = await api("POST", "/api/auth/sync-cookies", {});
          const synced = (data.domains_synced || []).length;
          if (synced) showToast(`已同步 ${synced} 个域名的 Cookie`, "success");
          else showToast("未读到 Cookie：请确认已在浏览器登录，并用扩展「从浏览器同步 Cookie」", "warn");
          await refreshSourceChipStatuses();
          const fresh = (await fetchSourceAuthChecks([sourceId]))[0];
          if (fresh?.ui_status === "ready") {
            pendingResult = "ready";
            dialog.close();
          }
        } catch (err) {
          showToast(
            `${err.message || "同步失败"}。请用扩展弹窗「从浏览器同步 Cookie」，或前往设置页。`,
            "warn",
          );
        }
      },
      { once: true },
    );
    serpBtn?.addEventListener(
      "click",
      () => {
        pendingResult = "serp";
        dialog.close();
      },
      { once: true },
    );
    dialog.querySelector('button[value="cancel"]')?.addEventListener(
      "click",
      () => {
        pendingResult = "cancel";
        dialog.close();
      },
      { once: true },
    );
    dialog.showModal();
  });
}

async function handleSourceCheckboxAuth(checkbox) {
  if (!checkbox?.checked || checkbox.dataset.authBypass === "1") return;
  const sourceId = checkbox.value;
  const meta = SOURCE_CATALOG_META[sourceId];
  if (!meta?.needs_cookie_sync) return;
  let check;
  try {
    check = (await fetchSourceAuthChecks([sourceId]))[0];
  } catch (_) {
    return;
  }
  if (!sourceNeedsAuthPrompt(check, sourceId)) return;
  const action = await showSourceAuthModal(sourceId, check);
  if (action === "serp") {
    if (!workspaceSerpFallbackAccepted.includes(sourceId)) workspaceSerpFallbackAccepted.push(sourceId);
    saveSerpFallbackAccepted();
    showToast(`「${SOURCE_LABELS[sourceId] || sourceId}」将使用搜索引擎摘要`, "info");
    void refreshSourceChipStatuses();
    void checkAuthBanner();
    return;
  }
  if (action === "ready") {
    void checkAuthBanner();
    return;
  }
  checkbox.dataset.authBypass = "1";
  checkbox.checked = false;
  delete checkbox.dataset.authBypass;
  updateSourceSelectionSummary();
}

function initCommentMineUI(sourceCatalog) {
  const host = document.getElementById("comment-mine-sources");
  const master = document.getElementById("opt-mine-comments");
  if (!host) return;
  const sources = [];
  (sourceCatalog || []).forEach((group) => {
    (group.sources || []).forEach((s) => {
      if (s.comment_mine) sources.push(s);
    });
  });
  if (!sources.length) {
    host.innerHTML = "<span class='muted'>当前目录无支持社区层挖掘的信源</span>";
    return;
  }
  host.innerHTML = sources
    .map(
      (s) => `<label class="chip comment-mine-chip" title="${escapeHtml(s.description || "")}">
      <input type="checkbox" name="comment_mine_sources" value="${escapeHtml(s.id)}" checked>
      ${escapeHtml(s.label)}
    </label>`,
    )
    .join("");
  const syncDisabled = () => {
    const on = master?.checked !== false;
    host.querySelectorAll("input").forEach((inp) => {
      inp.disabled = !on;
    });
    host.classList.toggle("is-disabled", !on);
  };
  master?.addEventListener("change", syncDisabled);
  syncDisabled();
}

function getCommentMineSourcesForSearch() {
  const master = document.getElementById("opt-mine-comments");
  if (!master?.checked) return [];
  return [...document.querySelectorAll("input[name='comment_mine_sources']:checked")].map((el) => el.value);
}

function getSourceOverrides() {
  const force = workspaceSourceOverrides.force.filter(Boolean);
  const block = workspaceSourceOverrides.block.filter(Boolean);
  if (!force.length && !block.length) return null;
  return { force, block };
}

function setSourceOverride(sourceId, action) {
  if (!sourceId) return;
  if (action === "force") {
    workspaceSourceOverrides.block = workspaceSourceOverrides.block.filter((s) => s !== sourceId);
    if (!workspaceSourceOverrides.force.includes(sourceId)) workspaceSourceOverrides.force.push(sourceId);
    const box = document.querySelector(`input[name='sources'][value='${sourceId}']`);
    if (box) box.checked = true;
    showToast(`已标记「${SOURCE_LABELS[sourceId] || sourceId}」本次必采`, "success");
  } else if (action === "block") {
    workspaceSourceOverrides.force = workspaceSourceOverrides.force.filter((s) => s !== sourceId);
    if (!workspaceSourceOverrides.block.includes(sourceId)) workspaceSourceOverrides.block.push(sourceId);
    showToast(`已标记「${SOURCE_LABELS[sourceId] || sourceId}」本次排除`, "success");
  } else if (action === "clear") {
    workspaceSourceOverrides.force = workspaceSourceOverrides.force.filter((s) => s !== sourceId);
    workspaceSourceOverrides.block = workspaceSourceOverrides.block.filter((s) => s !== sourceId);
  }
  void refreshExpandedQueries();
}

async function bootstrapSourceLabels() {
  try {
    const data = await api("GET", "/api/search/source-catalog");
    (data.groups || []).forEach((group) => {
      (group.sources || []).forEach((s) => {
        if (s.id) SOURCE_LABELS[s.id] = s.label || s.id;
      });
    });
  } catch (_) {
    /* catalog optional on runs pages */
  }
}

const SOURCE_LABELS = {
  zhihu: "知乎",
  bilibili: "B站",
  web: "网页",
  weixin: "搜狗微信公众平台",
  v2ex: "V2EX",
  rss: "RSS",
  ithome: "IT之家",
  sspai: "少数派",
  juejin: "掘金",
  solidot: "Solidot",
  kr36: "36氪",
  huxiu: "虎嗅",
  netease_music: "网易云音乐",
  qq_music: "QQ音乐",
  kugou: "酷狗音乐",
  douban: "豆瓣",
};

const PROFILE_LABELS = {
  default: "默认",
  full: "全量",
  research: "深度研究",
  zhihu_deep: "知乎深挖",
};

function profileLabel(id) {
  if (!id) return "";
  return PROFILE_LABELS[id] || id;
}

const RESULTS_RENDER_BATCH = 30;
let _markmapLoaderPromise = null;

function ensureMarkmapLoader() {
  if (window.markmap?.autoLoader) return Promise.resolve();
  if (_markmapLoaderPromise) return _markmapLoaderPromise;
  _markmapLoaderPromise = new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = "https://cdn.jsdelivr.net/npm/markmap-autoloader@0.17.2";
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("Markmap 脚本加载失败"));
    document.head.appendChild(script);
  });
  return _markmapLoaderPromise;
}

function appendResultCardInteractions(container, runId, items) {
  hydrateItemCards(container, items);
  initItemCardInteractions(container);
  if (container.dataset.simOverrideBound !== "1") {
    container.dataset.simOverrideBound = "1";
    container.addEventListener("click", (ev) => {
      const btn = ev.target.closest?.("[data-sim-override]");
      if (!btn || !container.contains(btn)) return;
      overrideSimVerdict(btn.dataset.id, btn.dataset.run, btn.dataset.simOverride, btn);
    });
  }
  container.querySelectorAll("[data-feedback]").forEach((btn) => {
    if (btn.dataset.bound === "1") return;
    btn.dataset.bound = "1";
    btn.addEventListener("click", () => submitFeedback(btn.dataset.feedback, btn.dataset.id, runId, btn));
  });
  container.querySelectorAll("[data-sim-feedback]").forEach((btn) => {
    if (btn.dataset.bound === "1") return;
    btn.dataset.bound = "1";
    btn.addEventListener("click", () =>
      submitSimFeedback(btn.dataset.simFeedback, btn.dataset.id, btn.dataset.verdict, runId, btn));
  });
  container.querySelectorAll("[data-save]").forEach((btn) => {
    if (btn.dataset.bound === "1") return;
    btn.dataset.bound = "1";
    btn.addEventListener("click", () => saveFromCard(btn.dataset.save));
  });
  container.querySelectorAll("[data-research-item]").forEach((btn) => {
    if (btn.dataset.bound === "1") return;
    btn.dataset.bound = "1";
    btn.addEventListener("click", () => {
      const itemId = String(btn.dataset.researchItem || "");
      const item = items.find((row) => String(row.id || "") === itemId);
      if (item) void addSearchItemToResearch(item);
    });
  });
}

function mountIncrementalResultsList(container, items, simMap, runId, feedbackMap) {
  let visible = Math.min(RESULTS_RENDER_BATCH, items.length);
  let rendered = 0;

  const renderRange = (start, end) => items
    .slice(start, end)
    .map((item, i) => renderItemCard(item, simMap[item.id], runId, feedbackMap, start + i === 0, start + i))
    .join("");

  const updateMoreBtn = () => {
    const moreBtn = container.querySelector("[data-load-more-results]");
    if (moreBtn) {
      if (visible >= items.length) moreBtn.classList.add("hidden");
      else {
        moreBtn.classList.remove("hidden");
        moreBtn.textContent = `加载更多（还剩 ${items.length - visible} 条）`;
      }
    }
  };

  const initialRender = () => {
    const list = container.querySelector(".item-card-list");
    if (!list) return;
    list.innerHTML = renderRange(0, visible);
    rendered = visible;
    appendResultCardInteractions(container, runId, items.slice(0, visible));
    updateMoreBtn();
    if (typeof container._applyResultFilters === "function") container._applyResultFilters();
  };

  container.querySelector("[data-load-more-results]")?.addEventListener("click", () => {
    const prevVisible = visible;
    visible = Math.min(items.length, visible + RESULTS_RENDER_BATCH);
    const list = container.querySelector(".item-card-list");
    if (list && visible > rendered) {
      const html = renderRange(rendered, visible);
      list.insertAdjacentHTML("beforeend", html);
      appendResultCardInteractions(container, runId, items.slice(rendered, visible));
      rendered = visible;
    }
    updateMoreBtn();
    if (typeof container._applyResultFilters === "function") container._applyResultFilters();
  });
  initialRender();
}

function formatStepLabel(step) {
  return STEP_LABELS[step] || step || "";
}

function formatCommandLabel(cmd) {
  return COMMAND_LABELS[cmd] || cmd || "";
}

function formatSourceLabels(sources) {
  return (sources || []).map((s) => SOURCE_LABELS[s] || s).join("、");
}

function formatRunTime(iso) {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleString("zh-CN", { hour12: false });
  } catch (_) {
    return iso;
  }
}

function formatDurationSec(sec) {
  if (sec == null || sec < 0) return "—";
  if (sec < 60) return `${sec} 秒`;
  if (sec < 3600) return `${Math.floor(sec / 60)} 分 ${sec % 60} 秒`;
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  return `${h} 小时 ${m} 分`;
}

function runStatusClass(status) {
  return `run-status-${status || "unknown"}`;
}

const NODE_STATUS_LABELS = {
  running: "进行中",
  done: "完成",
  error: "失败",
  cancelled: "取消",
  interrupted: "中断",
};

function formatRunStatus(status) {
  return RUN_STATUS_LABELS[status] || status || RUN_STATUS_LABELS.unknown;
}

function showWorkspaceAlert(id, message, kind = "warn") {
  const el = document.getElementById(id);
  if (!el) return;
  el.className = `alert alert-${kind}`;
  el.innerHTML = message;
  el.classList.remove("hidden");
}

function hideWorkspaceAlert(id) {
  document.getElementById(id)?.classList.add("hidden");
}

function showResearchFeedback(message, kind = "error") {
  showWorkspaceAlert("research-feedback", escapeHtml(message), kind);
}

function clearResearchFeedback() {
  hideWorkspaceAlert("research-feedback");
}

function setActiveSearchRunId(runId) {
  workspaceSession.activeRunId = runId || null;
  if (runId) {
    setCurrentRunId(runId);
    sessionStorage.setItem("activeSearchRunId", runId);
  } else {
    sessionStorage.removeItem("activeSearchRunId");
  }
}

function setResearchTreeId(treeId) {
  workspaceSession.treeId = treeId || null;
  const delBtn = document.getElementById("btn-research-delete-tree");
  if (delBtn) delBtn.classList.toggle("hidden", !treeId);
  if (treeId) {
    sessionStorage.setItem("researchTreeId", treeId);
    workspaceSession.parentNodeId = loadStoredParentNodeId(treeId);
  } else {
    sessionStorage.removeItem("researchTreeId");
    workspaceSession.parentNodeId = null;
  }
}

async function syncResearchTreeSelect() {
  const select = document.getElementById("research-tree-select");
  if (!select) return;
  try {
    const data = await api("GET", "/api/research/trees?limit=30");
    const trees = data.trees || [];
    const options = [`<option value="">— 选择研究树 —</option>`];
    trees.forEach((tree) => {
      const id = tree.id || "";
      const title = (tree.title || id).slice(0, 48);
      const selected = id === workspaceSession.treeId ? " selected" : "";
      options.push(`<option value="${escapeHtml(id)}"${selected}>${escapeHtml(title)}</option>`);
    });
    if (workspaceSession.treeId && !trees.some((t) => t.id === workspaceSession.treeId)) {
      options.push(
        `<option value="${escapeHtml(workspaceSession.treeId)}" selected>当前研究</option>`
      );
    }
    select.innerHTML = options.join("");
  } catch (_) {
    select.innerHTML = `<option value="">研究树列表不可用</option>`;
  }
}

async function createNewResearchTree() {
  const query = document.getElementById("search-query")?.value.trim();
  const title = query || window.prompt("新研究主题名称", "")?.trim();
  if (!title) return;
  try {
    const data = await api("POST", "/api/research/trees", { title, query: query || title });
    const treeId = data.tree?.id;
    if (!treeId) throw new Error("创建研究树失败");
    setResearchTreeId(treeId);
    setWorkspaceParentNodeId(null);
    const chk = document.getElementById("opt-create-research-tree");
    if (chk) chk.checked = true;
    await syncResearchTreeSelect();
    await refreshResearchTree();
    showToast(`已创建研究树「${title}」`, "success");
  } catch (err) {
    showResearchFeedback(err.message);
  }
}

function initResearchTreeToolbar() {
  document.getElementById("btn-research-new")?.addEventListener("click", () => void createNewResearchTree());
  document.getElementById("btn-research-clear")?.addEventListener("click", () => {
    setResearchTreeId(null);
    setWorkspaceParentNodeId(null);
    workspaceSession.selectedNodeId = null;
    renderResearchSuggestChips([]);
    void syncResearchTreeSelect();
    void refreshResearchTree();
    showToast("已脱离当前研究树", "info");
  });
  document.getElementById("btn-research-delete-tree")?.addEventListener("click", () => {
    if (!workspaceSession.treeId) return;
    if (!confirm("确认删除整棵研究树？此操作不可恢复。")) return;
    api("DELETE", `/api/research/trees/${workspaceSession.treeId}`)
      .then(() => {
        setResearchTreeId(null);
        setWorkspaceParentNodeId(null);
        workspaceSession.selectedNodeId = null;
        return syncResearchTreeSelect();
      })
      .then(() => refreshResearchTree())
      .catch((e) => toast(e.message || "删除失败", "error"));
  });
  document.getElementById("research-tree-select")?.addEventListener("change", (e) => {
    const id = e.target.value;
    if (!id) return;
    setResearchTreeId(id);
    setWorkspaceParentNodeId(null);
    void refreshResearchTree();
  });
}

async function pollActiveJobs() {
  const chip = document.getElementById("sidebar-active-jobs");
  if (!chip) return;
  try {
    const { jobs: data } = await getShellStatus();
    const jobs = data?.jobs || [];
    if (!jobs.length) {
      chip.classList.add("hidden");
      chip.innerHTML = "";
      return;
    }
    chip.classList.remove("hidden");
    const lines = jobs.slice(0, 3).map((j) => {
      const pctVal = j.progress?.percent;
      const pctHtml = pctVal != null ? `<span class="job-pct">${Math.round(pctVal)}%</span>` : "";
      let text = "";
      if (j.kind === "search") {
        text = `搜罗 · ${(j.query || j.progress?.detail || "").slice(0, 16)}`;
      } else if (j.kind === "full_sync") {
        text = "完整同步";
      } else if (j.kind === "playwright_install") {
        text = "Playwright";
      } else {
        text = j.kind || "任务";
      }
      const href = j.kind === "search" ? `/?run=${encodeURIComponent(j.job_id)}` : "/ingest";
      return `<a href="${href}" title="点击继续查看">${escapeHtml(text)}${pctHtml}</a>`;
    });
    chip.innerHTML = `后台任务 ${lines.join(" · ")}`;
    chip.classList.add("warn");
  } catch (_) {
    chip.classList.add("hidden");
  }
}

async function pollUntilSearchDone(runId, resultsEl, stepsEl, reportEl, progressUi) {
  const gen = searchSession.generation;
  const abort = new AbortController();
  searchSession.pollAbort = abort;
  for (let i = 0; i < 360; i += 1) {
    if (abort.signal.aborted || !isActiveSearchSession(gen, runId)) return;
    await new Promise((r) => setTimeout(r, 2000));
    if (abort.signal.aborted || !isActiveSearchSession(gen, runId)) return;
    try {
      const data = await api("GET", `/api/search/${runId}`);
      if (data.progress && progressUi) progressUi.update(data.progress);
      if (data.status === "running") continue;
      if (data.status === "done") {
        finishSearchRun(progressUi, () => {
          void renderSearchResults(data, resultsEl, reportEl, runId);
          void refreshResearchTree();
        });
        setActiveSearchRunId(null);
        return;
      }
      if (data.status === "interrupted") {
        finishSearchRun(progressUi, async () => {
          await renderSearchResults(data, resultsEl, reportEl, runId);
          if (data.items?.length || data.report) {
            prependResultsBanner(resultsEl, "warn", data.error || "任务已中断，以下为已落盘部分结果");
          }
          void refreshResearchTree();
        });
        setActiveSearchRunId(null);
        return;
      }
      if (data.status === "cancelled") {
        finishSearchRun(progressUi, () => {
          resultsEl.innerHTML = `<div class="alert alert-warn">${escapeHtml(data.error || "已取消")}</div>`;
        });
        setActiveSearchRunId(null);
        return;
      }
    } catch (err) {
      if (err.message && String(err.message).includes("404")) break;
    }
  }
  finishSearchRun(progressUi, () => {
    resultsEl.innerHTML =
      "<div class='alert alert-warn'>搜罗仍在后台进行。<a href='/?run=" +
      encodeURIComponent(runId) +
      "'>点此继续跟踪</a></div>";
  });
}

async function resumeSearchRun(runId) {
  const resultsEl = document.getElementById("search-results");
  const stepsEl = document.getElementById("steps-bar");
  const reportEl = document.getElementById("report-panel");
  const runLink = document.getElementById("run-link");
  if (!resultsEl || !stepsEl) return;
  workspaceProgressUi?.stop();
  searchTaskRegistry.focusedRunId = runId;
  resetFocusedSearchWorkspace({ reportPlaceholder: false });
  beginSearchSession(runId);
  switchWorkspacePanel("results");
  const progressUi = mountSearchProgress(resultsEl);
  progressUi.setRunId(runId);
  stepsEl.innerHTML = "<span class='step-pill active'>恢复跟踪…</span>";
  if (runLink) {
    runLink.href = `/runs/${runId}`;
    runLink.classList.remove("hidden");
    runLink.textContent = "查看运行记录";
  }
  setActiveSearchRunId(runId);
  highlightSearchTaskItem(runId);
  try {
    const data = await api("GET", `/api/search/${runId}`);
    if (data.status === "done" || data.status === "interrupted") {
      finishSearchRun(progressUi, async () => {
        await renderSearchResults(data, resultsEl, reportEl, runId);
        if (data.status === "interrupted" && (data.items?.length || data.report)) {
          prependResultsBanner(resultsEl, "warn", data.error || "任务已中断，以下为已落盘部分结果");
        }
      });
      setActiveSearchRunId(null);
      searchTaskRegistry.focusedRunId = null;
      return;
    }
    if (data.status === "cancelled" || data.status === "error") {
      finishSearchRun(progressUi, () => {
        resultsEl.innerHTML = `<div class="alert alert-error">${escapeHtml(data.error || data.detail || "搜罗失败")}</div>`;
      });
      setActiveSearchRunId(null);
      searchTaskRegistry.focusedRunId = null;
      return;
    }
    if (data.status === "queued") {
      const pos = data.queue_position ? `（第 ${data.queue_position} 位）` : "";
      resultsEl.innerHTML = `<div class="alert alert-warn">排队中${escapeHtml(pos)}，即将开始…</div>`;
      stepsEl.innerHTML = "<span class='step-pill active'>排队中</span>";
      void waitUntilSearchRunning(runId, resultsEl, stepsEl, reportEl, progressUi);
      return;
    }
    if (data.progress) progressUi.update(data.progress);
    subscribeSearchEvents(runId, resultsEl, stepsEl, reportEl, progressUi);
  } catch (err) {
    finishSearchRun(progressUi, () => {
      resultsEl.innerHTML = `<div class="alert alert-error">${escapeHtml(err.message)}</div>`;
    });
  }
}

async function focusSearchTask(runId) {
  if (!runId) return;
  if (searchTaskRegistry.focusedRunId === runId) return;
  const panel = document.getElementById("search-task-panel");
  panel?.setAttribute("open", "");
  await resumeSearchRun(runId);
}

async function waitUntilSearchRunning(runId, resultsEl, stepsEl, reportEl, progressUi) {
  const gen = searchSession.generation;
  for (let i = 0; i < 600; i += 1) {
    if (!isActiveSearchSession(gen, runId)) return;
    await new Promise((r) => setTimeout(r, 2000));
    if (!isActiveSearchSession(gen, runId)) return;
    try {
      const data = await api("GET", `/api/search/${runId}`, null, { timeoutMs: 15000 });
      if (!isActiveSearchSession(gen, runId)) return;
      if (data.status === "running") {
        if (data.progress) progressUi?.update(data.progress);
        resultsEl.innerHTML = "";
        subscribeSearchEvents(runId, resultsEl, stepsEl, reportEl, progressUi);
        return;
      }
      if (data.status === "cancelled" || data.status === "error") {
        finishSearchRun(progressUi, () => {
          resultsEl.innerHTML = `<div class="alert alert-error">${escapeHtml(data.error || "搜罗失败")}</div>`;
        });
        return;
      }
      if (data.status === "done") {
        finishSearchRun(progressUi, async () => {
          await renderSearchResults(data, resultsEl, reportEl, runId);
        });
        return;
      }
      if (data.status === "queued" && data.queue_position) {
        resultsEl.innerHTML = `<div class="alert alert-warn">排队中（第 ${escapeHtml(String(data.queue_position))} 位）…</div>`;
      }
    } catch (_) {}
  }
  resultsEl.innerHTML =
    "<div class='alert alert-warn'>仍在排队或后台搜罗中，请从任务列表切换查看。</div>";
}

function highlightSearchTaskItem(runId) {
  document.querySelectorAll(".search-task-item").forEach((el) => {
    el.classList.toggle("is-focused", el.dataset.runId === runId);
  });
}

function searchTaskSummaryText(tasks) {
  const running = tasks.filter((t) => t.status === "running").length;
  const queued = tasks.filter((t) => t.status === "queued").length;
  if (!running && !queued) return "";
  const parts = [];
  if (running) parts.push(`${running} 进行中`);
  if (queued) parts.push(`${queued} 排队`);
  return parts.join(" · ");
}

function renderSearchTaskList(tasks) {
  const listEl = document.getElementById("search-task-list");
  const summaryEl = document.getElementById("search-task-summary");
  if (!listEl) return;
  if (summaryEl) summaryEl.textContent = searchTaskSummaryText(tasks);

  const active = tasks.filter((t) => t.status === "running" || t.status === "queued");
  if (!tasks.length) {
    listEl.innerHTML = "暂无搜罗任务；填写话题后点击「开始搜罗」或「加入队列」";
    listEl.classList.add("muted");
    return;
  }
  listEl.classList.toggle("muted", !active.length && !tasks.some((t) => t.status === "done"));

  listEl.innerHTML = tasks
    .map((task) => {
      const runId = task.run_id || task.job_id;
      const status = task.status || "unknown";
      const label = SEARCH_TASK_STATUS_LABELS[status] || status;
      const query = (task.query || runId || "").slice(0, 48);
      const focused = searchTaskRegistry.focusedRunId === runId || searchSession.runId === runId;
      const pct = task.progress?.percent;
      const progressHtml =
        status === "running" && pct != null
          ? `<div class="search-task-progress" aria-hidden="true"><div class="search-task-progress-fill" style="width:${Math.min(100, Math.round(pct))}%"></div></div>`
          : "";
      const queueHint =
        status === "queued" && task.queue_position ? ` · 第 ${task.queue_position} 位` : "";
      const itemCount =
        status === "done" && task.item_count != null ? ` · ${task.item_count} 条` : "";
      const canCancel = status === "running" || status === "queued";
      const cancelBtn = canCancel
        ? `<button type="button" class="btn btn-sm btn-ghost search-task-cancel" data-action="cancel-search-task" data-run-id="${escapeHtml(runId)}">取消</button>`
        : "";
      return `<div class="search-task-item${focused ? " is-focused" : ""}" data-run-id="${escapeHtml(runId)}" role="listitem">
        <button type="button" class="search-task-focus" data-action="focus-search-task" data-run-id="${escapeHtml(runId)}">
          <span class="search-task-badge search-task-badge--${escapeHtml(status)}">${escapeHtml(label)}</span>
          <div class="search-task-main">
            <div class="search-task-query" title="${escapeHtml(task.query || "")}">${escapeHtml(query)}</div>
            <div class="search-task-meta muted">${escapeHtml(label)}${escapeHtml(queueHint)}${escapeHtml(itemCount)}</div>
          </div>
          ${progressHtml}
        </button>
        ${cancelBtn}
      </div>`;
    })
    .join("");
}

function notifySearchTaskTransitions(tasks) {
  tasks.forEach((task) => {
    const runId = task.run_id || task.job_id;
    const prev = searchTaskRegistry.lastStatusByRun.get(runId);
    const next = task.status;
  if (prev === "running" && next === "done" && runId !== searchSession.runId) {
      const label = (task.query || "搜罗").slice(0, 24);
      showToast(`搜罗完成：${label}`, "success");
    }
    if (prev === "running" && next === "error" && runId !== searchSession.runId) {
      showToast(`搜罗失败：${(task.query || runId).slice(0, 24)}`, "error");
    }
    searchTaskRegistry.lastStatusByRun.set(runId, next);
  });
}

async function refreshSearchTaskList() {
  const listEl = document.getElementById("search-task-list");
  if (!listEl) return;
  try {
    const data = await api("GET", "/api/search/tasks?limit=30", null, { timeoutMs: 10000 });
    const tasks = data.tasks || [];
    notifySearchTaskTransitions(tasks);
    renderSearchTaskList(tasks);
    const hasActive = tasks.some((t) => t.status === "running" || t.status === "queued");
    if (hasActive) startSearchTaskPolling();
    else stopSearchTaskPolling();
  } catch (_) {}
}

function startSearchTaskPolling() {
  if (searchTaskRegistry.pollTimer || document.hidden || sidebarPollTimer) return;
  searchTaskRegistry.pollTimer = window.setInterval(() => {
    if (document.hidden) return;
    void refreshSearchTaskList();
  }, 5000);
}

function stopSearchTaskPolling() {
  if (!searchTaskRegistry.pollTimer) return;
  clearInterval(searchTaskRegistry.pollTimer);
  searchTaskRegistry.pollTimer = null;
}

async function cancelSearchTask(runId) {
  if (!runId) return;
  try {
    await api("POST", `/api/search/${runId}/cancel`);
    showToast("已请求取消", "info");
    if (searchSession.runId === runId) {
      cleanupSearchSession();
      searchSession.runId = null;
      searchTaskRegistry.focusedRunId = null;
      setActiveSearchRunId(null);
    }
    void refreshSearchTaskList();
  } catch (err) {
    showToast(err.message || "取消失败", "error");
  }
}

function initSearchTaskPanel() {
  const listEl = document.getElementById("search-task-list");
  if (!listEl) return;

  listEl.addEventListener("click", (e) => {
    const cancelBtn = e.target.closest("[data-action='cancel-search-task']");
    if (cancelBtn) {
      e.stopPropagation();
      void cancelSearchTask(cancelBtn.dataset.runId);
      return;
    }
    const focusBtn = e.target.closest("[data-action='focus-search-task']");
    if (!focusBtn?.dataset.runId) return;
    void focusSearchTask(focusBtn.dataset.runId);
  });

  listEl.setAttribute("role", "list");

  document.addEventListener("visibilitychange", () => {
    if (document.hidden) stopSearchTaskPolling();
  });

  void refreshSearchTaskList();
}

function prependResultsBanner(resultsEl, kind, message) {
  const banner = document.createElement("div");
  banner.className = `alert alert-${kind} results-status-banner`;
  banner.textContent = message;
  resultsEl.prepend(banner);
}

const RESEARCH_KIND_LABELS = {
  topic: "主题",
  search: "搜罗",
  note: "笔记",
  insight: "要点",
  ask: "追问",
};

function nodeStatusHtml(meta) {
  const st = meta?.status;
  if (!st) return "";
  const label = NODE_STATUS_LABELS[st] || st;
  return `<span class="research-node-status research-node-status-${escapeHtml(st)}">${escapeHtml(label)}</span>`;
}

function findResearchNode(tree, nodeId) {
  return (tree?.nodes || []).find((n) => n.id === nodeId) || null;
}

function showResearchNodeDetail(node) {
  const el = document.getElementById("research-node-detail");
  if (!el) return;
  const kindsWithPayload = ["note", "insight", "ask"];
  if (!node || !kindsWithPayload.includes(node.kind) || !node.payload) {
    el.classList.add("hidden");
    el.innerHTML = "";
    workspaceSession.editingNodeId = null;
    return;
  }
  el.classList.remove("hidden");
  const kindLabel = RESEARCH_KIND_LABELS[node.kind] || node.kind;
  const editable = node.kind === "note" || node.kind === "insight";
  el.innerHTML = `<div class="research-node-detail-inner">
    <div class="research-node-detail-header">
      <strong>${escapeHtml(node.title || kindLabel)}</strong>
      ${editable ? `<button type="button" class="btn btn-sm btn-ghost" id="btn-research-edit">编辑</button>` : ""}
    </div>
    <div class="research-node-payload markdown-body"></div>
    <form id="research-edit-form" class="research-edit-form hidden">
      <input type="text" id="research-edit-title" class="input-sm" placeholder="标题">
      <textarea id="research-edit-payload" rows="6" placeholder="内容（Markdown）"></textarea>
      <div class="research-note-form-actions">
        <button type="button" class="btn btn-sm" id="btn-research-edit-save">保存</button>
        <button type="button" class="btn btn-sm btn-ghost" id="btn-research-edit-cancel">取消</button>
      </div>
    </form>
  </div>`;
  renderMarkdown(el.querySelector(".research-node-payload"), node.payload);
  if (editable) {
    document.getElementById("btn-research-edit")?.addEventListener("click", () => {
      const form = document.getElementById("research-edit-form");
      const payloadEl = el.querySelector(".research-node-payload");
      form?.classList.remove("hidden");
      payloadEl?.classList.add("hidden");
      document.getElementById("research-edit-title").value = node.title || "";
      document.getElementById("research-edit-payload").value = node.payload || "";
      workspaceSession.editingNodeId = node.id;
    });
    document.getElementById("btn-research-edit-cancel")?.addEventListener("click", () => {
      document.getElementById("research-edit-form")?.classList.add("hidden");
      el.querySelector(".research-node-payload")?.classList.remove("hidden");
      workspaceSession.editingNodeId = null;
    });
    document.getElementById("btn-research-edit-save")?.addEventListener("click", () => void saveResearchNodeEdit(node.id));
  }
}

async function saveResearchNodeEdit(nodeId) {
  if (!workspaceSession.treeId || !nodeId) return;
  const title = document.getElementById("research-edit-title")?.value.trim();
  const payload = document.getElementById("research-edit-payload")?.value.trim();
  if (!payload) {
    showResearchFeedback("内容不能为空", "warn");
    return;
  }
  try {
    await api("PATCH", `/api/research/trees/${workspaceSession.treeId}/nodes/${nodeId}`, {
      title: title || payload.slice(0, 40),
      payload,
    });
    clearResearchFeedback();
    await refreshResearchTree(nodeId);
  } catch (err) {
    showResearchFeedback(err.message);
  }
}

function buildResearchTreeHtml(tree, selectedNodeId) {
  const nodes = tree.nodes || [];
  const byParent = {};
  nodes.forEach((n) => {
    const pid = n.parent_id || "__root__";
    if (!byParent[pid]) byParent[pid] = [];
    byParent[pid].push(n);
  });
  function renderList(parentKey, depth) {
    const list = byParent[parentKey] || [];
    if (!list.length) return "";
    return `<ul class="research-tree" style="margin-left:${depth * 0.75}rem">${list
      .map((n) => {
        const sel = n.id === selectedNodeId ? " selected" : "";
        const running = n.kind === "search" && n.meta?.status === "running" ? " is-running" : "";
        return `<li>
          <div class="research-tree-node${sel}${running}" data-node-id="${escapeHtml(n.id)}" data-run-id="${escapeHtml(n.run_id || "")}" data-node-kind="${escapeHtml(n.kind || "")}">
            <span class="research-node-kind">${escapeHtml(RESEARCH_KIND_LABELS[n.kind] || n.kind)}</span>
            <span>${escapeHtml((n.title || "").slice(0, 48))}${nodeStatusHtml(n.meta)}</span>
          </div>
          ${renderList(n.id, depth + 1)}
        </li>`;
      })
      .join("")}</ul>`;
  }
  let html = `<div class="research-tree-title"><strong>${escapeHtml(tree.title || "研究")}</strong></div>`;
  html += renderList("__root__", 0);
  if ((nodes.length || 0) <= 1) {
    html += `<p class="muted research-tree-hint">完成首轮搜罗后，节点会出现在此。</p>`;
  }
  return html;
}

async function refreshResearchTree(selectedNodeId) {
  const panel = document.getElementById("research-panel");
  const actions = document.getElementById("research-actions");
  if (!panel) return;
  await syncResearchTreeSelect();
  if (!workspaceSession.treeId) {
    panel.innerHTML = "<p class=\"muted\">勾选「纳入研究树」并开始搜罗，或点击「新建研究」创建主题。</p>";
    renderResearchActions();
    return;
  }
  clearResearchFeedback();
  try {
    const data = await api("GET", `/api/research/trees/${workspaceSession.treeId}`);
    const tree = data.tree;
    workspaceSession.currentTree = tree;
    if (!getActiveResearchRunId()) {
      const latest = pickLatestSearchRunId(tree);
      if (latest) setCurrentRunId(latest);
    }
    panel.innerHTML = buildResearchTreeHtml(tree, selectedNodeId || workspaceSession.selectedNodeId);
    const titleEl = panel.querySelector(".research-tree-title");
    if (titleEl) {
      titleEl.ondblclick = () => {
        const newTitle = window.prompt("重命名研究树", tree.title || "");
        if (newTitle && newTitle !== tree.title) {
          api("PATCH", `/api/research/trees/${workspaceSession.treeId}`, { title: newTitle })
            .then(() => refreshResearchTree())
            .catch((e) => toast(e.message || "重命名失败", "error"));
        }
      };
      titleEl.style.cursor = "pointer";
      titleEl.title = "双击重命名";
    }
    const focusId = selectedNodeId || workspaceSession.selectedNodeId;
    const selectedNode = focusId ? findResearchNode(tree, focusId) : null;
    showResearchNodeDetail(selectedNode);
    panel.onclick = (e) => {
      const nodeEl = e.target.closest(".research-tree-node");
      if (!nodeEl) return;
      const runId = nodeEl.dataset.runId;
      const nodeId = nodeEl.dataset.nodeId;
      workspaceSession.selectedNodeId = nodeId;
      setWorkspaceParentNodeId(nodeId);
      const node = findResearchNode(workspaceSession.currentTree, nodeId);
      if (runId) {
        workspaceSession.selectedRunId = runId;
        setCurrentRunId(runId);
      }
      void refreshResearchTree(nodeId);
      showResearchNodeDetail(node);
      if (runId) void loadRunIntoWorkspace(runId);
    };
    renderResearchActions();
    void loadSuggestedQueries();
    const markmapEl = document.getElementById("research-markmap");
    if (markmapEl && !markmapEl.classList.contains("hidden")) {
      void renderResearchMarkmap(tree);
    }
  } catch (err) {
    panel.innerHTML = `<p class="muted">${escapeHtml(err.message)}</p>`;
  }
}

async function renderResearchMarkmap(tree) {
  const el = document.getElementById("research-markmap");
  if (!el) return;
  try {
    await ensureMarkmapLoader();
    const md = await api("GET", `/api/research/trees/${tree.id}/markmap`);
    el.textContent = "";
    const pre = document.createElement("pre");
    pre.className = "markmap";
    pre.textContent = md.markdown || "";
    el.appendChild(pre);
    if (window.markmap?.autoLoader) {
      window.markmap.autoLoader.renderAll();
    }
  } catch (_) {
    el.innerHTML = "<p class='muted p-1'>无法渲染导图</p>";
  }
}

function initResearchViewToggle() {
  document.querySelectorAll("[data-research-view]").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("[data-research-view]").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      const view = btn.dataset.researchView;
      const panel = document.getElementById("research-panel");
      const markmap = document.getElementById("research-markmap");
      if (view === "markmap") {
        panel?.classList.add("hidden");
        markmap?.classList.remove("hidden");
        if (workspaceSession.treeId) void refreshResearchTree();
      } else {
        panel?.classList.remove("hidden");
        markmap?.classList.add("hidden");
      }
      localStorage.setItem("researchView", view);
    });
  });
  const saved = localStorage.getItem("researchView");
  if (saved === "markmap") {
    document.querySelector('[data-research-view="markmap"]')?.click();
  }
}

async function loadRunIntoWorkspace(runId) {
  setCurrentRunId(runId);
  const resultsEl = document.getElementById("search-results");
  const reportEl = document.getElementById("report-panel");
  if (!resultsEl) return;
  try {
    const data = await api("GET", `/api/search/${runId}`);
    if (data.status === "running") {
      await resumeSearchRun(runId);
      return;
    }
    if (data.status === "done" || data.status === "interrupted") {
      await renderSearchResults(data, resultsEl, reportEl, runId);
      if (data.status === "interrupted") {
        prependResultsBanner(resultsEl, "warn", data.error || "任务已中断");
      }
      renderResearchActions();
    }
  } catch (err) {
    resultsEl.innerHTML = `<div class="alert alert-error">${escapeHtml(err.message)}</div>`;
  }
}

function toggleResearchNoteForm(show) {
  const form = document.getElementById("research-note-form");
  if (!form) return;
  if (show) {
    form.classList.remove("hidden");
    document.getElementById("research-note-input")?.focus();
  } else {
    form.classList.add("hidden");
    const input = document.getElementById("research-note-input");
    if (input) input.value = "";
  }
}

async function saveResearchNote() {
  if (!workspaceSession.treeId) return;
  const input = document.getElementById("research-note-input");
  const text = input?.value.trim();
  if (!text) {
    showResearchFeedback("请输入笔记内容", "warn");
    return;
  }
  try {
    await api("POST", `/api/research/trees/${workspaceSession.treeId}/nodes`, {
      parent_id: workspaceSession.parentNodeId,
      kind: "note",
      title: text.slice(0, 40),
      payload: text,
    });
    toggleResearchNoteForm(false);
    clearResearchFeedback();
    await refreshResearchTree(workspaceSession.parentNodeId);
  } catch (err) {
    showResearchFeedback(err.message);
  }
}

function showForkBanner(runId) {
  showWorkspaceAlert(
    "fork-banner",
    '分叉搜罗：将继承上一轮报告与有用/噪音反馈。修改关键词后点「开始搜罗」。'
      + ' <button type="button" class="btn btn-sm btn-ghost" id="btn-cancel-fork">取消分叉</button>',
    "info",
  );
  document.getElementById("btn-cancel-fork")?.addEventListener("click", () => {
    workspaceSession.forkFromRunId = null;
    hideWorkspaceAlert("fork-banner");
  });
  const queryInput = document.getElementById("search-query");
  queryInput?.focus();
  queryInput?.scrollIntoView({ behavior: "smooth", block: "center" });
}

function forkSearchFromRun(runId) {
  if (!runId) return;
  workspaceSession.forkFromRunId = runId;
  const input = document.getElementById("search-query");
  if (input && !input.value.trim()) {
    api("GET", `/api/runs/${runId}`)
      .then((d) => {
        if (d.query) input.value = d.query;
      })
      .catch(() => {});
  }
  document.getElementById("opt-create-research-tree").checked = true;
  showForkBanner(runId);
}

async function generateResearchInsight(runId) {
  if (!workspaceSession.treeId || !runId) {
    showResearchFeedback("请先选中研究树中的一轮搜罗", "warn");
    return;
  }
  const btn = document.getElementById("btn-research-insight");
  if (btn) {
    btn.disabled = true;
    btn.textContent = "归纳中…";
  }
  clearResearchFeedback();
  try {
    const result = await api("POST", "/api/research/insight", {
      tree_id: workspaceSession.treeId,
      run_id: runId,
      parent_node_id: insightParentNodeId(runId),
    });
    const newId = result.node?.id;
    showToast("研究要点已生成", "success");
    switchWorkspacePanel("research");
    await refreshResearchTree(newId || workspaceSession.selectedNodeId);
    if (newId) {
      workspaceSession.selectedNodeId = newId;
      setWorkspaceParentNodeId(newId);
      showResearchNodeDetail(findResearchNode(workspaceSession.currentTree, newId));
    }
  } catch (err) {
    showResearchFeedback(err.message || "归纳失败，请确认已配置 DeepSeek API Key");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = "归纳要点";
    }
    renderResearchActions();
  }
}

function renderResearchSuggestChips(queries) {
  const wrap = document.getElementById("research-suggested-queries");
  if (!wrap) return;
  if (!queries.length) {
    wrap.classList.add("hidden");
    wrap.innerHTML = "";
    return;
  }
  wrap.classList.remove("hidden");
  wrap.innerHTML = `<span class="toolbar-label">建议深挖（点击填入搜索框）</span>${queries
    .map((q) => `<button type="button" class="chip chip-btn" data-suggest-query="${escapeHtml(q)}">${escapeHtml(q)}</button>`)
    .join("")}`;
  wrap.querySelectorAll("[data-suggest-query]").forEach((chipBtn) => {
    chipBtn.addEventListener("click", () => {
      const input = document.getElementById("search-query");
      if (input) {
        input.value = chipBtn.dataset.suggestQuery;
        input.focus();
      }
      document.getElementById("search-form")?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  });
}

async function suggestResearchQueries(runId) {
  if (!runId) {
    showResearchFeedback("请先选中研究树中的一轮搜罗", "warn");
    return;
  }
  const btn = document.getElementById("btn-research-suggest");
  if (btn) {
    btn.disabled = true;
    btn.textContent = "生成中…";
  }
  clearResearchFeedback();
  try {
    const data = await api("POST", "/api/research/suggest-queries", {
      run_id: runId,
      tree_id: workspaceSession.treeId,
    });
    const queries = data.queries || [];
    if (!data.ok && data.error) {
      showResearchFeedback(data.error, "warn");
      return;
    }
    if (!queries.length) {
      showResearchFeedback("暂无建议，请勾选「本轮情报报告」完成搜罗后再试", "warn");
      return;
    }
    renderResearchSuggestChips(queries);
    switchWorkspacePanel("research");
    showToast(`已生成 ${queries.length} 条建议查询`, "success");
  } catch (err) {
    showResearchFeedback(err.message || "建议查询失败，请确认已配置 DeepSeek API Key");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = "建议查询";
    }
    renderResearchActions();
  }
}

function initResearchNoteForm() {
  document.getElementById("btn-research-note-save")?.addEventListener("click", () => void saveResearchNote());
  document.getElementById("btn-research-note-cancel")?.addEventListener("click", () => toggleResearchNoteForm(false));
  document.getElementById("research-note-input")?.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      void saveResearchNote();
    }
  });
}

async function checkAuthBanner() {
  const banner = document.getElementById("auth-banner");
  const sourceHint = document.getElementById("source-auth-hint");
  const checked = [...document.querySelectorAll("input[name='sources']:checked")].map((el) => el.value);
  try {
    const data = await api("GET", "/api/auth/status");
    const fails = data.items.filter((i) => !i.ok && (i.key === "zhihu" || i.key === "bilibili"));
    if (banner) {
      if (fails.length) {
        banner.classList.remove("hidden");
        banner.innerHTML = `核心来源未登录：${fails.map((f) => escapeHtml(f.name)).join("、")}。请先在浏览器登录，再通过扩展或<a href="/settings">设置页同步 Cookie</a>`;
      } else {
        banner.classList.add("hidden");
      }
    }
    if (sourceHint && checked.length) {
      const authData = await api("GET", `/api/sources/auth-check?sources=${encodeURIComponent(checked.join(","))}`);
      const need = (authData.checks || []).filter(
        (c) =>
          (c.action && !c.ok && c.mode !== "serp_only" && c.mode !== "none") ||
          (c.ui_status === "serp_fallback" && !workspaceSerpFallbackAccepted.includes(c.source)),
      );
      if (need.length) {
        sourceHint.classList.remove("hidden");
        const lines = need
          .slice(0, 4)
          .map((c) => {
            const name = SOURCE_LABELS[c.source] || c.source;
            if (c.ui_status === "serp_fallback") {
              return `${name}：未登录（勾选时已提示登录，或选择「搜索引擎摘要」）`;
            }
            return `${name}：${c.login_hint || c.reason || "请同步 Cookie"}`;
          })
          .join("；");
        sourceHint.innerHTML = `${escapeHtml(lines)}。<a href="/settings">去同步 Cookie</a>`;
      } else {
        sourceHint.classList.add("hidden");
        sourceHint.innerHTML = "";
      }
    } else if (sourceHint) {
      sourceHint.classList.add("hidden");
    }
  } catch (_) {}
}

async function loadPersonaStaleBanner() {
  const el = document.getElementById("persona-stale-banner");
  if (!el) return;
  try {
    const data = await api("GET", "/api/persona/status");
    if (data.auto_rebuild_notice) {
      const n = data.auto_rebuild_notice;
      const at = n.at ? formatRunTime(n.at) : "";
      el.classList.remove("hidden");
      el.className = "alert alert-success";
      el.innerHTML = `心智画像已自动重建（v${escapeHtml(String(n.version || "?"))}${at ? ` · ${escapeHtml(at)}` : ""}）。<button type="button" class="btn btn-sm" id="btn-persona-notice-dismiss">知道了</button> <a href="/persona">查看</a>`;
      document.getElementById("btn-persona-notice-dismiss")?.addEventListener("click", async () => {
        await api("POST", "/api/persona/dismiss-notice");
        el.classList.add("hidden");
      });
      return;
    }
    if (data.stale_prompt ?? (data.stale && data.auto_rebuild_mode === "prompt")) {
      const thresholdBits = [];
      if (data.auto_rebuild_threshold) thresholdBits.push(`新增行为达到 ${data.auto_rebuild_threshold} 条`);
      if (data.auto_rebuild_max_age_hours) thresholdBits.push(`距离上次构建超过 ${data.auto_rebuild_max_age_hours} 小时`);
      const thresholdText = thresholdBits.length ? `（${thresholdBits.join("，或")}）` : "";
      el.classList.remove("hidden");
      el.className = "alert alert-warn";
      el.innerHTML = `画像可能已过时${escapeHtml(thresholdText)}。<button type="button" class="btn btn-sm" id="btn-persona-rebuild-inline">立即重建</button> <a href="/persona">详情</a>`;
      document.getElementById("btn-persona-rebuild-inline")?.addEventListener("click", async () => {
        try {
          await api("POST", "/api/persona/build?review=true");
          el.classList.add("hidden");
          showToast("画像已重建", "success");
        } catch (err) {
          showToast(err.message, "error");
        }
      });
      return;
    }
    el.classList.add("hidden");
  } catch (_) {
    el.classList.add("hidden");
  }
}

function stepLabel(name) {
  return formatStepLabel(name);
}

function formatElapsedMs(ms) {
  const sec = Math.max(0, Math.floor(ms / 1000));
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return m > 0 ? `${m}:${String(s).padStart(2, "0")}` : `${s}s`;
}

function formatEtaSeconds(sec) {
  if (sec == null || sec === "" || Number.isNaN(Number(sec))) return "";
  const n = Math.max(0, Math.ceil(Number(sec)));
  if (n <= 3) return "即将完成";
  if (n < 60) return `约 ${n} 秒`;
  if (n < 3600) return `约 ${Math.ceil(n / 60)} 分钟`;
  return `约 ${Math.ceil(n / 3600)} 小时`;
}

function setSearchBusy(busy) {
  const btn = document.getElementById("btn-search-submit");
  const queueBtn = document.getElementById("btn-search-queue");
  if (btn) {
    btn.disabled = busy;
    btn.textContent = busy ? "提交中…" : "开始搜罗";
    btn.setAttribute("aria-busy", busy ? "true" : "false");
  }
  if (queueBtn) {
    queueBtn.disabled = busy;
  }
}

function normalizeStepName(raw) {
  return String(raw || "")
    .replace(/^\d+_/, "")
    .replace(/\.json$/, "");
}

function renderJobProgressPanel(container, state, options = {}) {
  if (!container) return;
  if (
    state.boundGen != null &&
    state.runId &&
    !isActiveSearchSession(state.boundGen, state.runId)
  ) {
    return;
  }
  const {
    labelFn = stepLabel,
    showCancel = false,
    cancelUrl = "",
    showPartial = false,
    forcePercent = null,
    tickOnly = false,
  } = options;
  const phase = normalizeStepName(state.phase);
  const label = labelFn(phase);
  const detail = state.detail || "";
  const startedAt = state.startedAt ? new Date(state.startedAt).getTime() : Date.now();
  const elapsed = formatElapsedMs(Date.now() - startedAt);
  if (tickOnly) {
    const elapsedEl = container.querySelector(".search-progress-elapsed");
    if (elapsedEl) elapsedEl.textContent = elapsed;
    return;
  }
  const completed = state.completedSteps || [];
  const collectDone = Number(state.collectDone) || 0;
  const collectTotal = Number(state.collectTotal) || 0;
  const itemsFound = Number(state.itemsFound) || 0;
  const eta = formatEtaSeconds(state.etaSec);
  const stepDone = Number(state.stepDone) || 0;
  const stepTotal = Number(state.stepTotal) || 0;
  let pct =
    forcePercent != null
      ? forcePercent
      : stepTotal > 0
        ? Math.min(100, Math.round((stepDone / stepTotal) * 100))
        : collectTotal > 0
          ? Math.min(100, Math.round((collectDone / collectTotal) * 100))
          : Number(state.percent) || 0;
  if (state.percent != null && stepTotal > 0) pct = Math.min(100, Number(state.percent) || pct);
  const showBar = (phase === "collect_all" && collectTotal > 0) || stepTotal > 0 || forcePercent != null;
  const currentUrl = (state.currentUrl || "").trim();
  const recent = state.recentUrls || [];
  const partialItems = state.partialItems || [];

  const stepsHtml = completed
    .map((s) => {
      const name = labelFn(normalizeStepName(s.step));
      const ms = s.duration_ms != null ? ` · ${(s.duration_ms / 1000).toFixed(1)}s` : "";
      const summary = s.summary ? ` — ${escapeHtml(String(s.summary))}` : "";
      const err = s.status === "error" ? " search-step-error" : "";
      return `<li class="search-progress-step done${err}"><span class="search-progress-check">✓</span> ${escapeHtml(name)}${escapeHtml(ms)}${summary}</li>`;
    })
    .join("");

  const activeStepHtml = phase
    ? `<li class="search-progress-step is-active"><span class="search-progress-pulse" aria-hidden="true"></span>${escapeHtml(label)}</li>`
    : "";

  const statsParts = [];
  if (itemsFound > 0) statsParts.push(`已找到 ${itemsFound} 条`);
  if (phase === "collect_all" && collectTotal > 0) statsParts.push(`${collectDone}/${collectTotal}`);
  if (stepTotal > 0 && phase !== "collect_all") statsParts.push(`${stepDone}/${stepTotal}`);
  if (eta) statsParts.push(`剩余 ${eta}`);
  const statsHtml = statsParts.length
    ? `<div class="search-progress-stats muted">${escapeHtml(statsParts.join(" · "))}</div>`
    : "";

  const barHtml = showBar
    ? `<div class="search-progress-bar" role="progressbar" aria-valuenow="${pct}" aria-valuemin="0" aria-valuemax="100"><div class="search-progress-bar-fill" style="width:${pct}%"></div></div>`
    : "";

  const urlHtml = currentUrl.startsWith("http")
    ? `<div class="search-progress-url muted">当前：<a href="${escapeHtml(currentUrl)}" target="_blank" rel="noopener">${escapeHtml(currentUrl.length > 72 ? `${currentUrl.slice(0, 69)}…` : currentUrl)}</a></div>`
    : "";

  const recentHtml = recent.length
    ? `<ul class="search-progress-recent">${recent
        .slice(0, 4)
        .map(
          (r) =>
            `<li><a href="${safeHref(r.url)}" target="_blank" rel="noopener">${escapeHtml((r.title || r.url || "").slice(0, 60))}</a></li>`
        )
        .join("")}</ul>`
    : "";

  const partialHtml =
    showPartial && partialItems.length
      ? `<ul class="search-progress-partial">${partialItems
          .slice(-6)
          .map((item) => {
            const title = escapeHtml((item.title || item.url || "无标题").slice(0, 72));
            const src = escapeHtml(sourceLabel(item.source || ""));
            const rel = item.relevance != null ? ` · ${Math.round(Number(item.relevance) * 100)}%` : "";
            const href = safeHref(item.url);
            const link = href
              ? `<a href="${escapeHtml(href)}" target="_blank" rel="noopener">${title}</a>`
              : title;
            return `<li><span class="chip chip-sm">${src}</span> ${link}<span class="muted">${rel}</span></li>`;
          })
          .join("")}</ul>`
      : "";

  const cancelHtml =
    showCancel && cancelUrl
      ? `<button type="button" class="btn btn-sm btn-ghost job-progress-cancel" data-cancel-url="${escapeHtml(cancelUrl)}">取消</button>`
      : "";

  container.innerHTML = `
    <div class="search-progress card card-flat search-progress-sticky">
      <div class="search-progress-head">
        <span class="search-progress-spinner" aria-hidden="true"></span>
        <div class="search-progress-main">
          <div class="search-progress-phase is-active">${escapeHtml(label)}</div>
          <div class="search-progress-detail muted" aria-live="polite">${escapeHtml(detail || "处理中…")}</div>
        </div>
        ${cancelHtml}
        <span class="search-progress-elapsed muted" title="已用时间">${escapeHtml(elapsed)}</span>
      </div>
      ${barHtml}
      ${statsHtml}
      ${urlHtml}
      ${recentHtml}
      ${partialHtml}
      ${stepsHtml || activeStepHtml ? `<ol class="search-progress-steps">${stepsHtml}${activeStepHtml}</ol>` : ""}
    </div>`;

  container.querySelector(".job-progress-cancel")?.addEventListener("click", async (ev) => {
    const btn = ev.currentTarget;
    const url = btn.getAttribute("data-cancel-url");
    if (!url || btn.disabled) return;
    btn.disabled = true;
    btn.textContent = "取消中…";
    try {
      await api("POST", url, {});
    } catch (_) {
      btn.disabled = false;
      btn.textContent = "取消";
    }
  });
}

function renderSearchProgressPanel(container, state) {
  renderJobProgressPanel(container, state, {
    showCancel: Boolean(state.runId),
    cancelUrl: state.runId ? `/api/search/${state.runId}/cancel` : "",
    showPartial: true,
  });
}

function applyProgressPatch(state, progress) {
  if (!progress) return;
  if (progress.phase) state.phase = progress.phase;
  if (progress.detail) state.detail = progress.detail;
  if (progress.started_at) state.startedAt = progress.started_at;
  if (progress.completed_steps) state.completedSteps = progress.completed_steps;
  if (progress.collect_done != null) state.collectDone = progress.collect_done;
  if (progress.collect_total != null) state.collectTotal = progress.collect_total;
  if (progress.items_found != null) state.itemsFound = progress.items_found;
  if (progress.eta_sec != null) state.etaSec = progress.eta_sec;
  if (progress.current_url != null) state.currentUrl = progress.current_url;
  if (progress.recent_urls) state.recentUrls = progress.recent_urls;
  if (progress.partial_items) state.partialItems = progress.partial_items;
  if (progress.step_done != null) state.stepDone = progress.step_done;
  if (progress.step_total != null) state.stepTotal = progress.step_total;
  if (progress.percent != null) state.percent = progress.percent;
}

function mountSearchProgress(container, runId = "") {
  workspaceProgressUi?.stop();
  const boundGen = searchSession.generation;
  const state = {
    runId,
    boundGen,
    phase: "starting",
    detail: "正在启动…",
    startedAt: new Date().toISOString(),
    completedSteps: [],
    collectDone: 0,
    collectTotal: 0,
    itemsFound: 0,
    etaSec: null,
    currentUrl: "",
    recentUrls: [],
    partialItems: [],
    stepDone: 0,
    stepTotal: 0,
    percent: 0,
  };
  renderSearchProgressPanel(container, state);
  const timer = setInterval(() => {
    if (!container.querySelector(".search-progress")) {
      return;
    }
    renderJobProgressPanel(container, state, {
      labelFn: stepLabel,
      showCancel: Boolean(state.runId),
      cancelUrl: state.runId ? `/api/search/${state.runId}/cancel` : "",
      showPartial: true,
      tickOnly: true,
    });
  }, 1000);
  const ui = {
    setRunId(id) {
      state.runId = id;
      state.boundGen = searchSession.generation;
      renderSearchProgressPanel(container, state);
    },
    update(progress) {
      applyProgressPatch(state, progress);
      renderSearchProgressPanel(container, state);
    },
    stop() {
      clearInterval(timer);
      if (workspaceProgressUi === ui) workspaceProgressUi = null;
    },
  };
  workspaceProgressUi = ui;
  return ui;
}

function mountJobProgress(container, { cancelUrl = "", labelFn = stepLabel, showPartial = false } = {}) {
  const state = {
    phase: "starting",
    detail: "正在启动…",
    startedAt: new Date().toISOString(),
    completedSteps: [],
    collectDone: 0,
    collectTotal: 0,
    itemsFound: 0,
    etaSec: null,
    currentUrl: "",
    recentUrls: [],
    partialItems: [],
    stepDone: 0,
    stepTotal: 0,
    percent: 0,
  };
  const render = () =>
    renderJobProgressPanel(container, state, {
      labelFn,
      showCancel: Boolean(cancelUrl),
      cancelUrl,
      showPartial,
    });
  render();
  const timer = setInterval(() => {
    if (!container.querySelector(".search-progress")) {
      clearInterval(timer);
      return;
    }
    render();
  }, 1000);
  return {
    update(progress) {
      applyProgressPatch(state, progress);
      render();
    },
    stop() {
      clearInterval(timer);
    },
  };
}

function sourceLabel(name) {
  return SOURCE_LABELS[name] || name;
}

function formatSimulation(sim, itemId, runId, feedbackMap = {}) {
  if (!sim) return "";
  if (sim.error) {
    return `<div class="sim-block"><p class="alert alert-error">${escapeHtml(sim.error)}</p></div>`;
  }
  if (sim.raw) {
    return `<div class="sim-block"><p class="muted">未能结构化，请重新构建画像或关闭模拟</p></div>`;
  }
  const interest = sim.interest || "neutral";
  const conf = sim.confidence != null && !sim.overridden
    ? ` · ${Math.round(Number(sim.confidence) * 100)}%` : "";
  const verdict = sim.verdict ? escapeHtml(sim.verdict) : interest;
  const reason = sim.reason ? `<p class="sim-reason">${escapeHtml(sim.reason)}</p>` : "";
  const overridden = sim.overridden ? ` <span class="muted">（已覆盖）</span>` : "";
  const overrideBtns = itemId && runId
    ? `<div class="sim-override-btns">
        <button class="btn btn-sm ${interest === "interested" ? "is-active" : ""}" data-sim-override="interested" data-id="${escapeHtml(itemId)}" data-run="${escapeHtml(runId)}">有价值</button>
        <button class="btn btn-sm ${interest === "neutral" ? "is-active" : ""}" data-sim-override="neutral" data-id="${escapeHtml(itemId)}" data-run="${escapeHtml(runId)}">不确定</button>
        <button class="btn btn-sm ${interest === "skip" ? "is-active" : ""}" data-sim-override="skip" data-id="${escapeHtml(itemId)}" data-run="${escapeHtml(runId)}">无价值</button>
      </div>`
    : "";
  return `<div class="sim-block"><span class="sim-badge sim-${escapeHtml(interest)}">${verdict}${conf}</span>${overridden}${reason}${overrideBtns}</div>`;
}

async function loadSetupWizard() {
  const el = document.getElementById("setup-wizard");
  if (!el) return;
  try {
    const data = await api("GET", "/api/setup/status");
    if (data.ready || data.dismissed) {
      el.classList.add("hidden");
      if (data.ready) {
        const noSim = document.getElementById("opt-no-simulate");
        if (noSim) noSim.checked = false;
      }
      return;
    }
    el.classList.remove("hidden");
    const steps = (data.steps || [])
      .map(
        (s) => {
          const badge = s.required === false ? ' <span class="muted">(可选)</span>' : "";
          const label = s.required === false ? escapeHtml(s.label) : `<strong>${escapeHtml(s.label)}</strong>`;
          return `<li class="${s.done ? "done" : "pending"}"><a href="${s.href}">${label}</a>${badge}<span class="muted">${escapeHtml(s.detail)}</span></li>`;
        }
      )
      .join("");
    const tagline = data.tagline ? `<p class="muted">${escapeHtml(data.tagline)}</p>` : "";
    el.innerHTML = `
      <div class="setup-header">
        <h2>入门向导</h2>
        <button type="button" class="btn btn-ghost btn-sm" id="setup-dismiss">稍后再说</button>
      </div>
      ${tagline}
      <p class="muted">按顺序完成<strong>加粗步骤</strong>后，画像模拟与个性化搜罗更准确。</p>
      <ol class="setup-steps">${steps}</ol>
    `;
    document.getElementById("setup-dismiss")?.addEventListener("click", async () => {
      await api("POST", "/api/setup/dismiss", {});
      el.classList.add("hidden");
    }, { once: true });
  } catch (_) {}
}

/* 搜罗工作台 */
function updateSourceSelectionSummary() {
  const el = document.getElementById("source-selection-summary");
  if (!el) return;
  const checked = [...document.querySelectorAll("input[name='sources']:checked")];
  if (!checked.length) {
    el.textContent = "未选择来源";
    return;
  }
  const labels = checked.map((c) => SOURCE_LABELS[c.value] || c.value);
  if (labels.length <= 4) {
    el.textContent = `已选 ${labels.length} 项：${labels.join("、")}`;
    return;
  }
  el.textContent = `已选 ${labels.length} 项：${labels.slice(0, 4).join("、")}…`;
}

function initSourceCatalogUI() {
  const form = document.getElementById("search-form");
  const more = document.querySelector(".source-catalog-more");
  const extCount = document.getElementById("extended-source-count");
  if (extCount) {
    const n = document.querySelectorAll(".source-catalog-extended input[name='sources']").length;
    if (n) extCount.textContent = `（${n} 个可选）`;
  }
  const refresh = () => {
    updateSourceSelectionSummary();
    void refreshSourceChipStatuses();
    void checkAuthBanner();
    if (!more) return;
    const hasExtendedChecked = [
      ...document.querySelectorAll(".source-catalog-extended input[name='sources']:checked"),
    ].length;
    if (hasExtendedChecked) more.open = true;
  };
  form?.addEventListener("change", async (e) => {
    if (e.target?.name === "sources") {
      await handleSourceCheckboxAuth(e.target);
      refresh();
      return;
    }
    if (e.target?.name === "comment_mine_sources") return;
    refresh();
  });
  refresh();
}

function applySearchProfile(profileId, catalogById, { syncSources = true } = {}) {
  const prof = catalogById[profileId];
  const hint = document.getElementById("search-profile-hint");
  if (!prof) {
    if (hint) hint.innerHTML = "";
    return;
  }
  if (hint) {
    let html = `<strong>${escapeHtml(prof.label)}</strong> — ${escapeHtml(prof.summary || "")}`;
    if (prof.detail) {
      html += `<p class="profile-hint-detail">${escapeHtml(prof.detail)}</p>`;
    }
    if (prof.simulate_persona === true) {
      html += `<p class="profile-hint-meta">画像模拟：本模式默认<strong>开启</strong>（可在「更多选项」中调整）</p>`;
    } else if (prof.simulate_persona === false) {
      html += `<p class="profile-hint-meta">画像模拟：本模式默认<strong>关闭</strong></p>`;
    } else {
      html += `<p class="profile-hint-meta">画像模拟：由「更多选项 → 跳过画像模拟」自行决定</p>`;
    }
    hint.innerHTML = html;
  }
  if (syncSources && Array.isArray(prof.sources)) {
    document.querySelectorAll("input[name='sources']").forEach((el) => {
      el.checked = prof.sources.includes(el.value);
    });
  }
  const noSim = document.getElementById("opt-no-simulate");
  if (noSim && prof.simulate_persona === true) noSim.checked = false;
  if (noSim && prof.simulate_persona === false) noSim.checked = true;
  updateSourceSelectionSummary();
  void refreshSourceChipStatuses();
}

function initFloatingNav() {
  const nav = document.getElementById("floating-nav");
  if (!nav) return;
  const tabsEl = document.querySelector(".workspace-panel-tabs");
  const panelMap = {
    "workspace-panel-results": "results",
    "workspace-panel-report": "report",
    "workspace-panel-research": "research",
  };
  const panelIds = Object.keys(panelMap);
  function getActivePanel() {
    const active = document.querySelector(".workspace-panel-tab.active");
    return active ? active.dataset.panel : "results";
  }
  function syncActiveBtn() {
    const active = getActivePanel();
    nav.querySelectorAll(".floating-nav-btn[data-target]").forEach((btn) => {
      const panelId = btn.dataset.target;
      const panelName = panelMap[panelId];
      btn.classList.toggle("active", panelName === active);
    });
  }
  function checkVisibility() {
    if (!tabsEl) return;
    const rect = tabsEl.getBoundingClientRect();
    nav.classList.toggle("visible", rect.bottom < 0);
  }
  nav.querySelectorAll(".floating-nav-btn[data-target]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const panelId = btn.dataset.target;
      const panelEl = document.getElementById(panelId);
      if (!panelEl) return;
      const panelName = panelMap[panelId];
      const tabBtn = document.querySelector(`.workspace-panel-tab[data-panel="${panelName}"]`);
      if (tabBtn && !tabBtn.classList.contains("active")) tabBtn.click();
      const tabsRect = tabsEl ? tabsEl.getBoundingClientRect() : null;
      const targetY = tabsRect ? window.scrollY + tabsRect.bottom : panelEl.getBoundingClientRect().top + window.scrollY;
      window.scrollTo({ top: targetY, behavior: "smooth" });
    });
  });
  nav.querySelector(".floating-nav-top")?.addEventListener("click", () => {
    const target = tabsEl || document.querySelector(".workspace-panel-tabs");
    if (target) {
      const rect = target.getBoundingClientRect();
      window.scrollTo({ top: window.scrollY + rect.top - 8, behavior: "smooth" });
    } else {
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
  });
  window.addEventListener("scroll", checkVisibility, { passive: true });
  checkVisibility();
  syncActiveBtn();
  const observer = new MutationObserver(syncActiveBtn);
  const activeTab = document.querySelector(".workspace-panel-tab.active");
  if (activeTab) observer.observe(activeTab, { attributes: true, attributeFilter: ["class"] });
  document.querySelectorAll(".workspace-panel-tab").forEach((tab) => {
    observer.observe(tab, { attributes: true, attributeFilter: ["class"] });
  });
}

function initWorkspace(profileCatalog, sourceCatalog) {
  const form = document.getElementById("search-form");
  if (!form) return;

  void fetch("/api/health", { credentials: "same-origin" }).catch(() => {});

  if (Array.isArray(sourceCatalog)) {
    sourceCatalog.forEach((group) => {
      (group.sources || []).forEach((s) => {
        if (s.id) {
          SOURCE_LABELS[s.id] = s.label || s.id;
          SOURCE_CATALOG_META[s.id] = s;
        }
      });
    });
  }

  const catalogById = Object.fromEntries((profileCatalog || []).map((p) => [p.id, p]));

  const params = new URLSearchParams(window.location.search);
  const q = params.get("q");
  const runParam = params.get("run");
  if (q) document.getElementById("search-query").value = q;

  const profileSel = document.getElementById("search-profile");
  profileSel?.addEventListener("change", () => {
    applySearchProfile(profileSel.value, catalogById);
    void refreshExpandedQueries();
  });
  if (profileSel) applySearchProfile(profileSel.value, catalogById);
  initSourceCatalogUI();
  initCommentMineUI(sourceCatalog);

  checkAuthBanner();
  loadSetupWizard();
  void initWorkspaceContext();
  initResearchNoteForm();
  initResearchViewToggle();
  initResearchTreeToolbar();
  initWorkspacePanelTabs();
  initWorkspaceSplitToggle();
  initWorkspaceInteractionTips();
  initSidebarPollVisibility();
  initReadingToolbar();
  document.addEventListener("click", handleCitationClick);
  void syncResearchTreeSelect();
  void loadWatches();
  void loadSuggestedQueries();
  document.getElementById("btn-watches-refresh")?.addEventListener("click", () => void loadWatches());
  if (workspaceSession.treeId) {
    void refreshResearchTree().then(() => {
      const runId = getActiveResearchRunId();
      if (runId) void loadRunIntoWorkspace(runId);
    });
  } else if (getActiveResearchRunId()) {
    void loadRunIntoWorkspace(getActiveResearchRunId());
  }

  initFloatingNav();

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    await submitSearch({ focus: true });
  });
  document.getElementById("btn-search-queue")?.addEventListener("click", () => {
    void submitSearch({ focus: false });
  });
  initSearchTaskPanel();

  const queryInput = document.getElementById("search-query");
  let expandTimer = null;
  queryInput?.addEventListener("input", () => {
    clearTimeout(expandTimer);
    expandTimer = setTimeout(() => refreshExpandedQueries(), 400);
  });
  document.getElementById("opt-include-slurs")?.addEventListener("change", () => refreshExpandedQueries());
  document.getElementById("opt-no-ai")?.addEventListener("change", () => refreshExpandedQueries());
  form.addEventListener("change", (e) => {
    if (e.target?.name === "sources") void refreshExpandedQueries();
  });
  queryInput?.addEventListener("blur", () => refreshExpandedQueries());

  document.getElementById("opt-create-research-tree")?.addEventListener("change", () => void loadSuggestedQueries());

  if (runParam) {
    void resumeSearchRun(runParam);
  } else if (workspaceSession.activeRunId && !q) {
    void resumeSearchRun(workspaceSession.activeRunId);
  } else if (q) {
    runSearch();
  } else {
    void recoverActiveSearches();
  }
}

async function refreshExpandedQueries() {
  const gen = ++expandSession.generation;
  const wrap = document.getElementById("expanded-queries-wrap");
  const chips = document.getElementById("expanded-queries");
  const countEl = document.getElementById("expanded-queries-count");
  const query = document.getElementById("search-query")?.value.trim();
  if (!wrap || !chips || !query || query.length < 2) {
    wrap?.classList.add("hidden");
    return;
  }
  try {
    const sources = [...document.querySelectorAll("input[name='sources']:checked")].map((el) => el.value);
    const profile = document.getElementById("search-profile")?.value || "default";
    const overrides = getSourceOverrides();
    const expandBody = {
      query,
      sources,
      profile,
      no_ai: document.getElementById("opt-no-ai")?.checked || false,
      include_slurs: document.getElementById("opt-include-slurs")?.checked !== false,
    };
    if (overrides) expandBody.source_overrides = overrides;
    const data = await api("POST", "/api/search/expand", expandBody);
    if (gen !== expandSession.generation) return;
    const terms = data.queries_used || data.expanded_queries || [query];
    const foreignTerms = data.foreign_queries || [];
    if (terms.length <= 1 && !foreignTerms.length) {
      wrap.classList.add("hidden");
      return;
    }
    wrap.classList.remove("hidden");
    if (countEl) {
      const persisted = data.discover_meta?.persist?.saved;
      const added = (data.discover_meta?.persist?.added_aliases || []).length
        + (data.discover_meta?.persist?.added_slurs || []).length;
      const parts = [];
      if (terms.length > 1) parts.push(`中文 ${terms.length}`);
      if (foreignTerms.length) parts.push(`外文 ${foreignTerms.length}`);
      countEl.textContent = parts.length ? `(${parts.join("，")}${persisted && added ? `，新沉淀 ${added}` : ""})` : "";
    }
    const network = new Set(data.network_aliases || data.discover_meta?.discovered_aliases || []);
    chips.innerHTML = terms
      .map((t) => {
        const tag = network.has(t) ? "chip chip-network chip-btn" : "chip chip-static chip-btn";
        const label = network.has(t) ? `${escapeHtml(t)} · 联网` : escapeHtml(t);
        return `<button type="button" class="${tag}" data-expand-term="${escapeHtml(t)}" title="点击填入搜索框">${label}</button>`;
      })
      .join("");
    chips.querySelectorAll("[data-expand-term]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const input = document.getElementById("search-query");
        if (input) input.value = btn.dataset.expandTerm || "";
      });
    });
    const foreignWrap = document.getElementById("foreign-queries-wrap");
    const foreignEl = document.getElementById("foreign-queries");
    const foreignHint = document.getElementById("foreign-expand-hint");
    if (foreignWrap && foreignEl) {
      if (foreignTerms.length) {
        foreignWrap.classList.remove("hidden");
        foreignEl.innerHTML = foreignTerms
          .map(
            (t) =>
              `<button type="button" class="chip chip-static chip-btn" data-expand-term="${escapeHtml(t)}" title="外文检索词">${escapeHtml(t)}</button>`
          )
          .join("");
        foreignEl.querySelectorAll("[data-expand-term]").forEach((btn) => {
          btn.addEventListener("click", () => {
            const input = document.getElementById("search-query");
            if (input) input.value = btn.dataset.expandTerm || "";
          });
        });
      } else {
        foreignWrap.classList.add("hidden");
        foreignEl.innerHTML = "";
      }
    }
    if (foreignHint) {
      const fe = data.foreign_expand || {};
      if (fe.degraded) {
        foreignHint.innerHTML =
          '未配置代理：国际信源可能降级，可在<a href="/settings#tunables">设置页 → 运行参数 → 外文信源</a>配置 HTTP 代理。';
      } else if (fe.reason === "intl_degraded_no_proxy") {
        foreignHint.textContent = "国外信源已降级（无代理）。";
      } else {
        foreignHint.textContent = "";
      }
    }
    updateSourceRoutingHint(data.source_routing);
    renderSourcePlanPanel(data.source_plan, data.source_routing);
  } catch (_) {
    if (gen !== expandSession.generation) return;
    wrap.classList.add("hidden");
    if (countEl) countEl.textContent = "（关联词暂不可用）";
  }
}

function buildSourcePlanInnerHtml(plan, routing) {
  const chain = plan?.reasoning_chain || [];
  const breakdown = routing?.score_breakdown || {};
  const keywords = plan?.topic_keywords || [];
  let html = "";
  if (plan?.topic_summary) {
    html += `<p class="source-plan-summary"><strong>话题：</strong>${escapeHtml(plan.topic_summary)}</p>`;
  }
  if (keywords.length) {
    html += `<div class="chip-group source-plan-keywords">${keywords
      .map((k) => `<span class="chip chip-static">${escapeHtml(k)}</span>`)
      .join("")}</div>`;
  }
  if (chain.length) {
    html += `<ol class="source-plan-chain">${chain
      .map(
        (step) =>
          `<li><strong>${escapeHtml(step.title || "")}</strong><div class="muted source-plan-thought">${escapeHtml(step.content || "")}</div></li>`
      )
      .join("")}</ol>`;
  }
  const rows = Object.entries(breakdown).sort((a, b) => (b[1].final || 0) - (a[1].final || 0));
  if (rows.length) {
    html += `<p class="muted source-plan-override-hint" role="note">「纠错」列可点 <strong>必采</strong> / <strong>排除</strong> 覆盖 AI 信源决策，下次搜罗同一话题时生效。</p>`;
    html += `<table class="data-table source-plan-table"><thead><tr>
      <th>信源</th><th>规则</th><th>AI</th><th>综合</th><th>决策</th><th>说明</th><th>纠错</th>
    </tr></thead><tbody>${rows
      .map(([sid, row]) => {
        const decision = row.decision === "skipped" ? "跳过" : row.decision === "active" ? "采集" : "—";
        const cls = row.decision === "skipped" ? "source-plan-skipped" : "source-plan-active";
        const forced = workspaceSourceOverrides.force.includes(sid);
        const blocked = workspaceSourceOverrides.block.includes(sid);
        return `<tr class="${cls}">
          <td>${escapeHtml(SOURCE_LABELS[sid] || sid)}</td>
          <td>${row.rule ?? "—"}</td>
          <td>${row.ai ?? "—"}</td>
          <td><strong>${row.final ?? "—"}</strong></td>
          <td>${escapeHtml(decision)}</td>
          <td class="muted">${escapeHtml(row.reason || "")}</td>
          <td class="source-plan-override">
            <button type="button" class="btn btn-xs btn-ghost${forced ? " active" : ""}" data-override-force="${escapeHtml(sid)}" title="强制纳入本次搜罗（覆盖 AI 跳过）">必采</button>
            <button type="button" class="btn btn-xs btn-ghost${blocked ? " active" : ""}" data-override-block="${escapeHtml(sid)}" title="强制排除本次搜罗（覆盖 AI 推荐）">排除</button>
          </td>
        </tr>`;
      })
      .join("")}</tbody></table>`;
  }
  const active = routing?.active_sources || [];
  if (active.length) {
    html += `<p class="muted source-plan-footer">本次采集顺序：${active
      .map((s) => escapeHtml(SOURCE_LABELS[s] || s))
      .join(" → ")}</p>`;
  }
  return html;
}

function renderSourcePlanPanel(plan, routing) {
  const panel = document.getElementById("source-plan-panel");
  const body = document.getElementById("source-plan-body");
  const badge = document.getElementById("source-plan-badge");
  if (!panel || !body) return;

  const chain = plan?.reasoning_chain || [];
  const breakdown = routing?.score_breakdown || {};
  const hasContent = chain.length > 0 || Object.keys(breakdown).length > 0 || routing?.hint;

  if (!hasContent) {
    panel.classList.add("hidden");
    body.innerHTML = "";
    if (badge) badge.textContent = "";
    return;
  }

  panel.classList.remove("hidden");
  const cryptic = routing?.is_cryptic || plan?.is_cryptic;
  if (badge) {
    if (cryptic) badge.textContent = "· 隐晦查询 · AI 加权";
    else if (chain.length) badge.textContent = "· AI 已参与信源决策";
    else if (plan?.ai_invoked === false) badge.textContent = "· 规则回退";
    else badge.textContent = "";
  }

  body.innerHTML = buildSourcePlanInnerHtml(plan, routing);
  body.querySelectorAll("[data-override-force]").forEach((btn) => {
    btn.addEventListener("click", () => setSourceOverride(btn.getAttribute("data-override-force"), "force"));
  });
  body.querySelectorAll("[data-override-block]").forEach((btn) => {
    btn.addEventListener("click", () => setSourceOverride(btn.getAttribute("data-override-block"), "block"));
  });
}

function updateSourceRoutingHint(routing) {
  const el = document.getElementById("source-routing-hint");
  if (!el) return;
  if (!routing?.hint && !(routing?.auto_enabled || []).length && !(routing?.skipped || []).length) {
    el.classList.add("hidden");
    el.innerHTML = "";
    return;
  }
  let html = "";
  if (routing.hint) {
    html += `<div>${escapeHtml(routing.hint)}</div>`;
  }
  const auto = routing.auto_enabled || routing.suggested_sources || [];
  if (auto.length) {
    html += `<div class="source-routing-meta muted mt-1">自动启用：${auto
      .map((src) => escapeHtml(SOURCE_LABELS[src] || src))
      .join("、")}</div>`;
  }
  const skipped = routing.skipped || [];
  if (skipped.length) {
    html += `<div class="source-routing-actions mt-1">${skipped
      .map(
        (src) =>
          `<button type="button" class="btn btn-sm btn-ghost btn-enable-source" data-source="${escapeHtml(src)}">强制启用 ${escapeHtml(SOURCE_LABELS[src] || src)}</button>`
      )
      .join(" ")}</div>`;
  }
  el.innerHTML = html;
  el.classList.remove("hidden");
  el.querySelectorAll(".btn-enable-source").forEach((btn) => {
    btn.addEventListener("click", () => {
      const src = btn.getAttribute("data-source");
      const box = document.querySelector(`input[name='sources'][value='${src}']`);
      if (box) {
        box.checked = true;
        showToast(`已勾选 ${SOURCE_LABELS[src] || src}，下次搜罗将纳入`, "success");
        void refreshExpandedQueries();
      }
    });
  });
}

async function applyWorkspaceDefaults() {
  try {
    const auth = await api("GET", "/api/auth/status");
    const deepseek = auth.items.find((i) => i.key === "deepseek");
    if (deepseek?.ok) {
      const digest = document.getElementById("opt-digest");
      if (digest && !digest.dataset.userTouched) digest.checked = true;
    }
    const persona = await api("GET", "/api/persona/status", null, { timeoutMs: 8000 });
    const hasPersona =
      (persona.version && persona.version > 0) ||
      (persona.hints_count && persona.hints_count > 0) ||
      (persona.recent_topics && persona.recent_topics.length > 0);
    if (hasPersona) {
      const noSim = document.getElementById("opt-no-simulate");
      if (noSim && !noSim.dataset.userTouched) noSim.checked = false;
    }
  } catch (_) {}
  document.getElementById("opt-digest")?.addEventListener("change", (e) => {
    e.target.dataset.userTouched = "1";
    if (e.target.checked && document.getElementById("opt-no-ai")?.checked) {
      showToast("已勾选「跳过 AI」时，本轮情报报告可能无法生成", "warn");
    }
  });
  document.getElementById("opt-no-simulate")?.addEventListener("change", (e) => {
    e.target.dataset.userTouched = "1";
  });
}

async function initWorkspaceContext() {
  await Promise.all([loadPersonaStaleBanner(), applyWorkspaceDefaults()]);
}

function buildSearchRequestBody() {
  const query = document.getElementById("search-query")?.value.trim();
  const sources = [...document.querySelectorAll("input[name='sources']:checked")].map((el) => el.value);
  if (!query) {
    return { error: "请输入要搜罗的话题" };
  }
  if (!sources.length) {
    return { error: "请至少勾选一个来源" };
  }
  const body = {
    query,
    sources,
    limit: parseInt(document.getElementById("search-limit").value, 10) || 10,
    digest: document.getElementById("opt-digest").checked,
    trace: document.getElementById("opt-trace").checked,
    profile: document.getElementById("search-profile").value,
    no_ai: document.getElementById("opt-no-ai").checked,
    no_simulate: document.getElementById("opt-no-simulate").checked,
    ai_instruct: document.getElementById("ai-instruct").value,
    mine_comments: document.getElementById("opt-mine-comments")?.checked !== false,
    include_slurs: document.getElementById("opt-include-slurs")?.checked !== false,
    disabled_ai_steps: [...document.querySelectorAll("input[name='no-ai-step']:checked")].map((el) => el.value),
  };
  const overrides = getSourceOverrides();
  if (overrides) body.source_overrides = overrides;
  if (workspaceSerpFallbackAccepted.length) {
    body.serp_fallback_accepted = [...workspaceSerpFallbackAccepted];
  }
  const commentMineSources = getCommentMineSourcesForSearch();
  if (commentMineSources.length) body.comment_mine_sources = commentMineSources;
  const topParsed = parseInt(document.getElementById("comment-mine-top")?.value, 10);
  if (Number.isFinite(topParsed)) body.comment_mine_top = topParsed;
  if (document.getElementById("opt-create-research-tree")?.checked) {
    if (workspaceSession.treeId) {
      body.tree_id = workspaceSession.treeId;
      body.parent_node_id = workspaceSession.parentNodeId;
    } else {
      body.create_tree = true;
    }
  }
  if (workspaceSession.forkFromRunId) {
    body.fork_from_run_id = workspaceSession.forkFromRunId;
    workspaceSession.forkFromRunId = null;
    hideWorkspaceAlert("fork-banner");
  }
  return { body, query };
}

function resetFocusedSearchWorkspace({ reportPlaceholder = true } = {}) {
  const resultsEl = document.getElementById("search-results");
  const stepsEl = document.getElementById("steps-bar");
  const reportEl = document.getElementById("report-panel");
  const countEl = document.getElementById("results-count");
  const askSection = document.getElementById("ask-section");
  const askHistory = document.getElementById("ask-history");
  if (resultsEl) resultsEl.innerHTML = "";
  if (stepsEl) stepsEl.innerHTML = "";
  if (countEl) countEl.textContent = "";
  renderSearchTimeline(null);
  renderSourcePlanPanel(null, null);
  updateSourceRoutingHint(null);
  const digestOn = document.getElementById("opt-digest")?.checked;
  if (reportEl) {
    if (reportPlaceholder) {
      reportEl.innerHTML = digestOn
        ? "<p class='muted'>本轮情报报告将在搜罗完成后生成…</p>"
        : "<p class='muted'>未勾选「本轮情报报告」；完成后可逐条查看结果与反馈。</p>";
    } else {
      reportEl.innerHTML = "<p class='muted'>加载中…</p>";
    }
    delete reportEl.dataset.rawMarkdown;
    delete reportEl.dataset.readingWrapped;
  }
  const toc = document.getElementById("report-toc");
  if (toc) {
    toc.classList.add("hidden");
    toc.innerHTML = "";
  }
  if (askSection) askSection.classList.add("hidden");
  if (askHistory) askHistory.innerHTML = "";
  askSession.runId = null;
  askSession.history = [];
  askSession.citationMap = {};
  workspaceSession.citationMap = {};
  workspaceSession.citationUrlExtras = {};
  workspaceSession.searchItems = [];
}

function prepareFocusedSearchWorkspace() {
  const resultsEl = document.getElementById("search-results");
  const stepsEl = document.getElementById("steps-bar");
  const reportEl = document.getElementById("report-panel");
  resetFocusedSearchWorkspace({ reportPlaceholder: true });
  switchWorkspacePanel("results");
  if (stepsEl) stepsEl.innerHTML = "<span class='step-pill active'>准备中</span>";
  return {
    resultsEl,
    stepsEl,
    reportEl,
    progressUi: resultsEl ? mountSearchProgress(resultsEl) : null,
  };
}

async function submitSearch({ focus = true } = {}) {
  const resultsEl = document.getElementById("search-results");
  const built = buildSearchRequestBody();
  if (built.error) {
    if (resultsEl) resultsEl.innerHTML = `<div class='alert alert-warn'>${escapeHtml(built.error)}</div>`;
    return null;
  }
  const { body, query } = built;

  setSearchBusy(true);

  let workspace = null;
  if (focus) {
    beginSearchSession(null);
    workspace = prepareFocusedSearchWorkspace();
  }

  try {
    const start = await api("POST", "/api/search", body, { timeoutMs: 30000 });
    const run_id = start.run_id;
    if (start.tree_id) setResearchTreeId(start.tree_id);
    workspaceSession.selectedNodeId = null;
    searchTaskRegistry.lastStatusByRun.set(run_id, start.status || "running");
    void refreshSearchTaskList();

    if (start.status === "queued") {
      const pos = start.queue_position ? `（第 ${start.queue_position} 位）` : "";
      showToast(`已加入队列${pos}`, "info");
      if (!focus) return start;
      beginSearchSession(run_id);
      searchTaskRegistry.focusedRunId = run_id;
      setActiveSearchRunId(run_id);
      const runLink = document.getElementById("run-link");
      if (runLink) {
        runLink.href = `/runs/${run_id}`;
        runLink.classList.remove("hidden");
        runLink.textContent = "查看运行记录";
      }
      workspace?.progressUi?.setRunId(run_id);
      if (workspace?.resultsEl) {
        workspace.resultsEl.innerHTML = `<div class="alert alert-warn">排队中${escapeHtml(pos)}，即将开始…</div>`;
      }
      void waitUntilSearchRunning(
        run_id,
        workspace?.resultsEl,
        workspace?.stepsEl,
        workspace?.reportEl,
        workspace?.progressUi,
      );
      return start;
    }

    if (!focus) {
      showToast(`搜罗已开始：${query.slice(0, 24)}`, "success");
      return start;
    }

    beginSearchSession(run_id);
    searchTaskRegistry.focusedRunId = run_id;
    setActiveSearchRunId(run_id);
    workspace?.progressUi?.setRunId(run_id);
    const runLink = document.getElementById("run-link");
    if (runLink) {
      runLink.href = `/runs/${run_id}`;
      runLink.classList.remove("hidden");
      runLink.textContent = "查看运行记录";
    }
    subscribeSearchEvents(
      run_id,
      workspace?.resultsEl,
      workspace?.stepsEl,
      workspace?.reportEl,
      workspace?.progressUi,
    );
    return start;
  } catch (err) {
    workspace?.progressUi?.stop();
    if (focus && workspace?.resultsEl) {
      workspace.resultsEl.innerHTML = `<div class="alert alert-error">${escapeHtml(err.message)}</div>`;
      if (workspace.stepsEl) workspace.stepsEl.innerHTML = "";
    } else {
      showToast(err.message || "提交失败", "error");
    }
    return null;
  } finally {
    setSearchBusy(false);
  }
}

async function runSearch() {
  await submitSearch({ focus: true });
}

function finishSearchRun(progressUi, onDone) {
  progressUi?.stop();
  setSearchBusy(false);
  if (typeof onDone === "function") onDone();
}

function subscribeSearchEvents(runId, resultsEl, stepsEl, reportEl, progressUi) {
  const gen = searchSession.generation;
  const seen = new Set();
  let activePill = stepsEl.querySelector(".step-pill.active");
  const es = new EventSource(`/api/search/${runId}/events`);
  searchSession.es = es;
  searchSession.streamClosed = false;

  function markStepDone(stepName) {
    const key = normalizeStepName(stepName);
    if (seen.has(key)) return;
    seen.add(key);
    if (activePill) {
      activePill.classList.remove("active");
      activePill.classList.add("done");
      activePill.textContent = stepLabel(key);
    }
    activePill = document.createElement("span");
    activePill.className = "step-pill active";
    activePill.textContent = "进行中…";
    stepsEl.appendChild(activePill);
  }

  es.onmessage = (ev) => {
    if (!isActiveSearchSession(gen, runId)) return;
    let msg;
    try {
      msg = JSON.parse(ev.data);
    } catch (_) {
      return;
    }
    if (msg.type === "progress" && msg.progress) {
      progressUi?.update(msg.progress);
      const phase = normalizeStepName(msg.progress.phase);
      if (activePill && phase) {
        activePill.textContent = stepLabel(phase);
      }
    }
    if (msg.type === "step") {
      const step = msg.step?.step || msg.file;
      markStepDone(String(step).replace(/^\d+_/, "").replace(/\.json$/, ""));
    }
    if (msg.type === "source_plan") {
      renderSourcePlanPanel(msg.source_plan, msg.source_routing);
      updateSourceRoutingHint(msg.source_routing);
    }
    if (msg.type === "source_error") {
      showSourceErrors(msg.errors || [], resultsEl);
    }
    if (msg.type === "source_warning") {
      showSourceWarnings(msg.warnings || [], resultsEl);
    }
    if (msg.type === "done") {
      finishSearchRun(progressUi, () => {
        searchSession.streamClosed = true;
        es.close();
        if (searchSession.es === es) searchSession.es = null;
        if (activePill) {
          activePill.classList.remove("active");
          activePill.classList.add("done");
          activePill.textContent = "完成";
        }
        setActiveSearchRunId(null);
        searchTaskRegistry.focusedRunId = null;
        void refreshSearchTaskList();
        void (async () => {
          let result = msg.result;
          if (!result) {
            try {
              result = await api("GET", `/api/search/${runId}`, null, { timeoutMs: 120000 });
            } catch (err) {
              resultsEl.innerHTML = `<div class="alert alert-error">${escapeHtml(err.message)}</div>`;
              return;
            }
          }
          await renderSearchResults(result, resultsEl, reportEl, runId);
          void refreshResearchTree();
        })();
      });
    }
    if (msg.type === "cancelled") {
      finishSearchRun(progressUi, () => {
        searchSession.streamClosed = true;
        es.close();
        if (searchSession.es === es) searchSession.es = null;
        resultsEl.innerHTML = `<div class="alert alert-warn">${escapeHtml(msg.error || "搜罗已取消")}</div>`;
        stepsEl.innerHTML = "";
      });
    }
    if (msg.type === "error") {
      finishSearchRun(progressUi, () => {
        searchSession.streamClosed = true;
        es.close();
        if (searchSession.es === es) searchSession.es = null;
        resultsEl.innerHTML = `<div class="alert alert-error">${escapeHtml(msg.error || "搜罗失败")}</div>`;
        stepsEl.innerHTML = "";
      });
    }
    if (msg.type === "timeout") {
      searchSession.streamClosed = true;
      es.close();
      if (searchSession.es === es) searchSession.es = null;
      void pollUntilSearchDone(runId, resultsEl, stepsEl, reportEl, progressUi);
    }
  };

  es.onerror = () => {
    if (searchSession.streamClosed) return;
    searchSession.streamClosed = true;
    es.close();
    if (searchSession.es === es) searchSession.es = null;
    if (!isActiveSearchSession(gen, runId)) return;
    void handleSearchStreamDrop(runId, resultsEl, stepsEl, reportEl, progressUi);
  };
}

async function handleSearchStreamDrop(runId, resultsEl, stepsEl, reportEl, progressUi) {
  try {
    const data = await api("GET", `/api/search/${runId}`);
    if (data.status === "done" || data.status === "interrupted") {
      finishSearchRun(progressUi, () => {
        void renderSearchResults(data, resultsEl, reportEl, runId);
        if (data.status === "interrupted") {
          prependResultsBanner(resultsEl, "warn", data.error || "连接中断，以下为已落盘部分结果");
        }
      });
      setActiveSearchRunId(null);
      return;
    }
    if (data.status === "cancelled" || data.status === "error") {
      finishSearchRun(progressUi, () => {
        const kind = data.status === "cancelled" ? "warn" : "error";
        resultsEl.innerHTML = `<div class="alert alert-${kind}">${escapeHtml(data.error || data.detail || "搜罗失败")}</div>`;
      });
      setActiveSearchRunId(null);
      return;
    }
    if (data.status === "running") {
      prependResultsBanner(resultsEl, "warn", "实时进度连接中断，正在轮询结果…");
      void pollUntilSearchDone(runId, resultsEl, stepsEl, reportEl, progressUi);
      return;
    }
  } catch (err) {
    finishSearchRun(progressUi, () => {
      resultsEl.innerHTML = `<div class="alert alert-warn">无法获取搜罗状态：${escapeHtml(err.message)}。<a href="/?run=${encodeURIComponent(runId)}">点此重试</a></div>`;
    });
  }
}

function consolidateSourceNotices(notices, textKey = "warning") {
  if (!notices?.length) return [];
  const pick = (w) => String(w[textKey] || w.message || w.error || "").trim();
  const exact = new Map();
  const order = [];
  for (const raw of notices) {
    if (!raw || typeof raw !== "object") continue;
    const source = String(raw.source || "?").trim() || "?";
    const text = pick(raw);
    if (!text) continue;
    const key = `${source}\0${text}`;
    if (!exact.has(key)) {
      exact.set(key, { ...raw, source, [textKey]: text, _count: 1 });
      order.push(key);
    } else {
      exact.get(key)._count += 1;
    }
  }

  const apiFailRe = /^(.+? API 失败):\s*(.+)$/i;
  const apiRateRe = /^(.+? API 速率限制.*)$/i;
  const apiBuckets = new Map();
  const apiOrder = [];
  const standaloneKeys = new Set();

  for (const key of order) {
    const entry = exact.get(key);
    const text = pick(entry);
    if (apiFailRe.test(text) || apiRateRe.test(text)) {
      const src = entry.source;
      if (!apiBuckets.has(src)) {
        apiBuckets.set(src, []);
        apiOrder.push(src);
      }
      apiBuckets.get(src).push(entry);
    } else {
      standaloneKeys.add(key);
    }
  }

  const finalize = (entry) => {
    const out = { ...entry };
    delete out._count;
    const count = entry._count || 1;
    const text = pick(out);
    if (count > 1 && text && !text.includes("（共 ")) {
      out[textKey] = `${text}（共 ${count} 次）`;
    }
    return out;
  };

  const truncate = (t, max = 72) => {
    const s = String(t || "").replace(/\s+/g, " ").trim();
    return s.length <= max ? s : `${s.slice(0, max - 1)}…`;
  };

  const mergeApiBucket = (bucket) => {
    const total = bucket.reduce((n, b) => n + (b._count || 1), 0);
    const first = pick(bucket[0]);
    const rate = first.match(apiRateRe);
    if (rate) return finalize({ ...bucket[0], [textKey]: first, _count: total });

    const details = bucket.map((entry) => {
      const text = pick(entry);
      const m = text.match(apiFailRe);
      const detail = truncate(m ? m[2] : text);
      const count = entry._count || 1;
      return count > 1 ? `${detail} ×${count}` : detail;
    });
    const m0 = first.match(apiFailRe);
    const apiLabel = m0 ? m0[1].replace(/ API 失败$/i, "").trim() || m0[1] : "API";
    let summary;
    if (details.length === 1 && total > 1) {
      const base = details[0].split(" ×")[0];
      summary = `${apiLabel} API 失败: ${base}（共 ${total} 次），已尝试回退`;
    } else if (details.length === 1) {
      summary = first;
    } else {
      let shown = details.slice(0, 2).join("；");
      if (details.length > 2) shown += ` 等 ${details.length} 类错误`;
      summary = `${apiLabel} API 多次失败（${total} 次），已尝试回退：${shown}`;
    }
    return { ...bucket[0], [textKey]: summary };
  };

  const out = [];
  const emittedApi = new Set();
  for (const key of order) {
    const entry = exact.get(key);
    const text = pick(entry);
    if (apiFailRe.test(text) || apiRateRe.test(text)) {
      const src = entry.source;
      if (emittedApi.has(src)) continue;
      const bucket = apiBuckets.get(src) || [entry];
      out.push(bucket.length === 1 && (bucket[0]._count || 1) === 1 ? finalize(bucket[0]) : mergeApiBucket(bucket));
      emittedApi.add(src);
      continue;
    }
    if (standaloneKeys.has(key)) out.push(finalize(entry));
  }
  return out;
}

function formatSourceWarningsHtml(warnings) {
  if (!warnings?.length) return "";
  const merged = consolidateSourceNotices(warnings, "warning");
  return `<div id="source-warning-banner" class="alert alert-info search-source-warnings">${merged
    .map((w) => {
      const text = w.warning || w.message || w.error || "";
      return `${escapeHtml(sourceLabel(w.source || "web"))}: ${escapeHtml(text)}`;
    })
    .join("；")}</div>`;
}

function formatSourceErrorsHtml(errors) {
  if (!errors?.length) return "";
  const merged = consolidateSourceNotices(errors, "error");
  const needsPlaywright = merged.some((e) => /playwright/i.test(String(e.error || "")));
  const needsCookie = merged.some((e) => /cookie|401|403|z_c0|SESSDATA/i.test(String(e.error || "")));
  let extra = "";
  if (needsPlaywright) extra += ' <a href="/settings#deps">去设置一键安装 Playwright</a>';
  if (needsCookie) extra += ' <a href="/settings">去设置同步 Cookie</a>';
  const needsNetwork = merged.some((e) => /connection|连接失败|timeout|超时/i.test(String(e.error || "")));
  if (needsNetwork) extra += " 可在 ~/.osint/config.yaml 配置 http.proxy，或检查本机代理/VPN。";
  return `<div id="source-error-banner" class="alert alert-warn search-source-errors">部分来源采集失败：${merged
    .map((e) => `${escapeHtml(sourceLabel(e.source || "web"))}: ${escapeHtml(e.error)}`)
    .join("；")}。${extra}</div>`;
}

function showSourceWarnings(warnings, resultsEl) {
  if (!warnings?.length) return;
  const html = formatSourceWarningsHtml(warnings);
  const host = resultsEl.querySelector(".search-progress") || resultsEl;
  let banner = document.getElementById("source-warning-banner");
  if (banner && !resultsEl.contains(banner)) banner = null;
  if (!banner) {
    host.insertAdjacentHTML("afterbegin", html);
  } else {
    banner.outerHTML = html;
  }
}

function showSourceErrors(errors, resultsEl) {
  if (!errors?.length) return;
  const html = formatSourceErrorsHtml(errors);
  const host = resultsEl.querySelector(".search-progress") || resultsEl;
  let banner = document.getElementById("source-error-banner");
  if (banner && !resultsEl.contains(banner)) banner = null;
  if (!banner) {
    host.insertAdjacentHTML("afterbegin", html);
  } else {
    banner.outerHTML = html;
  }
}

const askSession = { runId: null, history: [], citationMap: {} };
const knowledgeAskSession = { history: [] };

function renderReportPanel(result, reportEl, askSection, runId, resultsEl) {
  const hasItems = (result.items || []).length > 0;
  const resultsRoot = resultsEl || document.getElementById("search-results");
  const citationMap = buildCitationUrlMap(result.items || [], result.citation_urls || {});
  workspaceSession.citationMap = citationMap;
  workspaceSession.citationUrlExtras = result.citation_urls || {};
  workspaceSession.searchItems = result.items || [];
  askSession.citationMap = citationMap;
  if (reportEl && result.report) {
    reportEl.classList.add("intel-report", "markdown-body");
    reportEl.dataset.rawMarkdown = result.report;
    renderMarkdown(reportEl, result.report);
    wrapReportForReading(reportEl);
    wireCitationLinks(reportEl, resultsRoot, citationMap);
    buildReportToc(reportEl);
    updateReportInteractionHint(reportEl, true);
    updateResultsInteractionHint(true, reportEl);
    if (askSection) {
      askSection.classList.remove("hidden");
      initAskPanel(runId, result.items || [], true);
    }
    return true;
  }
  if (reportEl) {
    reportEl.innerHTML = "<p class='muted'>未生成报告。勾选「本轮情报报告」或在高级选项中关闭「跳过 AI」。</p>";
  }
  updateReportInteractionHint(null, false);
  updateResultsInteractionHint(false, null);
  if (askSection) {
    if (hasItems) {
      askSection.classList.remove("hidden");
      initAskPanel(runId, result.items || [], false);
    } else {
      askSection.classList.add("hidden");
    }
  }
  return false;
}

async function renderSearchResults(result, resultsEl, reportEl, runId) {
  if (runId) setCurrentRunId(runId);
  const warnHtml = formatSourceWarningsHtml(result.source_warnings);
  const errorHtml = formatSourceErrorsHtml(result.source_errors);
  const metaHtml = renderSearchMetaBanner(result);
  renderSearchTimeline(result);
  renderSourcePlanPanel(
    result.source_plan || result.query_analysis?.source_plan,
    result.source_routing || result.query_analysis?.source_routing
  );
  updateSourceRoutingHint(result.source_routing || result.query_analysis?.source_routing);
  const items = (result.items || []).filter((i) => !i.signals?.fold_reason);
  const sims = result.simulations || [];
  const simMap = {};
  sims.forEach((s) => { if (s.item_id) simMap[s.item_id] = s; });
  const countEl = document.getElementById("results-count");
  const askSection = document.getElementById("ask-section");

  if (countEl) {
    countEl.textContent = items.length ? `共 ${items.length} 条` : "";
  }

  if (!items.length) {
    resultsEl.innerHTML = `${warnHtml}${errorHtml}${metaHtml}${renderEmptyStateRich("search", "未找到结果", "可尝试换关键词、增加来源或检查 Cookie 设置", `<a href="/settings" class="btn btn-sm btn-secondary">去设置 Cookie</a>`)}`;
    const hasReport = renderReportPanel(result, reportEl, askSection, runId, resultsEl);
    if (hasReport) {
      const splitOn = document.getElementById("workspace-split-view")?.checked;
      if (!splitOn) switchWorkspacePanel("report");
    }
    return;
  }

  const feedbackMap = await loadFeedbackMap(items.map((i) => i.id));
  resultsEl._simMap = simMap;
  const loadMore = items.length > RESULTS_RENDER_BATCH
    ? `<div class="results-load-more-wrap mt-1"><button type="button" class="btn btn-sm btn-secondary" data-load-more-results>加载更多</button></div>`
    : "";
  resultsEl.innerHTML = `${warnHtml}${errorHtml}${metaHtml}${renderResultsToolbar(items.length, result.intel_stats, countItemsBySource(items))}<div class="item-card-list"></div>${loadMore}`;
  initAiStepsToggles();

  if (items.length > RESULTS_RENDER_BATCH) {
    bindResultsToolbar(resultsEl, runId);
    mountIncrementalResultsList(resultsEl, items, simMap, runId, feedbackMap);
  } else {
    resultsEl.querySelector(".item-card-list").innerHTML = items
      .map((item, idx) => renderItemCard(item, simMap[item.id], runId, feedbackMap, idx === 0, idx))
      .join("");
    bindResultsToolbar(resultsEl, runId);
    appendResultCardInteractions(resultsEl, runId, items);
  }

  renderReportPanel(result, reportEl, askSection, runId, resultsEl);
  const hasReport = !!result.report;
  if (hasReport && document.getElementById("opt-digest")?.checked) {
    const splitOn = document.getElementById("workspace-split-view")?.checked;
    if (!splitOn) switchWorkspacePanel("report");
  }
}

function renderSearchTimeline(result) {
  const panel = document.getElementById("search-timeline");
  const body = document.getElementById("search-timeline-body");
  if (!panel || !body) return;
  if (!result) {
    panel.classList.add("hidden");
    body.innerHTML = "";
    return;
  }
  const queries = result.queries_used || result.query_analysis?.queries_used || [];
  const sources = result.collect_sources || result.active_sources || [];
  const warnCount = (result.source_warnings || []).length;
  const errCount = (result.source_errors || []).length;
  const bySource = {};
  (result.items || []).forEach((item) => {
    const src = item.source || "web";
    bySource[src] = (bySource[src] || 0) + 1;
  });
  const parts = [];
  if (queries.length) {
    parts.push(`<div><strong>扩展查询</strong>（${queries.length}）：${queries.map(escapeHtml).join(" · ")}</div>`);
  }
  if (sources.length) {
    parts.push(
      `<div><strong>采集信源</strong>：${sources.map((s) => escapeHtml(sourceLabel(s))).join(" · ")}</div>`,
    );
  }
  const sourceBits = Object.entries(bySource)
    .map(([k, v]) => `${escapeHtml(sourceLabel(k))} ${v}`)
    .join(" · ");
  if (sourceBits) {
    parts.push(`<div><strong>每源条数</strong>：${sourceBits}</div>`);
  }
  if (warnCount || errCount) {
    const bits = [];
    if (warnCount) bits.push(`警告 ${warnCount}`);
    if (errCount) bits.push(`错误 ${errCount}`);
    parts.push(`<div><strong>采集提示</strong>：${bits.join("，")}</div>`);
  }
  if (!parts.length) {
    panel.classList.add("hidden");
    body.innerHTML = "";
    return;
  }
  panel.classList.remove("hidden");
  body.innerHTML = parts.join("");
}

let _aiStepsSeq = 0;

function formatAiParticipationSummary(result) {
  const noAi = result.no_ai === true || result.manifest?.no_ai === true;
  if (noAi) return `<span class="search-meta-ai">AI：已跳过（勾选「跳过 AI」）</span>`;
  const manifestSteps = result.manifest?.steps || [];
  const aiSteps = manifestSteps.filter((s) => s.ai_invoked === true);
  const labels = aiSteps.map((s) => formatStepLabel(s.step)).filter(Boolean);
  if (!labels.length) return `<span class="search-meta-ai">AI：已启用</span>`;

  const detailRows = aiSteps
    .map((s) => {
      const label = formatStepLabel(s.step);
      const input = escapeHtml(s.input_summary || "—");
      const output = escapeHtml(s.output_summary || "—");
      const duration = s.duration_ms ? `${(s.duration_ms / 1000).toFixed(1)}s` : "—";
      return `<tr><td class="ais-col-label">${label}</td><td class="ais-col-input">${input}</td><td class="ais-col-output">${output}</td><td class="ais-col-dur">${duration}</td></tr>`;
    })
    .join("");

  const uid = "ai-steps-" + (++_aiStepsSeq);
  return `
    <span class="search-meta-ai">
      <button type="button" class="ai-steps-toggle" data-ai-steps-target="${uid}">
        AI 参与：${labels.join(" → ")}
        <span class="ai-steps-caret">&#9662;</span>
      </button>
    </span>
    <div class="ai-steps-detail hidden" id="${uid}">
      <table class="ai-steps-table"><thead><tr><th>步骤</th><th>输入</th><th>产出</th><th>耗时</th></tr></thead><tbody>${detailRows}</tbody></table>
    </div>`;
}

function initAiStepsToggles() {
  document.querySelectorAll(".ai-steps-toggle").forEach((btn) => {
    if (btn.dataset.boundAiSteps) return;
    btn.dataset.boundAiSteps = "1";
    btn.addEventListener("click", () => {
      const targetId = btn.dataset.aiStepsTarget;
      const panel = document.getElementById(targetId);
      if (!panel) return;
      const caret = btn.querySelector(".ai-steps-caret");
      if (panel.classList.toggle("hidden")) {
        if (caret) caret.textContent = "\u25B6";
      } else {
        if (caret) caret.textContent = "\u25BC";
      }
    });
  });
}

function renderSearchMetaBanner(result) {
  const queries = result.queries_used || result.query_analysis?.queries_used || [];
  const discovered = result.discover_meta?.discovered_aliases || [];
  const parts = [];
  parts.push(formatAiParticipationSummary(result));
  if (queries.length > 1) {
    parts.push(`扩展查询 ${queries.length} 个：${queries.slice(0, 6).map(escapeHtml).join(" · ")}`);
  }
  if (discovered.length) {
    parts.push(`联网发现关联词：${discovered.slice(0, 8).map(escapeHtml).join(" · ")}`);
  }
  const routing = result.source_routing || result.query_analysis?.source_routing;
  const plan = result.source_plan || result.query_analysis?.source_plan;
  if (routing?.hint) {
    parts.push(escapeHtml(routing.hint));
  }
  if (plan?.topic_summary) {
    parts.push(`话题：${escapeHtml(plan.topic_summary)}`);
  }
  const stats = result.intel_stats;
  if (stats && (stats.new_count != null || stats.seen_count != null)) {
    parts.push(
      `本轮情报：新增 ${Number(stats.new_count) || 0} 条 · 已见过 ${Number(stats.seen_count) || 0} 条`,
    );
  }
  const knowledge = result.knowledge_audit?.summary || {};
  if (
    knowledge.linked_count != null
    || knowledge.known_url_count != null
    || knowledge.supplements_count != null
    || knowledge.project_linked_count != null
    || knowledge.persona_overlap_count != null
    || knowledge.followup_count != null
  ) {
    parts.push(
      `知识联动：关联 ${Number(knowledge.linked_count) || 0} 条 · 库中已有 ${Number(knowledge.known_url_count) || 0} 条 · 补充旧知识 ${Number(knowledge.supplements_count) || 0} 条 · 挂到项目 ${Number(knowledge.project_linked_count) || 0} 条 · 贴合画像 ${Number(knowledge.persona_overlap_count) || 0} 条 · 带后续问题 ${Number(knowledge.followup_count) || 0} 条`,
    );
  }
  const bySource = {};
  (result.items || []).forEach((item) => {
    const src = item.source || "web";
    bySource[src] = (bySource[src] || 0) + 1;
  });
  const sourceBits = Object.entries(bySource)
    .map(([k, v]) => `${escapeHtml(sourceLabel(k))} ${v}`)
    .join(" · ");
  if (sourceBits) parts.push(`来源分布：${sourceBits}`);
  if (!parts.length) return "";
  return `<div class="alert alert-info search-meta-banner">${parts.join("<br>")}</div>`;
}

function itemCommentCount(item) {
  const comments = item.layers?.comments?.length ? item.layers.comments : item.personal?.openapi_comments;
  return Array.isArray(comments) ? comments.length : 0;
}

function renderKnowledgeLinkageSection(item) {
  const linkage = knowledgeLinkage(item);
  if (!linkage) return "";
  const rows = [];
  if (linkage.known_url) {
    rows.push("<p class=\"muted\">这条内容的原始链接已经在知识库里出现过，可直接回到旧知识脉络继续研究。</p>");
  } else if (linkage.supplements_existing) {
    rows.push("<p class=\"muted\">这条内容能补充库中已有材料，适合并入现有研究线索。</p>");
  }
  if (linkage.matching_concepts?.length) {
    rows.push(
      `<div class="chip-group">${linkage.matching_concepts
        .slice(0, 8)
        .map((name) => `<span class="chip">${escapeHtml(name)}</span>`)
        .join("")}</div>`,
    );
  }
  if (linkage.project) {
    rows.push(`<p><strong>关联项目：</strong>${escapeHtml(linkage.project)}</p>`);
  }
  if (linkage.persona_overlap?.length) {
    rows.push(`<p><strong>与当前画像重合：</strong>${linkage.persona_overlap.slice(0, 6).map(escapeHtml).join("；")}</p>`);
  }
  if (linkage.related_titles?.length) {
    rows.push(
      `<p><strong>可衔接旧条目：</strong>${linkage.related_titles.slice(0, 4).map(escapeHtml).join("；")}</p>`,
    );
  }
  if (linkage.related_reasons?.length) {
    rows.push(
      `<p class="muted"><strong>关联原因：</strong>${linkage.related_reasons.slice(0, 4).map(escapeHtml).join("；")}</p>`,
    );
  }
  if (linkage.followups?.length) {
    rows.push(
      `<ul class="key-points">${linkage.followups
        .slice(0, 3)
        .map((q) => `<li>${escapeHtml(q)}</li>`)
        .join("")}</ul>`,
    );
  }
  if (!rows.length) return "";
  return `<details class="item-section item-section-knowledge" open>
    <summary class="item-section-summary">知识联动</summary>
    <div class="item-section-body">${rows.join("")}</div>
  </details>`;
}

function renderItemCard(item, sim, runId, feedbackMap = {}, expandedDefault = false, cardIndex = null) {
  const src = item.source || "web";
  const itemHref = safeHref(item.url);
  const fold = item.signals?.fold_reason
    ? `<div class="fold-reason">${escapeHtml(item.signals.fold_reason)}</div>` : "";
  const seenBadge = item.personal?.already_seen
    ? `<span class="source-badge source-seen">已关注</span>` : "";
  const simHtml = formatSimulation(sim, item.id, runId, feedbackMap);
  const itemRating = feedbackMap[`item:${item.id}`] || "";
  const rawText = bilibiliRawContent(item).trim();
  const teaser = escapeHtml(itemCardTeaser(item));
  const flags = itemSectionFlags(item, sim);
  const flagsHtml = flags.length
    ? `<div class="item-card-flags">${flags
        .map((f) => {
          const flag = typeof f === "string" ? { label: f, title: "" } : f;
          const title = flag.title ? ` title="${escapeHtml(flag.title)}"` : "";
          return `<span class="item-flag"${title}>${escapeHtml(flag.label || "")}</span>`;
        })
        .join("")}</div>`
    : "";
  const expandedClass = expandedDefault ? "is-expanded" : "is-collapsed";
  const ariaExpanded = expandedDefault ? "true" : "false";

  const sections = [];

  if (item.summary) {
    sections.push(`<details class="item-section item-section-summary-block" open>
      <summary class="item-section-summary">AI 摘要</summary>
      <div class="item-section-body">
        <div class="md-content summary-body"></div>
        ${item.key_points?.length ? `<ul class="key-points">${item.key_points.map((p) => `<li>${escapeHtml(p)}</li>`).join("")}</ul>` : ""}
      </div>
    </details>`);
  } else if (item.key_points?.length) {
    sections.push(`<details class="item-section" open>
      <summary class="item-section-summary">要点</summary>
      <div class="item-section-body">
        <ul class="key-points">${item.key_points.map((p) => `<li>${escapeHtml(p)}</li>`).join("")}</ul>
      </div>
    </details>`);
  }

  if (item.layers?.comments_summary) {
    sections.push(`<details class="item-section" open>
      <summary class="item-section-summary">社区观点归纳</summary>
      <div class="item-section-body">
        <div class="md-content comments-summary-body"></div>
        <p class="muted section-hint">以上为 AI 归纳，非事实陈述；可展开下方查看原始热评。</p>
      </div>
    </details>`);
  }

  const linkageSection = renderKnowledgeLinkageSection(item);
  if (linkageSection) sections.push(linkageSection);

  if (rawText) {
    sections.push(`<details class="item-section item-section-raw">
      <summary class="item-section-summary">原始内容</summary>
      <div class="item-section-body raw-section">
        <div class="md-content raw-body"></div>
        ${bilibiliShortRawHint(item, rawText)}
      </div>
    </details>`);
  } else if (item.source === "bilibili" && item.type === "video") {
    sections.push(`<details class="item-section">
      <summary class="item-section-summary">原始内容</summary>
      <div class="item-section-body">
        <p class="muted">B站未获取到简介或字幕；可点「原文」查看。字幕需有效 B 站登录 Cookie，或勾选评论挖掘拉热评。</p>
      </div>
    </details>`);
  }

  if (item.personal?.matched_queries?.length > 1) {
    sections.push(`<p class="item-meta-line muted">命中关联词：${item.personal.matched_queries.map((q) => escapeHtml(q)).join("、")}</p>`);
  }

  if (item.layers?.comments?.length) {
    sections.push(formatCommentsSection(item.layers.comments));
  } else if (item.personal?.openapi_comments?.length) {
    sections.push(formatCommentsSection(item.personal.openapi_comments));
  }

  if (simHtml) {
    sections.push(`<details class="item-section item-section-sim">
      <summary class="item-section-summary">画像模拟</summary>
      <div class="item-section-body">${simHtml}</div>
    </details>`);
  }

  const metrics = [];
  if (item.metrics?.likes) metrics.push(`👍 ${item.metrics.likes}`);
  const commentRows = itemCommentCount(item);
  if (commentRows) {
    metrics.push(`💬 ${commentRows} 条热评`);
  } else if (item.metrics?.comments) {
    metrics.push(`💬 ${item.metrics.comments}`);
  }
  if (item.author) metrics.push(escapeHtml(item.author));

  const enterClass = cardIndex != null && cardIndex < 20 ? " card-enter" : "";
  const staggerStyle = cardIndex != null && cardIndex < 20 ? ` style="--card-i: ${cardIndex}"` : "";

  return `<article class="card item-card item-source-${escapeHtml(src)} ${expandedClass}${enterClass}"${staggerStyle} data-item-id="${escapeHtml(item.id)}" data-item-source="${escapeHtml(src)}" data-citation-id="${escapeHtml(item.personal?.citation_id || "")}" data-item-url="${escapeHtml(itemHref || "")}" data-already-seen="${item.personal?.already_seen ? "1" : "0"}">
    <div class="item-card-header" role="button" tabindex="0" aria-expanded="${ariaExpanded}">
      <span class="item-card-chevron" aria-hidden="true"></span>
      <div class="item-card-head-content">
        <div class="item-card-meta">
          <span class="source-badge source-${escapeHtml(src)}">${escapeHtml(sourceLabel(src))}</span>
          ${item.personal?.citation_id ? `<span class="source-badge citation-badge" title="报告引用编号，与情报报告中的 [${escapeHtml(item.personal.citation_id)}] 对应">[${escapeHtml(item.personal.citation_id)}]</span>` : ""}
          ${seenBadge}
          ${formatRelevanceBadge(item)}
          ${metrics.map((m) => `<span class="item-metric">${m}</span>`).join("")}
        </div>
        <h3 class="item-card-title">${escapeHtml(item.title || "无标题")}</h3>
        <p class="item-card-teaser">${teaser}</p>
        ${flagsHtml}
        ${fold}
      </div>
      <div class="item-card-quick-actions">
        ${itemHref ? `<a class="btn btn-sm btn-secondary" href="${escapeHtml(itemHref)}" target="_blank" rel="noopener">原文</a>` : ""}
      </div>
    </div>
    <div class="item-card-body">
      <div class="item-card-sections">${sections.join("")}</div>
      <div class="actions">
        ${itemHref ? `<a class="btn btn-sm" href="${escapeHtml(itemHref)}" target="_blank" rel="noopener">打开原文</a>` : ""}
        <button class="btn btn-sm btn-secondary" data-save="${escapeHtml(item.url || "")}">收录</button>
        <button class="btn btn-sm btn-ghost" data-research-item="${escapeHtml(item.id || "")}">加入研究</button>
        <button class="${feedbackBtnClass(itemRating === "useful", "btn btn-sm btn-secondary")}" data-base-label="有用" data-feedback="useful" data-id="${escapeHtml(item.id || "")}">${feedbackLabel("有用", itemRating === "useful")}</button>
        <button class="${feedbackBtnClass(itemRating === "noise")}" data-base-label="噪音" data-feedback="noise" data-id="${escapeHtml(item.id || "")}">${feedbackLabel("噪音", itemRating === "noise")}</button>
      </div>
    </div>
  </article>`;
}

async function submitFeedback(rating, targetId, runId, btn) {
  try {
    await api("POST", "/api/feedback", { target_id: targetId, rating, run_id: runId, target_type: "item" });
    const card = btn.closest(".item-card");
    if (card) setFeedbackActive(card, "item", rating);
  } catch (err) {
    btn.classList.add("is-error");
    setTimeout(() => btn.classList.remove("is-error"), 2000);
    showToast(err.message || "反馈提交失败", "error");
  }
}

async function submitSimFeedback(rating, targetId, simVerdict, runId, btn) {
  try {
    await api("POST", "/api/feedback", {
      target_id: targetId,
      rating,
      run_id: runId,
      target_type: "simulation",
      sim_verdict: simVerdict || "",
    });
    const card = btn.closest(".item-card");
    if (card) setFeedbackActive(card, "simulation", rating);
  } catch (err) {
    btn.classList.add("is-error");
    setTimeout(() => btn.classList.remove("is-error"), 2000);
  }
}

async function overrideSimVerdict(targetId, runId, interest, btn) {
  if (!targetId || !runId || !interest) return;
  const card = btn.closest(".item-card");
  const resultsEl = card?.closest("#search-results");
  const simMap = resultsEl?._simMap || {};

  const labelMap = { interested: "有价值", neutral: "不确定", skip: "无价值" };
  const label = labelMap[interest] || interest;

  // Optimistic UI update first
  if (card) {
    card.querySelectorAll("[data-sim-override]").forEach((b) => {
      b.classList.toggle("is-active", b.dataset.simOverride === interest);
    });
  }

  try {
    const result = await api("POST", `/api/runs/${encodeURIComponent(runId)}/sim-override`, {
      item_id: targetId,
      interest: interest,
      confidence: 0.0,
      verdict: "",
      reason: "",
    });
    if (result?.ok && result?.updated_simulation) {
      const sim = simMap[targetId];
      if (sim) {
        sim.interest = interest;
        sim.overridden = true;
        if (interest === "interested") {
          sim.verdict = "用户判定为有价值";
        } else if (interest === "skip") {
          sim.verdict = "用户判定为无价值";
        } else {
          sim.verdict = "用户判定为不确定";
        }
        sim.confidence = 0.0;
        sim.reason = "";
      }
      if (card) {
        const simBlock = card.querySelector(".item-section-sim .item-section-body");
        if (simBlock) {
          simBlock.innerHTML = formatSimulation(sim, targetId, runId, {});
        }
        const badge = card.querySelector(".sim-badge");
        if (badge) {
          badge.className = `sim-badge sim-${interest}`;
          if (interest === "interested") {
            badge.textContent = "用户判定为有价值";
          } else if (interest === "skip") {
            badge.textContent = "用户判定为无价值";
          } else {
            badge.textContent = "用户判定为不确定";
          }
        }
      }
      showToast(`已覆盖 AI 判定 → ${label}`, "success");
    } else {
      showToast(result?.detail || "覆盖失败", "error");
    }
  } catch (err) {
    // Revert optimistic update on error
    if (card) {
      const sim = simMap[targetId];
      card.querySelectorAll("[data-sim-override]").forEach((b) => {
        b.classList.toggle("is-active", sim && b.dataset.simOverride === sim.interest);
      });
    }
    showToast(err.message || "覆盖失败", "error");
  }
}

async function loadSuggestedQueries() {
  const el = document.getElementById("suggested-queries");
  if (!el) return;
  const treeActive = !!workspaceSession.treeId || document.getElementById("opt-create-research-tree")?.checked;
  if (!treeActive) {
    el.classList.add("hidden");
    el.innerHTML = "";
    return;
  }
  el.classList.remove("hidden");
  try {
    const data = await api("GET", "/api/persona/suggested-queries");
    const queries = data.queries || [];
    if (!queries.length) {
      el.innerHTML = `<span class="muted">完成 <a href="/ingest">行为同步</a> 并 <a href="/persona">构建画像</a> 后，这里会显示推荐搜罗话题。</span>`;
      return;
    }
    el.innerHTML = `<span class="toolbar-label">推荐搜罗</span>${queries
      .map((q) => `<button type="button" class="chip chip-btn" data-suggest-query="${escapeHtml(q)}">${escapeHtml(q)}</button>`)
      .join("")}`;
    el.querySelectorAll("[data-suggest-query]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const input = document.getElementById("search-query");
        if (input) input.value = btn.dataset.suggestQuery;
        void runSearch();
      });
    });
  } catch (_) {
    el.innerHTML = `<span class="muted">推荐话题暂不可用 · <a href="/persona">先构建画像</a></span>`;
  }
}

async function saveFromCard(url) {
  try {
    const data = await api("POST", "/api/save", { url });
    showToast(`已收录：${data.item.title || url}`, "success");
  } catch (err) {
    showToast(err.message, "error");
  }
}

async function addSearchItemToResearch(item) {
  if (!item || typeof item !== "object") return;
  try {
    const payload = {
      item,
      tree_id: workspaceSession.treeId || null,
      parent_node_id: insightParentNodeId(workspaceSession.activeRunId) || workspaceSession.parentNodeId || null,
    };
    const data = await api("POST", "/api/research/from-search", payload, { timeoutMs: 30000, retry: 1 });
    if (data.tree?.id) {
      setResearchTreeId(data.tree.id);
      if (data.node?.id) setWorkspaceParentNodeId(data.node.id);
      await refreshResearchTree(data.node?.id || null);
      switchWorkspacePanel("research");
    }
    showToast(`已加入研究树：${item.title || "搜索结果"}`, "success");
  } catch (err) {
    showToast(err.message || "加入研究树失败", "error");
  }
}

function setAskFormBusy(form, busy) {
  const submitBtn = form.querySelector('button[type="submit"]');
  const input = document.getElementById("ask-question");
  form.classList.toggle("is-busy", busy);
  form.setAttribute("aria-busy", busy ? "true" : "false");
  if (submitBtn) {
    submitBtn.disabled = busy;
    submitBtn.textContent = busy ? "发送中…" : "发送";
  }
  if (input) input.disabled = busy;
}

function renderAskPendingBlock(question) {
  const block = document.createElement("div");
  block.className = "card ask-turn ask-turn-pending";
  block.innerHTML = `<p><strong>问:</strong> ${escapeHtml(question)}</p>
    <div class="ask-pending" role="status" aria-live="polite">
      <span class="search-progress-spinner" aria-hidden="true"></span>
      <span>正在生成回答…通常需 10–30 秒，请勿关闭页面</span>
    </div>`;
  return block;
}

function initAskPanel(runId, items = [], hasReport = false) {
  const form = document.getElementById("ask-form");
  const history = document.getElementById("ask-history");
  if (!form) return;
  if (askSession.runId !== runId) {
    askSession.runId = runId;
    askSession.history = [];
    if (history) history.innerHTML = "";
  }
  askSession.citationMap = buildCitationUrlMap(items, workspaceSession.citationUrlExtras || {});
  const itemHint = items.length
    ? `（报告 + ${items.length} 条结果）`
    : "";
  const askTitle = document.querySelector("#ask-section h2");
  if (askTitle) {
    askTitle.textContent = hasReport ? `追问报告${itemHint}` : `追问结果${itemHint}`;
  }
  updateAskInteractionHint(hasReport || items.length > 0);
  const askInput = document.getElementById("ask-question");
  if (askInput) {
    askInput.placeholder = hasReport ? "基于报告继续提问…" : "基于搜索结果继续提问…";
  }
  form.onsubmit = async (e) => {
    e.preventDefault();
    const input = document.getElementById("ask-question");
    const q = input.value.trim();
    if (!q || form.classList.contains("is-busy")) return;
    if (!history) return;

    setAskFormBusy(form, true);
    const pending = renderAskPendingBlock(q);
    history.appendChild(pending);
    history.scrollTop = history.scrollHeight;
    input.value = "";

    try {
      const data = await api(
        "POST",
        "/api/ask",
        {
          question: q,
          run_id: runId,
          history: askSession.history,
          tree_id: workspaceSession.treeId,
          parent_node_id: insightParentNodeId(runId),
        },
        { timeoutMs: 120000 }
      );
      if (data.ok === false) {
        pending.classList.remove("ask-turn-pending");
        pending.innerHTML = `<p><strong>问:</strong> ${escapeHtml(q)}</p><p class="alert alert-error">${escapeHtml(data.error || "追问失败")}</p>`;
        return;
      }
      pending.classList.remove("ask-turn-pending");
      pending.innerHTML = `<p><strong>问:</strong> ${escapeHtml(q)}</p><div class="markdown-body"></div>`;
      const answerEl = pending.querySelector(".markdown-body");
      renderMarkdown(answerEl, data.answer);
      const resultsRoot = document.getElementById("search-results");
      const reportEl = document.getElementById("report-panel");
      wireCitationLinks(answerEl, resultsRoot, askSession.citationMap);
      anchorReportReadingList(answerEl);
      updateAskInteractionHint(true);
      history.scrollTop = history.scrollHeight;
      askSession.history.push({ question: q, answer: data.answer || "" });
      void refreshResearchTree(insightParentNodeId(runId));
    } catch (err) {
      pending.classList.remove("ask-turn-pending");
      pending.innerHTML = `<p><strong>问:</strong> ${escapeHtml(q)}</p><p class="alert alert-error">${escapeHtml(err.message || "追问失败")}</p>`;
      showToast(err.message || "追问失败", "error");
    } finally {
      setAskFormBusy(form, false);
    }
  };
}

/* 收录页 */
function initSave(prefillUrl) {
  const form = document.getElementById("save-form");
  if (!form) return;
  if (prefillUrl) document.getElementById("save-url").value = prefillUrl;
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const msg = document.getElementById("save-message");
    try {
      const data = await api("POST", "/api/save", {
        url: document.getElementById("save-url").value.trim(),
        with_comments: document.getElementById("save-comments").checked,
        no_ai: document.getElementById("save-no-ai").checked,
      });
      msg.className = "alert alert-success";
      msg.textContent = `已收录: ${data.item.title}`;
      loadRecentItems();
    } catch (err) {
      msg.className = "alert alert-error";
      msg.textContent = err.message;
    }
  });
  loadRecentItems();
}

async function loadRecentItems() {
  const el = document.getElementById("recent-items");
  if (!el) return;
  try {
    const data = await api("GET", "/api/knowledge/items?limit=10");
    el.innerHTML = data.items.map((i) =>
      `<div class="card"><a href="${safeHref(i.url)}" target="_blank" rel="noopener">${escapeHtml(i.title)}</a><div class="muted">[${escapeHtml(i.source || "")}]</div></div>`
    ).join("") || "<p class='muted'>暂无收录</p>";
  } catch (_) {
    el.innerHTML = "<p class='muted'>加载失败</p>";
  }
}

/* 知识库 */
function currentKnowledgeSearchState() {
  return {
    q: document.getElementById("knowledge-query")?.value.trim() || "",
    source: document.getElementById("knowledge-source")?.value || "",
    topic: document.getElementById("knowledge-topic")?.value.trim() || "",
    entity: document.getElementById("knowledge-entity")?.value.trim() || "",
    tag: document.getElementById("knowledge-tag")?.value.trim() || "",
    conflict_status: document.getElementById("knowledge-conflict")?.value || "",
    mode: document.querySelector("input[name='knowledge-mode']:checked")?.value || "hybrid",
    explain: document.getElementById("knowledge-explain")?.checked !== false,
  };
}

function renderKnowledgeLinks(host, links) {
  if (!host) return;
  if (!links.length) {
    host.innerHTML = "<p class='muted mt-1'>没有找到可展示的关联条目</p>";
    return;
  }
  host.innerHTML = `<div class="ui-inset-group mt-1">${links.map((link) => {
    const item = link.item || {};
    return `<div class="ui-list-row">
      <div class="ui-list-row-main">
        <div class="item-card-meta">
          <span class="source-badge source-${escapeHtml(item.source || "web")}">${escapeHtml(link.relation_label || "关联")}</span>
          <span class="muted">置信度 ${escapeHtml(String(Math.round((Number(link.confidence) || 0) * 100)))}%</span>
        </div>
        <div class="ui-list-row-title">${escapeHtml(item.title || "无标题")}</div>
        <p class="ui-list-row-sub muted">${escapeHtml(link.evidence || item.summary || item.content?.slice(0, 160) || "")}</p>
      </div>
      <div class="ui-list-row-actions">
        <a class="btn btn-sm btn-secondary" href="${safeHref(item.url)}" target="_blank" rel="noopener">原文</a>
      </div>
    </div>`;
  }).join("")}</div>`;
}

async function loadKnowledgeFilters() {
  try {
    const data = await api("GET", "/api/knowledge/filters?limit=40");
    const topicList = document.getElementById("knowledge-topic-list");
    const entityList = document.getElementById("knowledge-entity-list");
    const tagList = document.getElementById("knowledge-tag-list");
    const sourceSel = document.getElementById("knowledge-source");
    if (topicList) topicList.innerHTML = (data.topics || []).map((row) => `<option value="${escapeHtml(row.value || row.topic || "")}"></option>`).join("");
    if (entityList) entityList.innerHTML = (data.entities || []).map((row) => `<option value="${escapeHtml(row.value || "")}"></option>`).join("");
    if (tagList) tagList.innerHTML = (data.tags || []).map((row) => `<option value="${escapeHtml(row.value || "")}"></option>`).join("");
    if (sourceSel && Array.isArray(data.sources) && data.sources.length) {
      const current = sourceSel.value;
      sourceSel.innerHTML = `<option value="">全部</option>${data.sources.map((row) =>
        `<option value="${escapeHtml(row.value || "")}">${escapeHtml(sourceLabel(row.value || ""))} (${escapeHtml(String(row.count || 0))})</option>`
      ).join("")}`;
      sourceSel.value = current || "";
    }
  } catch (_) {
    // keep page usable even if filter metadata fails
  }
}

function initKnowledge() {
  const params = new URLSearchParams(window.location.search);
  const q = params.get("q") || "";
  const tab = params.get("tab") || "search";
  const url = params.get("url") || "";
  const input = document.getElementById("knowledge-query");
  if (input && q) input.value = q;
  initSegmentedControl(document.getElementById("knowledge-tabs"), {
    onSelect: (name) => switchKnowledgeTab(name),
  });
  if (tab === "save") switchKnowledgeTab("save");
  initSave(url);
  const form = document.getElementById("knowledge-form");
  const ready = prewarmApiToken().catch(() => false);
  if (form) {
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      await searchKnowledge();
    });
    if (q) ready.finally(() => searchKnowledge());
  }
  const askForm = document.getElementById("knowledge-ask-form");
  if (askForm) {
    askForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const inputEl = document.getElementById("knowledge-ask-question");
      const question = inputEl?.value.trim() || "";
      const host = document.getElementById("knowledge-ask-answer");
      if (!question) {
        if (host) host.innerHTML = "<p class='muted'>请输入问题后再追问</p>";
        return;
      }
      if (host) host.innerHTML = "<p class='muted'>正在基于知识库回答…</p>";
      const filters = currentKnowledgeSearchState();
      try {
        const data = await api("POST", "/api/knowledge/rag/ask", {
          question,
          mode: filters.mode,
          source: filters.source || null,
          topic: filters.topic || null,
          entity: filters.entity || null,
          tag: filters.tag || null,
          conflict_status: filters.conflict_status || null,
          history: knowledgeAskSession.history,
        }, { timeoutMs: 45000, retry: 1, prewarm: true });
        if (data.ok === false) {
          if (host) host.innerHTML = `<div class="alert alert-error">${escapeHtml(data.error || "追问失败")}</div>`;
          return;
        }
        knowledgeAskSession.history.push({ question, answer: data.answer || "" });
        knowledgeAskSession.history = knowledgeAskSession.history.slice(-6);
        const refs = (data.evidence || data.hits || []).length
          ? `<div class="mt-1"><strong>RAG 证据</strong><div class="ui-inset-group mt-1">${(data.evidence || data.hits || []).map((hit) => `
              <div class="ui-list-row">
                <div class="ui-list-row-main">
                  <div class="item-card-meta">
                    <span class="source-badge source-web">${escapeHtml(hit.source_channel || "rag")}</span>
                    ${hit.needs_verification ? `<span class="source-badge source-bad">需核查</span>` : ""}
                    ${hit.relation ? `<span class="source-badge source-bilibili">${escapeHtml(hit.relation)}</span>` : ""}
                  </div>
                  <div class="ui-list-row-title">[${escapeHtml(hit.citation || "")}] ${escapeHtml(hit.title || "无标题")}</div>
                  <p class="ui-list-row-sub muted">${escapeHtml(hit.match_reason || hit.relation_reason || (hit.match_reasons || []).join("；") || hit.summary || "")}</p>
                </div>
                <div class="ui-list-row-actions">
                  <a class="btn btn-sm btn-secondary" href="${safeHref(hit.url)}" target="_blank" rel="noopener">原文</a>
                </div>
              </div>
            `).join("")}</div></div>`
          : "";
        const aiMeta = data.ai_used === false
          ? `<div class="alert alert-warning mt-1">${escapeHtml(data.warning || "当前回答未调用 AI，已回退为本地 RAG 证据整理。")}</div>`
          : `<div class="muted mt-1">本次回答: 本地 Graph-RAG 召回 + AI 生成</div>`;
        const followUps = renderKnowledgeFollowUps(data.follow_up_questions || []);
        if (host) {
          host.innerHTML = `${aiMeta}<div class="markdown-body"></div>${refs}${followUps}`;
          renderMarkdown(host.querySelector(".markdown-body"), data.answer || "");
          bindKnowledgeSuggestionButtons(host);
        }
      } catch (err) {
        if (host) host.innerHTML = `<div class="alert alert-error">${escapeHtml(err.message || "追问失败")}</div>`;
      }
    });
  }
  ready.finally(() => {
    loadKnowledgeHealth();
    loadKnowledgeFilters();
    loadKnowledgeCloudStatus();
    loadKnowledgeAiStatus();
    initKnowledgeGraphPanel();
  });
}

async function loadKnowledgeHealth() {
  const el = document.getElementById("knowledge-health-status");
  if (!el) return;
  try {
    const data = await api("GET", "/api/knowledge/health", null, { timeoutMs: 15000, retry: 1, prewarm: true });
    const issues = (data.issues || []).map((msg) => `<div class="alert alert-warning mt-1">${escapeHtml(msg)}</div>`).join("");
    const suggestions = (data.suggestions || []).map((msg) => `<span class="muted">${escapeHtml(msg)}</span>`).join(" · ");
    el.innerHTML = `
      <div class="toggle-row">
        <span class="muted">条目 ${escapeHtml(String(data.item_count || 0))}</span>
        <span class="muted">FTS ${data.fts_ok ? "正常" : "需检查"}</span>
        <span class="muted">概念 ${escapeHtml(String(data.concept_count || 0))}</span>
        <span class="muted">关系 ${escapeHtml(String(data.graph_edge_count || 0))}</span>
      </div>
      ${issues}
      ${suggestions ? `<div class="mt-1">${suggestions}</div>` : ""}
    `;
  } catch (err) {
    el.innerHTML = `<div class="alert alert-error">${escapeHtml(err.message || "知识诊断加载失败")}</div>`;
  }
}

async function loadKnowledgeAiStatus() {
  const el = document.getElementById("knowledge-ai-status");
  if (!el) return;
  try {
    const data = await api("GET", "/api/ai/status", null, { timeoutMs: 12000, retry: 1, prewarm: true });
    const enabled = Number(data.enabled_step_count || 0);
    const total = Number(data.total_step_count || 0);
    const apiReady = data.api_key_configured === true;
    const note = apiReady
      ? "AI 问答与搜罗增强已可用"
      : "当前未配置 AI Key，问答会自动回退为本地证据整理";
    el.innerHTML = `
      <div class="grid-2">
        <div>
          <div><strong>AI 引擎</strong></div>
          <div class="muted">${escapeHtml(data.provider || "")} · ${escapeHtml(data.model || "")}</div>
          <div class="muted">${escapeHtml(note)}</div>
        </div>
        <div>
          <div><strong>AI 参与方式</strong></div>
          <div class="muted">知识检索: 纯本地</div>
          <div class="muted">知识问答: 本地召回 + AI / 本地兜底</div>
        </div>
      </div>
      <div class="toggle-row mt-1">
        <span class="muted">API Key ${apiReady ? "已配置" : "未配置"}</span>
        <span class="muted">启用步骤 ${escapeHtml(String(enabled))}/${escapeHtml(String(total))}</span>
        <span class="muted">Prompt 覆盖 ${escapeHtml(String(data.prompt_overrides || 0))}</span>
      </div>
    `;
  } catch (err) {
    el.innerHTML = `<div class="alert alert-error">${escapeHtml(err.message || "无法加载 AI 状态")}</div>`;
  }
}

function switchKnowledgeTab(name) {
  document.querySelectorAll("[data-knowledge-tab]").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.knowledgeTab === name);
  });
  document.getElementById("knowledge-tab-search")?.classList.toggle("active", name === "search");
  document.getElementById("knowledge-tab-search")?.classList.toggle("hidden", name !== "search");
  document.getElementById("knowledge-tab-graph")?.classList.toggle("active", name === "graph");
  document.getElementById("knowledge-tab-graph")?.classList.toggle("hidden", name !== "graph");
  document.getElementById("knowledge-tab-save")?.classList.toggle("active", name === "save");
  document.getElementById("knowledge-tab-save")?.classList.toggle("hidden", name !== "save");
}

function initKnowledgeGraphPanel() {
  document.getElementById("knowledge-concepts-refresh")?.addEventListener("click", loadKnowledgeConcepts);
  document.getElementById("knowledge-graph-refresh")?.addEventListener("click", loadKnowledgeGraph);
  document.getElementById("knowledge-gaps-refresh")?.addEventListener("click", loadKnowledgeGaps);
  if (document.getElementById("knowledge-tab-graph")) {
    loadKnowledgeConcepts();
    loadKnowledgeGraph();
  }
}

function renderKnowledgeFollowUps(questions) {
  const rows = (questions || []).filter(Boolean).slice(0, 6);
  if (!rows.length) return "";
  return `<div class="mt-1"><strong>可继续研究</strong><div class="toggle-row mt-1">${rows.map((q) =>
    `<button type="button" class="btn btn-sm btn-secondary" data-knowledge-suggestion="${escapeHtml(q)}">${escapeHtml(q)}</button>`
  ).join("")}</div></div>`;
}

function bindKnowledgeSuggestionButtons(root = document) {
  root.querySelectorAll("[data-knowledge-suggestion]").forEach((btn) => {
    if (btn.dataset.bound === "1") return;
    btn.dataset.bound = "1";
    btn.addEventListener("click", () => {
      const value = btn.dataset.knowledgeSuggestion || "";
      const input = document.getElementById("knowledge-query");
      const ask = document.getElementById("knowledge-ask-question");
      if (input) input.value = value;
      if (ask) ask.value = value;
      switchKnowledgeTab("search");
      searchKnowledge();
    });
  });
}

async function loadKnowledgeConcepts() {
  const host = document.getElementById("knowledge-concepts-list");
  if (!host) return;
  const q = document.getElementById("knowledge-concept-query")?.value.trim() || "";
  const params = new URLSearchParams();
  params.set("limit", "40");
  if (q) params.set("q", q);
  host.innerHTML = "<p class='muted'>正在加载概念…</p>";
  try {
    const data = await api("GET", `/api/knowledge/concepts?${params.toString()}`, null, {
      timeoutMs: 20000,
      retry: 1,
      prewarm: true,
    });
    const rows = data.concepts || [];
    host.innerHTML = rows.length
      ? `<div class="ui-inset-group">${rows.map((row) => `
        <button type="button" class="ui-list-row text-left" data-concept-name="${escapeHtml(row.name || "")}">
          <div class="ui-list-row-main">
            <div class="item-card-meta">
              <span class="source-badge source-web">${escapeHtml(row.kind || "concept")}</span>
              <span class="muted">${escapeHtml(String(row.item_count || 0))} 条</span>
            </div>
            <div class="ui-list-row-title">${escapeHtml(row.name || "")}</div>
          </div>
        </button>
      `).join("")}</div>`
      : "<p class='muted'>暂无概念节点</p>";
    host.querySelectorAll("[data-concept-name]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const name = btn.dataset.conceptName || "";
        const gapInput = document.getElementById("knowledge-gap-topic");
        if (gapInput) gapInput.value = name;
        await loadKnowledgeGaps();
      });
    });
  } catch (err) {
    host.innerHTML = `<div class="alert alert-error">${escapeHtml(err.message || "概念加载失败")}</div>`;
  }
}

async function loadKnowledgeGraph() {
  const host = document.getElementById("knowledge-graph-summary");
  if (!host) return;
  const params = new URLSearchParams();
  params.set("limit", "80");
  const itemId = document.getElementById("knowledge-graph-item")?.value.trim() || "";
  const relation = document.getElementById("knowledge-graph-relation")?.value.trim() || "";
  const minConfidence = document.getElementById("knowledge-graph-confidence")?.value || "0";
  if (itemId) params.set("item_id", itemId);
  if (relation) params.set("relation", relation);
  params.set("min_confidence", minConfidence);
  host.innerHTML = "<p class='muted'>正在加载图谱…</p>";
  try {
    const data = await api("GET", `/api/knowledge/graph?${params.toString()}`, null, {
      timeoutMs: 25000,
      retry: 1,
      prewarm: true,
    });
    const nodes = data.nodes || [];
    const edges = data.edges || [];
    host.innerHTML = `
      <div class="toggle-row">
        <span class="muted">节点 ${escapeHtml(String(nodes.length))}</span>
        <span class="muted">关系 ${escapeHtml(String(edges.length))}</span>
      </div>
      <div class="ui-inset-group mt-1">${edges.slice(0, 20).map((edge) => `
        <div class="ui-list-row">
          <div class="ui-list-row-main">
            <div class="item-card-meta">
              <span class="source-badge source-bilibili">${escapeHtml(edge.relation || "relation")}</span>
              <span class="muted">${escapeHtml(String(Math.round((Number(edge.confidence) || 0) * 100)))}%</span>
            </div>
            <div class="ui-list-row-title">${escapeHtml(edge.from_id || "")} → ${escapeHtml(edge.to_id || "")}</div>
            <p class="ui-list-row-sub muted">${escapeHtml(edge.evidence || "")}</p>
          </div>
        </div>
      `).join("") || "<p class='muted'>暂无关系</p>"}</div>
    `;
  } catch (err) {
    host.innerHTML = `<div class="alert alert-warning">${escapeHtml(err.message || "图谱加载失败")}<div class="mt-1 muted">检索仍可继续使用；可先查看知识诊断条，必要时从云端 vault 重建索引。</div></div>`;
  }
}

async function loadKnowledgeGaps() {
  const host = document.getElementById("knowledge-gaps-list");
  if (!host) return;
  const topic = document.getElementById("knowledge-gap-topic")?.value.trim() || "";
  const itemId = document.getElementById("knowledge-graph-item")?.value.trim() || "";
  host.innerHTML = "<p class='muted'>正在生成研究问题…</p>";
  try {
    const data = await api("POST", "/api/knowledge/research-questions", {
      topic: topic || null,
      query: topic || null,
      item_id: itemId || null,
      limit: 8,
    }, { timeoutMs: 25000, retry: 1, prewarm: true });
    const rows = data.questions || [];
    host.innerHTML = rows.length
      ? `<div class="ui-inset-group">${rows.map((row) => `
        <div class="ui-list-row">
          <div class="ui-list-row-main">
            <div class="ui-list-row-title">${escapeHtml(row.question || "")}</div>
            <p class="ui-list-row-sub muted">${escapeHtml(row.evidence || row.source || "")}</p>
          </div>
        </div>
      `).join("")}</div>`
      : "<p class='muted'>暂无可生成的研究问题</p>";
  } catch (err) {
    host.innerHTML = `<div class="alert alert-error">${escapeHtml(err.message || "研究问题生成失败")}</div>`;
  }
}

async function searchKnowledge() {
  const el = document.getElementById("knowledge-results");
  const state = currentKnowledgeSearchState();
  const q = state.q;
  if (!q) {
    el.innerHTML = "<p class='muted'>请输入关键词后再检索</p>";
    return;
  }
  if (q.length < 2) {
    el.innerHTML = "<p class='muted'>关键词至少 2 个字符</p>";
    return;
  }
  const params = new URLSearchParams();
  params.set("q", q);
  params.set("limit", "50");
  params.set("mode", state.mode);
  if (state.source) params.set("source", state.source);
  if (state.topic) params.set("topic", state.topic);
  if (state.entity) params.set("entity", state.entity);
  if (state.tag) params.set("tag", state.tag);
  if (state.conflict_status) params.set("conflict_status", state.conflict_status);
  if (state.explain) params.set("explain", "1");
  el.innerHTML = "<p class='muted'>检索中…</p>";
  try {
    const data = await api("GET", `/api/knowledge/search?${params.toString()}`, null, {
      timeoutMs: 30000,
      retry: 1,
      prewarm: true,
    });
    const hits = data.hits || [];
    knowledgeAskSession.history = [];
    el.innerHTML = hits.length
      ? `<div class="ui-inset-group knowledge-results-list">${hits.map((hit) => {
        const i = hit.item || {};
        const src = i.source || "web";
        const concepts = (hit.concepts || []).slice(0, 5);
        const conceptLine = concepts.length
          ? `<div class="toggle-row mt-1">${concepts.map((c) =>
              `<span class="source-badge source-web">${escapeHtml(c.name || "")}</span>`
            ).join("")}</div>`
          : "";
        const projectLine = hit.project ? `<span class="source-badge source-zhihu">项目 ${escapeHtml(hit.project)}</span>` : "";
        const reasonLine = (hit.match_reasons || []).length
          ? `<p class="ui-list-row-sub muted">命中原因：${escapeHtml((hit.match_reasons || []).join("；"))}</p>`
          : "";
        const snippets = (hit.snippets || []).map((s) => `<p class="ui-list-row-sub muted">${escapeHtml(s)}</p>`).join("");
        const score = state.explain ? `<span class="muted">score ${escapeHtml(String(hit.score || 0))}</span>` : "";
        return `<div class="ui-list-row knowledge-result-row">
          <div class="ui-list-row-main">
            <div class="item-card-meta">
              <span class="source-badge source-${escapeHtml(src)}">${escapeHtml(sourceLabel(src))}</span>
              ${i.personal?.vault_conflict ? `<span class="source-badge source-web">需合并</span>` : ""}
              ${hit.match_type === "graph" ? `<span class="source-badge source-bilibili">关联扩展</span>` : ""}
              ${hit.match_type === "behavior" ? `<span class="source-badge source-zhihu">行为证据</span>` : ""}
              ${hit.match_type === "concept" ? `<span class="source-badge source-web">概念召回</span>` : ""}
              ${projectLine}
              ${score}
            </div>
            <div class="ui-list-row-title">${escapeHtml(i.title || "无标题")}</div>
            ${snippets || `<p class="ui-list-row-sub muted">${escapeHtml(i.summary || i.content?.slice(0, 200) || "")}</p>`}
            ${reasonLine}
            ${conceptLine}
            <div class="knowledge-links-slot" id="knowledge-links-${escapeHtml(i.id || "")}"></div>
          </div>
          <div class="ui-list-row-actions">
            <a class="btn btn-sm btn-secondary" href="${safeHref(i.url)}" target="_blank" rel="noopener">原文</a>
            ${i.id ? `<button type="button" class="btn btn-sm btn-secondary" data-knowledge-links="${escapeHtml(i.id)}">关联</button>` : ""}
          </div>
        </div>`;
      }).join("")}</div>`
      : renderKnowledgeSearchSuggestions(data.suggestions || {});
    bindKnowledgeSuggestionButtons(el);
    el.querySelectorAll("[data-knowledge-links]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const itemId = btn.dataset.knowledgeLinks;
        const host = document.getElementById(`knowledge-links-${itemId}`);
        if (!itemId || !host) return;
        if (host.innerHTML.trim()) {
          host.innerHTML = "";
          return;
        }
        host.innerHTML = "<p class='muted mt-1'>正在加载关联条目…</p>";
        try {
          const linkData = await api("GET", `/api/knowledge/items/${encodeURIComponent(itemId)}/links?limit=6`);
          renderKnowledgeLinks(host, linkData.links || []);
        } catch (err) {
          host.innerHTML = `<div class="alert alert-error mt-1">${escapeHtml(err.message || "关联加载失败")}</div>`;
        }
      });
    });
  } catch (err) {
    el.innerHTML = `<div class="alert alert-error">${escapeHtml(err.message)}</div>`;
  }
}

function renderKnowledgeSearchSuggestions(suggestions) {
  const keywords = (suggestions.keywords || []).slice(0, 8);
  const concepts = (suggestions.concepts || []).slice(0, 8);
  const questions = (suggestions.follow_up_questions || []).slice(0, 6);
  const chips = [
    ...keywords.map((k) => `<button type="button" class="btn btn-sm btn-secondary" data-knowledge-suggestion="${escapeHtml(k)}">${escapeHtml(k)}</button>`),
    ...concepts.map((c) => `<button type="button" class="btn btn-sm btn-secondary" data-knowledge-suggestion="${escapeHtml(c.name || "")}">${escapeHtml(c.name || "")}</button>`),
  ].join("");
  return `
    <div class="card">
      <h3>未找到匹配条目</h3>
      <p class="muted">可以换成更短关键词、相关概念，或把这个问题转为新一轮搜罗。</p>
      ${chips ? `<div class="toggle-row mt-1">${chips}</div>` : ""}
      ${renderKnowledgeFollowUps(questions)}
    </div>
  `;
}

async function loadKnowledgeCloudStatus() {
  const el = document.getElementById("knowledge-cloud-status");
  if (!el) return;
  try {
    const data = await api("GET", "/api/cloud/status", null, { timeoutMs: 20000, retry: 1, prewarm: true });
    const health = data.health || {};
    const healthWarnings = (health.warnings || []).map((msg) =>
      `<div class="alert alert-warning mt-1">${escapeHtml(msg)}</div>`
    ).join("");
    const healthIssues = (health.issues || []).map((msg) =>
      `<div class="alert alert-error mt-1">${escapeHtml(msg)}</div>`
    ).join("");
    if (!data.ready) {
      const recommended = data.recommended_vault_path
        ? `<div class="muted">推荐路径: ${escapeHtml(data.recommended_vault_path)}</div>`
        : "";
      const targets = data.one_drive_targets || [];
      const candidates = targets.length
        ? `<div class="muted">检测到 OneDrive: ${targets.map((entry) => escapeHtml(entry.root || "")).join(" · ")}</div>`
        : "";
      const rootPicker = targets.length
        ? `
          <div>
            <label for="knowledge-cloud-root">同步位置</label>
            <select id="knowledge-cloud-root">
              ${targets.map((entry) => `<option value="${escapeHtml(entry.root || "")}">${escapeHtml(entry.root || "")}</option>`).join("")}
            </select>
          </div>
          <div>
            <label for="knowledge-cloud-name">Vault 名称</label>
            <input id="knowledge-cloud-name" type="text" value="OSINT-Knowledge" />
          </div>
        `
        : `
          <div>
            <label for="knowledge-cloud-path">Vault 目录</label>
            <input id="knowledge-cloud-path" type="text" value="${escapeHtml(data.recommended_vault_path || "")}" placeholder="例如 D:/Knowledge/OSINT-Knowledge" />
          </div>
        `;
      el.innerHTML = `
        <div class="alert alert-warning">尚未配置 Markdown vault，同步与跨设备恢复未启用。</div>
        ${recommended}
        ${candidates}
        ${healthIssues}
        ${healthWarnings}
        <div class="grid-2 mt-1">
          ${rootPicker}
          <div>
            <label for="knowledge-cloud-mode">同步方式</label>
            <select id="knowledge-cloud-mode">
              <option value="manual">手动导出</option>
              <option value="passive">即时写入</option>
              <option value="scheduled">定时队列</option>
            </select>
          </div>
        </div>
        <label class="checkbox-row mt-1">
          <input id="knowledge-cloud-sync-after" type="checkbox" />
          <span>初始化后立即导出当前知识</span>
        </label>
        <div class="toggle-row mt-1">
          <button type="button" class="btn btn-secondary btn-sm" id="knowledge-cloud-init">初始化 vault</button>
        </div>
      `;
      document.getElementById("knowledge-cloud-init")?.addEventListener("click", async () => {
        try {
          const payload = {
            provider: targets.length ? "onedrive_folder" : "local_folder",
            sync_mode: document.getElementById("knowledge-cloud-mode")?.value || "manual",
            sync_after: !!document.getElementById("knowledge-cloud-sync-after")?.checked,
          };
          if (targets.length) {
            payload.onedrive_root = document.getElementById("knowledge-cloud-root")?.value || "";
            payload.vault_name = document.getElementById("knowledge-cloud-name")?.value || "OSINT-Knowledge";
          } else {
            payload.vault_path = document.getElementById("knowledge-cloud-path")?.value || data.recommended_vault_path || "";
          }
          await api("POST", "/api/cloud/init", payload, { timeoutMs: 45000, retry: 1, prewarm: true });
          showToast("Vault 已初始化", "success");
          await loadKnowledgeCloudStatus();
        } catch (err) {
          showToast(err.message || "Vault 初始化失败", "error");
        }
      });
      return;
    }
    const conflict = Number(data.conflict_count || 0);
    const pending = Number((data.statuses || {}).pending || 0);
    const warning = conflict > 0
      ? `<div class="alert alert-warning mt-1">当前有 ${conflict} 个条目需合并，请先处理冲突副本。</div>`
      : "";
    const onedriveLine = data.is_onedrive_vault
      ? `<div class="muted">OneDrive · ${escapeHtml(data.matched_onedrive_root || "")}</div>`
      : `<div class="muted">未检测到 OneDrive 目录映射</div>`;
    el.innerHTML = `
      <div class="grid-2">
        <div>
          <div><strong>Vault</strong></div>
          <div class="muted">${escapeHtml(data.vault_path || "")}</div>
          ${onedriveLine}
        </div>
        <div>
          <div><strong>同步状态</strong></div>
          <div class="muted">${escapeHtml(data.provider || "")} · ${escapeHtml(data.sync_mode || "")} · 最近同步 ${escapeHtml(data.last_synced_at || "未同步")}</div>
        </div>
      </div>
      <div class="toggle-row mt-1">
        <span class="muted">条目 ${escapeHtml(String(data.item_count || 0))}</span>
        <span class="muted">待同步 ${escapeHtml(String(pending))}</span>
        <span class="muted">冲突 ${escapeHtml(String(conflict))}</span>
        <button type="button" class="btn btn-secondary btn-sm" id="knowledge-cloud-sync">同步 vault</button>
        <button type="button" class="btn btn-secondary btn-sm" id="knowledge-cloud-reindex">重建索引</button>
      </div>
      ${warning}
      ${healthIssues}
      ${healthWarnings}
      <div id="knowledge-cloud-conflicts" class="mt-1"></div>
    `;
    document.getElementById("knowledge-cloud-sync")?.addEventListener("click", async () => {
      try {
        await api("POST", "/api/cloud/sync", {}, { timeoutMs: 60000, retry: 1, prewarm: true });
        showToast("Vault 同步完成", "success");
        await loadKnowledgeCloudStatus();
      } catch (err) {
        showToast(err.message || "Vault 同步失败", "error");
      }
    });
    document.getElementById("knowledge-cloud-reindex")?.addEventListener("click", async () => {
      try {
        await api("POST", "/api/cloud/reindex", {}, { timeoutMs: 60000, retry: 1, prewarm: true });
        showToast("已从 Vault 重建索引", "success");
        await loadKnowledgeCloudStatus();
      } catch (err) {
        showToast(err.message || "重建索引失败", "error");
      }
    });
    if (conflict > 0) {
      const conflictHost = document.getElementById("knowledge-cloud-conflicts");
      const conflictData = await api("GET", "/api/cloud/conflicts?limit=5", null, {
        timeoutMs: 20000,
        retry: 1,
        prewarm: true,
      });
      const rows = conflictData.conflicts || [];
      conflictHost.innerHTML = rows.length
        ? `<div class="ui-inset-group">${rows.map((entry) => `
          <div class="ui-list-row">
            <div class="ui-list-row-main">
              <div class="ui-list-row-title">${escapeHtml(entry.item_id || "未知条目")}</div>
              <p class="ui-list-row-sub muted">${escapeHtml(entry.conflict_path || entry.note_path || "")}</p>
            </div>
          </div>
        `).join("")}</div>`
        : "";
    }
  } catch (err) {
    el.innerHTML = `<div class="alert alert-error">${escapeHtml(err.message || "无法加载 cloud 状态")}</div>`;
  }
}

/* 简报 */
function initDigest() {
  document.getElementById("btn-daily")?.addEventListener("click", async () => {
    const el = document.getElementById("daily-content");
    const useAi = document.getElementById("opt-digest-ai")?.checked;
    const useHot = document.getElementById("opt-digest-hotlist")?.checked !== false;
    el.innerHTML = "<p class='muted'>生成中…</p>";
    try {
      const params = new URLSearchParams();
      if (useAi) params.set("ai", "1");
      if (!useHot) params.set("hot_list", "0");
      const qs = params.toString();
      const url = qs ? `/api/digest/daily?${qs}` : "/api/digest/daily";
      const data = await api("GET", url);
      renderMarkdown(el, data.content);
      ensureReadingSurface(el);
    } catch (err) {
      el.innerHTML = `<div class="alert alert-error">${escapeHtml(err.message)}</div>`;
    }
  });
  loadDigestHistory();
  loadReportList();
}

async function loadDigestHistory() {
  const el = document.getElementById("digest-history");
  if (!el) return;
  try {
    const data = await api("GET", "/api/digest/history");
    const items = data.digests || [];
    el.innerHTML = items.length
      ? `<div class="ui-inset-group digest-archive-list">${items.map((d) =>
        `<button type="button" class="ui-list-row digest-archive-item" data-digest-date="${escapeHtml(d.date)}">
          <span class="ui-list-row-title">${escapeHtml(d.date)}</span>
          <span class="ui-list-row-sub muted">${escapeHtml(d.preview || "")}</span>
        </button>`
      ).join("")}</div>`
      : "<p class='muted'>暂无存档。生成今日简报后会保存在 ~/.osint/digests/</p>";
    el.querySelectorAll("[data-digest-date]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const date = btn.dataset.digestDate;
        const daily = document.getElementById("daily-content");
        if (!daily || !date) return;
        daily.innerHTML = "<p class='muted'>加载存档…</p>";
        daily.scrollIntoView({ behavior: "smooth", block: "start" });
        try {
          const data = await api("GET", `/api/digest/history/${encodeURIComponent(date)}`);
          renderMarkdown(daily, data.content || data.preview || "");
          ensureReadingSurface(daily);
        } catch (err) {
          daily.innerHTML = `<div class="alert alert-error">${escapeHtml(err.message)}</div>`;
        }
      });
    });
  } catch (_) {
    el.textContent = "无法加载简报存档";
  }
}

async function loadReportList() {
  const el = document.getElementById("report-list");
  if (!el) return;
  try {
    const data = await api("GET", "/api/digest/reports");
    const reports = data.reports || [];
    if (!reports.length) {
      el.innerHTML = "<p class='muted'>暂无历史报告。在搜罗页勾选「本轮情报报告」后会出现。</p>";
      return;
    }
    el.innerHTML = `<table class="table"><thead><tr><th>Run ID</th><th>话题</th><th>操作</th></tr></thead><tbody>${
      reports.map((r) =>
        `<tr><td>${escapeHtml(r.run_id)}</td><td>${escapeHtml(r.query || "")}</td>
        <td><a href="/runs/${r.run_id}#report">查看报告</a> · <a href="/?run=${encodeURIComponent(r.run_id)}">在搜罗页打开</a></td></tr>`
      ).join("")
    }</tbody></table>`;
  } catch (err) {
    el.innerHTML = `<div class="alert alert-error">${escapeHtml(err.message)}</div>`;
  }
}

/* 行为时间线 */
function initBehavior() {
  document.getElementById("btn-behavior-refresh")?.addEventListener("click", loadBehavior);
  document.getElementById("btn-behavior-insights")?.addEventListener("click", () => loadBehaviorInsights(true));
  document.getElementById("behavior-filter")?.addEventListener("change", loadBehavior);
  document.getElementById("behavior-min-score")?.addEventListener("change", loadBehavior);
  loadPersonaStaleBanner();
  loadBehavior();
}

async function loadBehaviorInsights(refresh) {
  const el = document.getElementById("behavior-insights");
  if (!el) return;
  el.textContent = "解读生成中…";
  try {
    const url = refresh ? "/api/events/insights?refresh=1" : "/api/events/insights";
    const data = await api("GET", url);
    el.innerHTML = `<div class="card card-flat"><h3>AI 行为解读</h3><div class="markdown-body persona-brief-panel"></div>${data.cached ? "<p class='muted'>（缓存）</p>" : ""}</div>`;
    renderMarkdown(el.querySelector(".markdown-body"), data.insights || "");
  } catch (err) {
    el.innerHTML = `<div class="alert alert-error">${escapeHtml(err.message)}</div>`;
  }
}

async function loadBehavior() {
  const el = document.getElementById("behavior-list");
  if (!el) return;
  const filter = document.getElementById("behavior-filter")?.value || "";
  const minScore = parseInt(document.getElementById("behavior-min-score")?.value, 10) || 0;
  let url = `/api/events/recent?limit=60&min_score=${minScore}`;
  if (filter === "extension") url += "&via=extension";
  else if (filter) url += `&event_type=${encodeURIComponent(filter)}`;
  el.textContent = "加载中…";
  try {
    const data = await api("GET", url);
    if (!data.items?.length) {
      el.innerHTML = "<p class='muted'>暂无行为记录。<a href='/ingest#extension'>安装扩展</a>并正常浏览后会出现。</p>";
      return;
    }
    el.innerHTML = `<div class="ui-inset-group behavior-list-group">${data.items.map((row) => {
      const dwell = row.duration_ms ? ` · ${Math.round(row.duration_ms / 1000)}s` : "";
      const title = row.url
        ? `<a href="${safeHref(row.url)}" target="_blank" rel="noopener">${escapeHtml((row.title || row.url).slice(0, 80))}</a>${dwell}`
        : escapeHtml((row.title || "—").slice(0, 80));
      return `<div class="ui-list-row behavior-list-row">
        <div class="ui-list-row-main">
          <div class="ui-list-row-meta muted">${escapeHtml(String(row.created_at || "").slice(0, 16))}</div>
          <div class="ui-list-row-title">${title}</div>
          <div class="ui-list-row-sub muted">${escapeHtml(formatEventType(row.event_type))} · ${escapeHtml(row.source || "")}</div>
        </div>
        <div class="ui-list-row-side muted">${row.score}</div>
      </div>`;
    }).join("")}</div>`;
  } catch (err) {
    el.innerHTML = `<div class="alert alert-error">${escapeHtml(err.message)}</div>`;
  }
}

function formatPersonaDateTime(iso) {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return String(iso).slice(0, 19).replace("T", " ");
    return d.toLocaleString("zh-CN", { hour12: false, month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" });
  } catch (_) {
    return String(iso).slice(0, 19).replace("T", " ");
  }
}

function formatDateKey(iso) {
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "";
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
  } catch (_) {
    return "";
  }
}

function renderPersonaBuildHeatmap(history) {
  const entries = Array.isArray(history) ? history : [];
  if (!entries.length) return "";
  const dayCounts = new Map();
  let maxCount = 0;
  for (const item of entries) {
    const key = formatDateKey(item.built_at);
    if (!key) continue;
    const next = (dayCounts.get(key) || 0) + 1;
    dayCounts.set(key, next);
    if (next > maxCount) maxCount = next;
  }
  if (!dayCounts.size) return "";

  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const weeks = 14;
  const start = new Date(today);
  start.setDate(start.getDate() - weeks * 7 + (6 - start.getDay()));

  const cells = [];
  for (let w = 0; w < weeks; w += 1) {
    for (let dow = 0; dow < 7; dow += 1) {
      const cellDate = new Date(start);
      cellDate.setDate(start.getDate() + w * 7 + dow);
      if (cellDate > today) continue;
      const key = formatDateKey(cellDate.toISOString());
      const count = dayCounts.get(key) || 0;
      let level = 0;
      if (count > 0 && maxCount > 0) {
        const ratio = count / maxCount;
        if (ratio >= 0.75) level = 4;
        else if (ratio >= 0.5) level = 3;
        else if (ratio >= 0.25) level = 2;
        else level = 1;
      }
      const title = count ? `${key} · ${count} 次构建` : key;
      cells.push(`<span class="persona-heat-cell l${level}" title="${escapeHtml(title)}"></span>`);
    }
  }

  return `<div class="persona-heatmap-wrap">
    <div class="persona-heatmap-label muted">近 ${weeks} 周构建活跃度</div>
    <div class="persona-heatmap" role="img" aria-label="画像构建热力图">${cells.join("")}</div>
    <div class="persona-heatmap-legend muted">
      <span>少</span>
      <span class="persona-heat-cell l0"></span>
      <span class="persona-heat-cell l1"></span>
      <span class="persona-heat-cell l2"></span>
      <span class="persona-heat-cell l3"></span>
      <span class="persona-heat-cell l4"></span>
      <span>多</span>
    </div>
  </div>`;
}

function renderPersonaVersionHistory(history, currentVersion) {
  const entries = Array.isArray(history) ? [...history] : [];
  if (!entries.length) {
    return `<div class="card persona-version-card"><h2>版本历史</h2><p class="muted">暂无历史版本</p></div>`;
  }
  entries.sort((a, b) => Number(b.version) - Number(a.version));
  const heatmap = renderPersonaBuildHeatmap(entries);
  const recent = entries.slice(0, 8);
  const older = entries.slice(8);
  const row = (item) => {
    const ver = Number(item.version);
    const isCurrent = item.is_current || ver === Number(currentVersion);
    const meta = [
      formatPersonaDateTime(item.built_at),
      item.events_at_last_build != null ? `${item.events_at_last_build} 条行为` : "",
      item.brief_ai_generated ? "AI 摘要" : "规则摘要",
    ]
      .filter(Boolean)
      .join(" · ");
    const action = isCurrent
      ? `<span class="persona-version-badge current">当前</span>`
      : `<button type="button" class="btn btn-sm btn-ghost btn-persona-rollback" data-version="${ver}">恢复</button>`;
    return `<li class="persona-version-item${isCurrent ? " is-current" : ""}">
      <div class="persona-version-main">
        <strong>v${escapeHtml(String(ver))}</strong>
        <span class="muted persona-version-meta">${escapeHtml(meta)}</span>
      </div>
      ${action}
    </li>`;
  };
  const olderBlock =
    older.length > 0
      ? `<details class="persona-version-older"><summary class="muted">更早版本（${older.length} 个）</summary><ul class="persona-version-list">${older.map(row).join("")}</ul></details>`
      : "";
  return `<div class="card persona-version-card">
    <h2>版本历史</h2>
    <p class="muted section-hint">每次「构建画像」会存档一版，仅保留最近 10 个版本；颜色越深表示当天构建越频繁。</p>
    ${heatmap}
    <ul class="persona-version-list">${recent.map(row).join("")}</ul>
    ${olderBlock}
  </div>`;
}

function toStructuredPersonaRows(value) {
  if (!Array.isArray(value)) return [];
  return value
    .map((entry) => {
      if (entry == null) return null;
      if (typeof entry === "string") return { label: entry, meta: "" };
      if (typeof entry !== "object") return { label: String(entry), meta: "" };
      const label = entry.name || entry.title || entry.label || entry.value || entry.entity || entry.source || entry.domain || entry.goal;
      if (!label) return null;
      const metaBits = [
        entry.status,
        entry.reason,
        entry.note,
        entry.weight != null ? `权重 ${entry.weight}` : "",
        entry.count != null ? `频次 ${entry.count}` : "",
      ].filter(Boolean);
      return { label: String(label), meta: metaBits.join(" · ") };
    })
    .filter(Boolean);
}

function renderStructuredPersonaField(label, rows) {
  const normalized = toStructuredPersonaRows(rows);
  if (!normalized.length) return "";
  return `<div class="persona-field"><strong>${escapeHtml(label)}</strong><div class="chip-group">${normalized
    .slice(0, 16)
    .map((row) => `<span class="chip"${row.meta ? ` title="${escapeHtml(row.meta)}"` : ""}>${escapeHtml(row.label)}</span>`)
    .join("")}</div></div>`;
}

function renderPersonaProjectsCard(model) {
  const rows = Array.isArray(model?.active_projects) ? model.active_projects : [];
  if (!rows.length) return "";
  return `<div class="card persona-projects-card">
    <h2>当前项目</h2>
    <p class="muted section-hint">这些项目来自 Persona 结构化模型，可以直接拿来检索知识库或生成研究树。</p>
    <div class="ui-inset-group">${rows.slice(0, 8).map((row) => {
      const name = String(row?.name || "").trim();
      if (!name) return "";
      const status = String(row?.status || "");
      const signals = Array.isArray(row?.signals) ? row.signals.slice(0, 3) : [];
      const knowledgeHref = personaKnowledgeSearchUrl({ q: name, tab: "search" });
      const graphHref = personaKnowledgeSearchUrl({ q: name, tab: "graph" });
      return `<div class="ui-list-row persona-project-row">
        <div class="ui-list-row-main">
          <div class="item-card-meta">
            <span class="source-badge source-zhihu">项目</span>
            ${status ? `<span class="muted">${escapeHtml(status)}</span>` : ""}
          </div>
          <div class="ui-list-row-title">${escapeHtml(name)}</div>
          <p class="ui-list-row-sub muted">${escapeHtml(signals.join("；"))}</p>
        </div>
        <div class="ui-list-row-actions">
          <a class="btn btn-sm btn-secondary" href="${knowledgeHref}">查知识库</a>
          <a class="btn btn-sm btn-ghost" href="${graphHref}">看图谱</a>
          <button type="button" class="btn btn-sm btn-ghost" data-persona-project-research="${escapeHtml(name)}">建研究</button>
        </div>
      </div>`;
    }).join("")}</div>
    <div id="persona-project-research-result" class="mt-1 hidden"></div>
  </div>`;
}

function renderKeyValueChips(map, formatter = null, limit = 12) {
  if (!map || typeof map !== "object") return "";
  const rows = Object.entries(map)
    .filter(([, value]) => Number(value) > 0)
    .sort((a, b) => Number(b[1]) - Number(a[1]))
    .slice(0, limit);
  if (!rows.length) return "";
  return `<div class="chip-group">${rows
    .map(([key, value]) => {
      const label = formatter ? formatter(key, value) : `${key} ${value}`;
      return `<span class="chip">${escapeHtml(label)}</span>`;
    })
    .join("")}</div>`;
}

function personaKnowledgeSearchUrl({ q = "", source = "", tab = "search" } = {}) {
  const params = new URLSearchParams();
  if (q) params.set("q", q);
  if (source) params.set("source", source);
  if (tab) params.set("tab", tab);
  const query = params.toString();
  return query ? `/knowledge?${query}` : "/knowledge";
}

function renderPersonaWorkbench(consoleData) {
  const groups = Array.isArray(consoleData.behavior_workbench) ? consoleData.behavior_workbench : [];
  if (!groups.length) {
    return "<p class='muted'>暂无可展示的行为工作台样本。</p>";
  }
  const categoryOptions = groups.map((group) =>
    `<option value="${escapeHtml(group.category || "")}">${escapeHtml(group.label || formatBehaviorCategory(group.category))}</option>`
  ).join("");
  return `
    <div class="persona-workbench-toolbar">
      <div class="form-row">
        <label for="persona-workbench-filter">行为分类</label>
        <select id="persona-workbench-filter">
          <option value="">全部</option>
          ${categoryOptions}
        </select>
      </div>
      <div class="form-row">
        <label for="persona-workbench-keyword">关键词</label>
        <input type="search" id="persona-workbench-keyword" placeholder="筛选标题或来源">
      </div>
    </div>
    <div class="persona-workbench-grid">${groups.map((group) => {
    const rows = Array.isArray(group.items) ? group.items : [];
    return `<section class="persona-workbench-group" data-persona-category="${escapeHtml(group.category || "")}" data-persona-label="${escapeHtml((group.label || "").toLowerCase())}">
      <div class="persona-workbench-head">
        <h4>${escapeHtml(group.label || formatBehaviorCategory(group.category))}</h4>
        <span class="muted">${escapeHtml(String(rows.length))} 条样本</span>
      </div>
      <div class="ui-inset-group persona-evidence-list">${rows.map((row) => {
        const titleText = (row.title || row.url || "（无标题）").slice(0, 120);
        const title = row.url
          ? `<a href="${safeHref(row.url)}" target="_blank" rel="noopener">${escapeHtml(titleText)}</a>`
          : escapeHtml(titleText);
        const meta = [
          row.source ? sourceLabel(row.source) : "",
          row.event_type ? formatEventType(row.event_type) : "",
          row.score != null ? `权重 ${row.score}` : "",
          row.duration_ms && Number(row.duration_ms) > 0 ? `停留 ${Math.round(Number(row.duration_ms) / 1000)}s` : "",
        ]
          .filter(Boolean)
          .join(" · ");
        const knowledgeHref = personaKnowledgeSearchUrl({ q: row.title || row.url || "", source: row.source || "" });
        const graphHref = personaKnowledgeSearchUrl({ q: row.title || row.url || "", tab: "graph" });
        const researchSeed = row.title || row.url || "";
        return `<div class="ui-list-row persona-evidence-row" data-persona-item="${escapeHtml((titleText + " " + (row.source || "") + " " + (row.event_type || "")).toLowerCase())}">
          <div class="ui-list-row-main">
            <div class="ui-list-row-title">${title}</div>
            <div class="ui-list-row-sub muted">${escapeHtml(meta)}</div>
          </div>
          <div class="ui-list-row-actions">
            <a class="btn btn-sm btn-secondary" href="${knowledgeHref}">查知识库</a>
            <a class="btn btn-sm btn-ghost" href="${graphHref}">看图谱</a>
            <button type="button" class="btn btn-sm btn-ghost" data-persona-research="${escapeHtml(researchSeed)}">研究问题</button>
          </div>
        </div>`;
      }).join("")}</div>
      <div class="persona-research-panel hidden" data-persona-research-panel>
        <div class="muted">正在等待选择样本…</div>
      </div>
    </section>`;
  }).join("")}</div>`;
}

function bindPersonaWorkbench(root = document) {
  const filterEl = root.querySelector("#persona-workbench-filter");
  const keywordEl = root.querySelector("#persona-workbench-keyword");
  const groups = [...root.querySelectorAll(".persona-workbench-group")];
  const applyFilter = () => {
    const category = (filterEl?.value || "").trim();
    const keyword = (keywordEl?.value || "").trim().toLowerCase();
    groups.forEach((group) => {
      const groupCategory = group.dataset.personaCategory || "";
      const itemRows = [...group.querySelectorAll("[data-persona-item]")];
      let visibleRows = 0;
      itemRows.forEach((row) => {
        const haystack = row.dataset.personaItem || "";
        const matchCategory = !category || category === groupCategory;
        const matchKeyword = !keyword || haystack.includes(keyword);
        const visible = matchCategory && matchKeyword;
        row.classList.toggle("hidden", !visible);
        if (visible) visibleRows += 1;
      });
      group.classList.toggle("hidden", visibleRows === 0 || (category && category !== groupCategory && !keyword));
    });
  };
  filterEl?.addEventListener("change", applyFilter);
  keywordEl?.addEventListener("input", applyFilter);
  applyFilter();

  root.querySelectorAll("[data-persona-research]").forEach((btn) => {
    if (btn.dataset.bound === "1") return;
    btn.dataset.bound = "1";
    btn.addEventListener("click", async () => {
      const query = btn.dataset.personaResearch || "";
      const group = btn.closest(".persona-workbench-group");
      const panel = group?.querySelector("[data-persona-research-panel]");
      if (!panel || !query) return;
      panel.classList.remove("hidden");
      panel.innerHTML = "<div class='muted'>正在生成研究问题…</div>";
      try {
        const data = await api("POST", "/api/knowledge/research-questions", {
          query,
          topic: query,
          limit: 5,
        }, { timeoutMs: 25000, retry: 1, prewarm: true });
        const rows = data.questions || [];
        panel.innerHTML = rows.length
          ? `<div class="ui-inset-group mt-1">${rows.map((row) => `
            <div class="ui-list-row">
              <div class="ui-list-row-main">
                <div class="ui-list-row-title">${escapeHtml(row.question || "")}</div>
                <p class="ui-list-row-sub muted">${escapeHtml(row.evidence || row.source || "")}</p>
              </div>
              <div class="ui-list-row-actions">
                <a class="btn btn-sm btn-secondary" href="${personaKnowledgeSearchUrl({ q: row.question || query })}">去检索</a>
              </div>
            </div>
          `).join("")}</div>`
          : "<p class='muted'>暂时没有生成出可用的研究问题。</p>";
      } catch (err) {
        panel.innerHTML = `<div class="alert alert-error">${escapeHtml(err.message || "研究问题生成失败")}</div>`;
      }
    });
  });

  root.querySelectorAll("[data-persona-project-research]").forEach((btn) => {
    if (btn.dataset.bound === "1") return;
    btn.dataset.bound = "1";
    btn.addEventListener("click", async () => {
      const name = btn.dataset.personaProjectResearch || "";
      const host = document.getElementById("persona-project-research-result");
      if (!host || !name) return;
      host.classList.remove("hidden");
      host.innerHTML = "<div class='muted'>正在创建研究项目…</div>";
      try {
        const created = await api("POST", "/api/research/trees", { title: name, query: name });
        const treeId = created.tree?.id;
        if (!treeId) throw new Error("研究树创建失败");
        const questions = await api("POST", "/api/knowledge/research-questions", {
          topic: name,
          query: name,
          limit: 5,
        }, { timeoutMs: 25000, retry: 1, prewarm: true });
        host.innerHTML = `<div class="alert alert-success">已创建研究树「${escapeHtml(name)}」</div>
          <div class="ui-inset-group mt-1">${(questions.questions || []).map((row) => `
            <div class="ui-list-row">
              <div class="ui-list-row-main">
                <div class="ui-list-row-title">${escapeHtml(row.question || "")}</div>
                <div class="ui-list-row-sub muted">${escapeHtml(row.evidence || row.source || "")}</div>
              </div>
              <div class="ui-list-row-actions">
                <a class="btn btn-sm btn-secondary" href="/?tree=${encodeURIComponent(treeId)}">去研究树</a>
              </div>
            </div>
          `).join("") || "<p class='muted'>可继续在研究树中补充问题。</p>"}</div>`;
      } catch (err) {
        host.innerHTML = `<div class="alert alert-error">${escapeHtml(err.message || "研究树创建失败")}</div>`;
      }
    });
  });
}

function renderPersonaEvidenceConsole(consoleData) {
  if (!consoleData || typeof consoleData !== "object") return "";
  const eventBreakdown = consoleData.event_breakdown || {};
  const categoryBreakdown = consoleData.behavior_category_summary || {};
  const inventoryHtml = renderKeyValueChips(
    eventBreakdown.inventory_snapshots || {},
    (key, value) => `${formatEventType(key)} ${value}`,
    14,
  );
  const recentHtml = renderKeyValueChips(
    eventBreakdown.recent_activity_7d || {},
    (key, value) => `${formatEventType(key)} ${value}`,
    14,
  );
  const sourceHtml = renderKeyValueChips(
    consoleData.recent_sources || {},
    (key, value) => `${SOURCE_LABELS[key] || key} ${value}`,
    12,
  );
  const typeHtml = renderKeyValueChips(
    consoleData.recent_event_types || {},
    (key, value) => `${formatEventType(key)} ${value}`,
    16,
  );
  const categoryHtml = renderKeyValueChips(
    categoryBreakdown.recent_activity_7d || {},
    (key, value) => `${formatBehaviorCategory(key)} ${value}`,
    12,
  );
  const hints = Array.isArray(consoleData.high_interest_hints) ? consoleData.high_interest_hints : [];
  const evidenceMap = consoleData.evidence && typeof consoleData.evidence === "object" ? consoleData.evidence : {};
  const rankedSamples = Array.isArray(consoleData.ranked_behavior_samples) ? consoleData.ranked_behavior_samples : [];
  const dedupNote = consoleData.dedup_note && typeof consoleData.dedup_note === "object" ? consoleData.dedup_note : {};
  const hintHtml = hints.length
    ? `<div class="ui-inset-group persona-evidence-list">${hints
        .slice(0, 12)
        .map((hint) => {
          const title = hint.url
            ? `<a href="${safeHref(hint.url)}" target="_blank" rel="noopener">${escapeHtml((hint.title || hint.url).slice(0, 120))}</a>`
            : escapeHtml((hint.title || "（无标题）").slice(0, 120));
          const meta = [
            hint.source ? (SOURCE_LABELS[hint.source] || hint.source) : "",
            hint.event_type ? formatEventType(hint.event_type) : "",
            hint.dwell_sec && Number(hint.dwell_sec) > 0 ? `停留 ${hint.dwell_sec}s` : "",
          ]
            .filter(Boolean)
            .join(" · ");
          return `<div class="ui-list-row persona-evidence-row">
            <div class="ui-list-row-main">
              <div class="ui-list-row-title">${title}</div>
              <div class="ui-list-row-sub muted">${escapeHtml(meta)}</div>
            </div>
          </div>`;
        })
        .join("")}</div>`
    : "<p class='muted'>暂无高价值样本。</p>";
  const rankedHtml = rankedSamples.length
    ? `<div class="ui-inset-group persona-evidence-list">${rankedSamples
        .slice(0, 10)
        .map((row) => {
          const titleText = (row.title || row.url || "（无标题）").slice(0, 140);
          const title = row.url
            ? `<a href="${safeHref(row.url)}" target="_blank" rel="noopener">${escapeHtml(titleText)}</a>`
            : escapeHtml(titleText);
          const meta = [
            row.source ? (SOURCE_LABELS[row.source] || row.source) : "",
            row.event_type ? formatEventType(row.event_type) : "",
            row.score != null ? `权重 ${row.score}` : "",
            row.duration_ms && Number(row.duration_ms) > 0 ? `停留 ${Math.round(Number(row.duration_ms) / 1000)}s` : "",
            row.created_at ? formatPersonaDateTime(row.created_at) : "",
          ]
            .filter(Boolean)
            .join(" · ");
          return `<div class="ui-list-row persona-evidence-row">
            <div class="ui-list-row-main">
              <div class="ui-list-row-title">${title}</div>
              <div class="ui-list-row-sub muted">${escapeHtml(meta)}</div>
            </div>
          </div>`;
        })
        .join("")}</div>`
    : "<p class='muted'>暂无可展示的代表性行为样本。</p>";
  const evidenceBlocks = [];
  if (evidenceMap.event_types && typeof evidenceMap.event_types === "object") {
    evidenceBlocks.push(`
      <div>
        <h4>AI/规则使用的行为证据</h4>
        ${renderKeyValueChips(evidenceMap.event_types, (key, value) => `${formatEventType(key)} ${value}`, 16) || "<p class='muted'>暂无。</p>"}
      </div>
    `);
  }
  if (evidenceMap.recent_sources && typeof evidenceMap.recent_sources === "object") {
    evidenceBlocks.push(`
      <div>
        <h4>画像使用的信源证据</h4>
        ${renderKeyValueChips(evidenceMap.recent_sources, (key, value) => `${SOURCE_LABELS[key] || key} ${value}`, 12) || "<p class='muted'>暂无。</p>"}
      </div>
    `);
  }
  if (evidenceMap.useful_feedback_patterns && typeof evidenceMap.useful_feedback_patterns === "object") {
    evidenceBlocks.push(`
      <div>
        <h4>正向反馈模式</h4>
        ${renderKeyValueChips(evidenceMap.useful_feedback_patterns, (key, value) => `${key} ${value}`, 10) || "<p class='muted'>暂无。</p>"}
      </div>
    `);
  }
  const sampleSize = consoleData.sample_size || {};
  const sampleMeta = [
    sampleSize.events != null ? `采样事件 ${sampleSize.events}` : "",
    sampleSize.feedback != null ? `反馈 ${sampleSize.feedback}` : "",
    consoleData.version_retention ? `版本保留 ${consoleData.version_retention} 个` : "",
  ]
    .filter(Boolean)
    .join(" · ");

  return `<div class="card persona-console-card">
    <h2>画像证据台</h2>
    <p class="muted section-hint">这里展示画像构建时实际参考的行为数据与分类结果，帮助你判断是否有重复、偏差或遗漏。</p>
    ${sampleMeta ? `<p class="muted persona-console-meta">${escapeHtml(sampleMeta)}</p>` : ""}
    <div class="persona-console-grid">
      <section class="persona-console-section">
        <h3>近期信源分布</h3>
        ${sourceHtml || "<p class='muted'>暂无。</p>"}
      </section>
      <section class="persona-console-section">
        <h3>近期行为类型</h3>
        ${typeHtml || "<p class='muted'>暂无。</p>"}
      </section>
      <section class="persona-console-section">
        <h3>近 7 日高价值行为</h3>
        ${recentHtml || "<p class='muted'>暂无。</p>"}
      </section>
      <section class="persona-console-section">
        <h3>行为分类总览</h3>
        <p class="muted persona-console-note">把浏览、停留、点赞、收藏、发布等行为分开看，便于判断画像是否失真。</p>
        ${categoryHtml || "<p class='muted'>暂无。</p>"}
      </section>
      <section class="persona-console-section">
        <h3>账号清单快照</h3>
        <p class="muted persona-console-note">这部分更多反映长期收藏/关注库存，不等于近期高频行为。</p>
        ${inventoryHtml || "<p class='muted'>暂无。</p>"}
      </section>
    </div>
    <section class="persona-console-section mt-1">
      <h3>高兴趣行为样本</h3>
      ${hintHtml}
    </section>
    <section class="persona-console-section mt-1">
      <h3>代表性行为样本</h3>
      <p class="muted persona-console-note">这些样本按行为权重排序，用来支撑画像摘要、结构化偏好和后续 AI 调用。</p>
      ${rankedHtml}
    </section>
    <section class="persona-console-section mt-1">
      <h3>行为工作台</h3>
      <p class="muted persona-console-note">从这里可以直接顺着你的行为证据进入知识库检索或图谱视图，形成“浏览 -> 画像 -> 检索 -> 研究”的闭环。</p>
      ${renderPersonaWorkbench(consoleData)}
    </section>
    <section class="persona-console-section mt-1">
      <h3>画像证据映射</h3>
      <p class="muted persona-console-note">这里展示画像实际参考了哪些行为类型、信源和反馈模式。</p>
      <div class="persona-console-evidence-grid">
        ${evidenceBlocks.join("") || "<p class='muted'>暂无结构化证据映射。</p>"}
      </div>
    </section>
    <section class="persona-console-section mt-1">
      <h3>去重与采集说明</h3>
      <div class="persona-console-policy">
        <p class="muted">${escapeHtml(dedupNote.event_level || "行为事件写入前会按 dedup key 去重，避免同一事件反复入库。")}</p>
        <p class="muted">${escapeHtml(dedupNote.inventory_level || "账号收藏/关注类同步会作为清单快照保留，并与近期高频行为分开统计。")}</p>
        <p class="muted">${escapeHtml(dedupNote.semantic_limit || "跨平台同主题内容仍可能同时出现，这是语义层重合，不等于原始事件重复写入。")}</p>
      </div>
    </section>
  </div>`;
}

function renderPersonaModel(model) {
  if (!model || typeof model !== "object") return "<p class='muted'>暂无心智模型，请先完成行为同步并构建画像。</p>";
  const parts = [];
  if (model.version != null) {
    const builtAt = model.built_at ? formatPersonaDateTime(model.built_at) : "";
    const eventsNote = model.events_at_last_build != null ? `${model.events_at_last_build} 条行为` : "";
    const meta = [builtAt, eventsNote].filter(Boolean).join(" · ");
    parts.push(
      `<div class="persona-summary-grid"><div class="persona-stat">版本<strong>v${escapeHtml(String(model.version))}</strong><span class="muted">${escapeHtml(meta)}</span></div></div>`,
    );
  }
  const srcMap = model.recent_sources;
  if (srcMap && typeof srcMap === "object" && Object.keys(srcMap).length) {
    const srcLine = Object.entries(srcMap)
      .sort((a, b) => Number(b[1]) - Number(a[1]))
      .map(([k, v]) => `${escapeHtml(SOURCE_LABELS[k] || k)} ${v}`)
      .join(" · ");
    parts.push(`<div class="persona-field"><strong>近期信源</strong><p class="muted">${srcLine}</p></div>`);
  }
  const breakdown = model.event_breakdown;
  const recent7d = breakdown?.recent_activity_7d;
  if (recent7d && typeof recent7d === "object" && Object.keys(recent7d).length) {
    const line = Object.entries(recent7d)
      .sort((a, b) => Number(b[1]) - Number(a[1]))
      .slice(0, 8)
      .map(([k, v]) => `${escapeHtml(formatEventType(k))} ${v}`)
      .join(" · ");
    parts.push(`<div class="persona-field"><strong>近 7 日行为信号</strong><p class="muted">${line}</p></div>`);
  }
  const hints = model.high_interest_hints;
  if (Array.isArray(hints) && hints.length) {
    parts.push(
      `<div class="persona-field"><strong>高兴趣线索</strong><ul class="persona-hint-list">${hints
        .slice(0, 12)
        .map((h) => {
          const title = escapeHtml((h.title || "（无标题）").slice(0, 120));
          const src = escapeHtml(SOURCE_LABELS[h.source] || h.source || "");
          const url = h.url ? `<a href="${safeHref(h.url)}" target="_blank" rel="noopener">${title}</a>` : title;
          return `<li>${url}${src ? ` <span class="muted">· ${src}</span>` : ""}</li>`;
        })
        .join("")}</ul></div>`,
    );
  }
  [
    ["interest_domains", "长期兴趣"],
    ["active_projects", "当前项目"],
    ["knowledge_goals", "知识目标"],
    ["entity_affinities", "高频实体"],
    ["reading_style", "阅读风格"],
    ["avoid_patterns", "反感模式"],
  ].forEach(([key, label]) => {
    const html = renderStructuredPersonaField(label, model[key]);
    if (html) parts.push(html);
  });
  if (model.source_preferences && typeof model.source_preferences === "object") {
    const pref = model.source_preferences;
    const prefBlocks = [
      renderStructuredPersonaField("偏好信源", pref.preferred || pref.sources || []),
      renderStructuredPersonaField("回避信源", pref.avoid || pref.disliked || []),
      renderStructuredPersonaField("低价值模式", pref.low_value_patterns || pref.low_value || []),
    ].filter(Boolean);
    if (prefBlocks.length) {
      parts.push(`<div class="persona-field"><strong>信源偏好</strong>${prefBlocks.join("")}</div>`);
    }
  }
  const listFields = [
    ["interests", "兴趣"],
    ["topics", "话题"],
    ["domains", "领域"],
    ["preferred_sources", "常看来源"],
    ["keywords", "关键词"],
  ];
  listFields.forEach(([key, label]) => {
    const val = model[key];
    if (Array.isArray(val) && val.length) {
      parts.push(
        `<div class="persona-field"><strong>${label}</strong><div class="chip-group">${val
          .slice(0, 24)
          .map((v) => `<span class="chip">${escapeHtml(String(v))}</span>`)
          .join("")}</div></div>`,
      );
    }
  });
  if (typeof model.summary === "string" && model.summary.trim()) {
    parts.push(`<div class="persona-field"><strong>摘要</strong><p class="muted">${escapeHtml(model.summary.trim())}</p></div>`);
  }
  if (!parts.length) {
    return `<p class="muted">画像已生成，但结构较简。展开下方可查看原始数据。</p>
      <details class="mt-1"><summary>原始数据</summary><pre>${escapeHtml(JSON.stringify(model, null, 2))}</pre></details>`;
  }
  parts.push(
    `<details class="mt-1"><summary class="muted">原始 JSON（调试用）</summary><pre>${escapeHtml(JSON.stringify(model, null, 2))}</pre></details>`,
  );
  return parts.join("");
}

/* 画像 */
function initPersona() {
  loadSetupWizard();
  loadPersona();
  loadPersonaStaleBanner();
  document.getElementById("btn-build-persona")?.addEventListener("click", async () => {
    const btn = document.getElementById("btn-build-persona");
    if (btn) {
      btn.disabled = true;
      btn.textContent = "构建中…";
    }
    try {
      const data = await api("POST", "/api/persona/build?review=true");
      showPersonaReview(data);
      const noticeEl = document.getElementById("persona-notice");
      if (noticeEl) {
        noticeEl.className = `alert alert-${data.brief_ai_error ? "warn" : "success"} page-notice`;
        noticeEl.innerHTML = "";
        const ver = document.createElement("span");
        ver.textContent = `画像 v${data.version} 已生成`;
        noticeEl.appendChild(ver);
        if (data.brief_ai_error) {
          const err = document.createElement("span");
          err.textContent = `，但 AI 摘要失败：${data.brief_ai_error}`;
          noticeEl.appendChild(err);
        } else {
          const sep = document.createTextNode("。");
          const link = document.createElement("a");
          link.href = "/";
          link.textContent = "去搜罗页试试画像模拟";
          noticeEl.appendChild(sep);
          noticeEl.appendChild(link);
        }
        noticeEl.classList.remove("hidden");
        setTimeout(() => noticeEl.classList.add("hidden"), 10000);
      }
      loadPersona();
    } catch (err) {
      showPageNotice("persona-notice", escapeHtml(err.message), "error");
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = "构建画像";
      }
    }
  });
}

function showPersonaReview(data) {
  const panel = document.getElementById("persona-review-panel");
  if (!panel || !data.review_summary) return;
  const r = data.review_summary;
  panel.classList.remove("hidden");
  panel.innerHTML = `<h2>构建对比</h2>
    <p class="muted">Brief 变化摘要</p>
    <div class="grid-2 persona-review-grid">
      <div class="persona-review-col"><h3 class="persona-review-heading">构建前</h3><div class="markdown-body persona-brief-panel" id="persona-review-before"></div></div>
      <div class="persona-review-col"><h3 class="persona-review-heading">构建后</h3><div class="markdown-body persona-brief-panel" id="persona-review-after"></div></div>
    </div>
    <p class="mt-1"><a href="/" class="btn btn-sm">去搜罗试试</a></p>`;
  renderMarkdown(document.getElementById("persona-review-before"), r.brief_before || "");
  renderMarkdown(document.getElementById("persona-review-after"), r.brief_after || "");
}

async function loadPersona() {
  const el = document.getElementById("persona-content");
  if (!el) return;
  try {
    const data = await api("GET", "/api/persona");
    const versionHistory = data.version_history || [];
    const model = data.mental_model || {};
    const hasModel = data.built || (model.events_at_last_build != null && model.events_at_last_build > 0);
    if (!hasModel && !versionHistory.length) {
      el.innerHTML = renderEmptyStateRich(
        "persona",
        "尚未构建心智画像",
        "建议顺序：<a href=\"/ingest\">完整同步</a> 行为数据 → 点击下方「构建画像」→ 回到 <a href=\"/\">搜罗</a> 开启画像模拟。",
        `<a href="/ingest" class="btn btn-sm">去完整同步</a>`,
      );
      return;
    }
    el.innerHTML = `
      <div class="card persona-brief-card"><h2>可读摘要（Brief）</h2>
        ${data.brief_ai_error ? `<div class="alert alert-warn">AI 摘要生成失败：${escapeHtml(String(data.brief_ai_error))}。下方为规则摘要；请检查 API Key 后重新构建。</div>` : ""}
        ${data.brief_ai_generated === false && !data.brief_ai_error ? `<p class="muted section-hint">当前为规则摘要；配置 DeepSeek 后点「构建画像」可生成 AI 叙事版。</p>` : ""}
        <div class="markdown-body persona-brief-panel" id="persona-brief"></div>
      </div>
      ${renderPersonaProjectsCard(model)}
      ${renderPersonaEvidenceConsole(data.console)}
      <div class="card"><h2>心智模型</h2>${renderPersonaModel(data.mental_model)}</div>
      ${renderPersonaVersionHistory(versionHistory, model.version)}`;
    bindPersonaWorkbench(el);
    el.querySelectorAll(".btn-persona-rollback").forEach((btn) => {
      btn.addEventListener("click", () => {
        const ver = parseInt(btn.dataset.version, 10);
        if (ver) void rollbackPersona(ver);
      });
    });
    renderMarkdown(document.getElementById("persona-brief"), data.brief || "（暂无）");
    ensureReadingSurface(document.getElementById("persona-brief"));
  } catch (err) {
    el.innerHTML = `<div class="alert alert-error">${escapeHtml(err.message)}</div>`;
  }
}

async function rollbackPersona(version) {
  const ok = window.confirm(`确认恢复到 v${version}？当前画像与摘要将被替换。`);
  if (!ok) return;
  try {
    const data = await api("POST", "/api/persona/rollback", { version });
    if (data.ok) {
      showPageNotice("persona-notice", `已恢复到 v${version}`, "success");
      loadPersona();
    } else {
      showPageNotice("persona-notice", "版本不存在", "error");
    }
  } catch (err) {
    showPageNotice("persona-notice", escapeHtml(err.message), "error");
  }
}

/* 导入 */
function formatPersonaRebuildHint(rebuild) {
  if (!rebuild || rebuild.action === "none") {
    return '<a href="/persona">去构建画像</a>';
  }
  if (rebuild.action === "rebuilt") {
    const v = rebuild.version != null ? ` v${rebuild.version}` : "";
    return `画像已自动重建${v} · <a href="/persona">查看画像</a> · <a href="/">开始搜罗</a>`;
  }
  if (rebuild.action === "failed") {
    return `<span class="muted">画像自动重建失败</span> · <a href="/persona">手动构建</a>`;
  }
  return '<a href="/persona">建议更新画像</a>';
}

function extractPersonaRebuild(steps) {
  const acct = (steps || []).find((s) => s.step === "accounts-sync");
  return acct?.persona_rebuild || null;
}

function buildFullSyncResultHtml(job) {
  const count = job.count || 0;
  const steps = job.steps || [];
  const preflight = steps.find((s) => s.step === "preflight");
  if (!job.ok && count === 0 && preflight && preflight.ok === false) {
    const hints = (preflight.data?.hints || job.warnings || [])
      .map(escapeHtml)
      .join("<br>");
    return {
      className: "alert alert-error mt-1",
      html: `<strong>同步未开始</strong>：Cookie 或登录态未就绪。<br>${hints}<br><a href="/settings">去设置页同步 Cookie</a>`,
    };
  }
  const rebuild = extractPersonaRebuild(steps);
  if (count === 0) {
    return {
      className: "alert alert-warn mt-1",
      html: `同步完成但未导入新数据。请检查 Cookie / 隐私设置，或尝试 <a href="/ingest#extension">浏览器补洞</a> · <a href="/settings">Cookie 设置</a> · ${formatPersonaRebuildHint(rebuild)}`,
    };
  }
  let html = `完整同步完成：共 ${count} 条 · ${formatPersonaRebuildHint(rebuild)}`;
  if (job.warnings?.length) {
    html += `<br><span class="muted">${job.warnings.map(escapeHtml).join("；")}</span>`;
  }
  const hint = job.extension_flush_hint;
  if (hint?.message) {
    html += `<br><div class="alert alert-warn mt-1" style="margin-top:0.5rem">${escapeHtml(hint.message)}</div>`;
  }
  return { className: "alert alert-success mt-1", html };
}

async function recoverActiveSearches() {
  if (new URLSearchParams(window.location.search).get("run")) return;
  if (workspaceSession.activeRunId) return;
  try {
    const data = await api("GET", "/api/search/tasks?limit=30");
    const tasks = data.tasks || [];
    const active = tasks.filter((t) => t.status === "running" || t.status === "queued");
    renderSearchTaskList(tasks);
    active.forEach((t) => {
      searchTaskRegistry.lastStatusByRun.set(t.run_id || t.job_id, t.status);
    });
    if (active.length) startSearchTaskPolling();
    if (active.length === 1) {
      void resumeSearchRun(active[0].run_id || active[0].job_id);
      return;
    }
    if (active.length > 1) {
      const panel = document.getElementById("search-task-panel");
      panel?.setAttribute("open", "");
      hideWorkspaceAlert("active-search-banner");
      showWorkspaceAlert(
        "active-search-banner",
        `检测到 ${active.length} 个进行中的搜罗，请在下方「搜罗任务」列表中切换查看。`,
        "warn",
      );
    }
  } catch (_) {}
}

const INGEST_STEP_BUTTON_IDS = [
  "btn-ingest-browser",
  "btn-ingest-bilibili",
  "btn-ingest-zhihu",
  "btn-ingest-aicu",
  "btn-ingest-aicu-json",
  "btn-ingest-accounts-sync",
  "btn-ingest-browser-sync",
];

function setIngestStepButtonsEnabled(ready) {
  INGEST_STEP_BUTTON_IDS.forEach((id) => {
    const btn = document.getElementById(id);
    if (!btn) return;
    btn.disabled = !ready;
    btn.title = ready ? "" : "Cookie 未就绪，请先同步后再导入";
  });
}

async function loadIngestPreflight() {
  const el = document.getElementById("ingest-preflight-content");
  const btn = document.getElementById("btn-ingest-full-sync");
  if (!el) return false;
  try {
    const [pre, ext] = await Promise.all([
      api("GET", "/api/ingest/preflight", null, { timeoutMs: 15000 }),
      api("GET", "/api/extension/status?lite=1", null, { timeoutMs: 5000 }).catch(() => ({ connected: false })),
    ]);
    const rows = [];
    const biliOk = pre.login?.bilibili?.ok ?? false;
    const zhOk = pre.login?.zhihu?.ok ?? false;
    rows.push(
      `<div class="preflight-row"><span>B站登录</span><span class="preflight-badge ${biliOk ? "ok" : "fail"}">${biliOk ? "通过" : "未就绪"}</span></div>`,
    );
    rows.push(
      `<div class="preflight-row"><span>知乎登录</span><span class="preflight-badge ${zhOk ? "ok" : "fail"}">${zhOk ? "通过" : "未就绪"}</span></div>`,
    );
    rows.push(
      `<div class="preflight-row"><span>浏览器扩展</span><span class="preflight-badge ${ext.connected ? "ok" : "warn"}">${ext.connected ? "已连接" : "未连接（可选）"}</span></div>`,
    );
    let hints = "";
    if (!pre.ready) {
      hints = `<div class="alert alert-warn mt-1">${(pre.hints || ["请先在设置或扩展弹窗同步 Cookie"]).map(escapeHtml).join("<br>")}<br><a href="/settings">去设置页同步 Cookie</a> · <a href="/ingest#extension">查看扩展安装</a></div>`;
      if (btn) {
        btn.disabled = true;
        btn.title = "Cookie 未就绪，请先同步后再完整同步";
      }
      setIngestStepButtonsEnabled(false);
    } else {
      hints = `<div class="alert alert-success mt-1">可以开始完整同步（约 2–5 分钟）。${!biliOk || !zhOk ? "<br><span class=\"muted\">提示：单平台就绪即可同步，未登录的平台将跳过。</span>" : ""}</div>`;
      if (btn) {
        btn.disabled = false;
        btn.title = "";
      }
      setIngestStepButtonsEnabled(true);
    }
    el.innerHTML = rows.join("") + hints;
    return !!pre.ready;
  } catch (err) {
    el.innerHTML = `<div class="alert alert-error">${escapeHtml(err.message)}</div>`;
    return false;
  }
}

function initIngest() {
  checkAuthBanner();
  loadSetupWizard();
  loadPersonaStaleBanner();
  void loadIngestPreflight();
  loadIngestHealth();
  document.getElementById("btn-ingest-browser")?.addEventListener("click", async (e) => {
    const days = parseInt(document.getElementById("browser-since").value, 10) || 90;
    await runIngest("browser", { since_days: days }, "ingest-browser-result", e.currentTarget);
  });
  document.getElementById("btn-ingest-bilibili")?.addEventListener("click", (e) =>
    runIngest("bilibili", null, "ingest-bilibili-result", e.currentTarget));
  document.getElementById("btn-ingest-aicu")?.addEventListener("click", (e) =>
    runIngest("aicu-comments", null, "ingest-aicu-result", e.currentTarget));
  document.getElementById("btn-ingest-aicu-json")?.addEventListener("click", async () => {
    const el = document.getElementById("ingest-aicu-result");
    const raw = document.getElementById("aicu-json-input")?.value?.trim();
    if (!raw) {
      el.className = "alert alert-error";
      el.textContent = "请先粘贴 JSON";
      return;
    }
    el.textContent = "导入中…";
    try {
      const payload = JSON.parse(raw);
      const data = await api("POST", "/api/ingest/aicu-json", { payload });
      if (data.ok === false) {
        el.className = "alert alert-error";
        el.textContent = data.error || "导入失败";
        return;
      }
      el.className = "alert alert-success";
      el.innerHTML = `共 ${data.count} 条（跳过重复 ${data.skipped || 0}）。<a href="/persona">去构建画像</a>`;
    } catch (err) {
      el.className = "alert alert-error";
      el.textContent = err.message;
    }
  });
  document.getElementById("btn-ingest-zhihu")?.addEventListener("click", (e) =>
    runIngest("zhihu", null, "ingest-zhihu-result", e.currentTarget));
  document.getElementById("btn-ingest-full-sync")?.addEventListener("click", async () => {
    const el = document.getElementById("ingest-full-sync-result");
    const progressEl = document.getElementById("ingest-full-sync-progress");
    const btn = document.getElementById("btn-ingest-full-sync");
    if (!el) return;
    if (btn) {
      btn.disabled = true;
      btn.textContent = "同步中…";
    }
    el.className = "alert alert-warn mt-1";
    el.textContent = "启动完整同步…";
    let progressUi = null;
    if (progressEl) {
      progressEl.classList.remove("hidden");
      progressEl.innerHTML = "";
      progressUi = mountJobProgress(progressEl, { cancelUrl: "" });
    }
    const syncStepLabels = {
      preflight: "Cookie 预检",
      "accounts-sync": "B站/知乎 API",
      "browser-history": "Edge 浏览历史",
      "browser-sync": "浏览器补洞",
      aicu: "AICU 发评",
      "extension-flush": "扩展上报",
      done: "完成",
    };
    try {
      const pre = await api("GET", "/api/ingest/preflight");
      if (!pre.ready) {
        progressUi?.stop();
        el.className = "alert alert-error mt-1";
        el.innerHTML = `${(pre.hints || ["Cookie 未就绪，请先同步"]).map(escapeHtml).join("<br>")}<br><a href="/settings">去设置页同步 Cookie</a>`;
        return;
      }
      const start = await api("POST", "/api/ingest/full-sync");
      const jobId = start.job_id;
      if (!jobId) throw new Error("未返回 job_id");
      if (progressUi) {
        progressUi.stop();
        progressUi = mountJobProgress(progressEl, {
          cancelUrl: `/api/ingest/full-sync/${jobId}/cancel`,
          labelFn: (name) => syncStepLabels[name] || stepLabel(name),
        });
      }
      for (let i = 0; i < 180; i += 1) {
        await new Promise((r) => setTimeout(r, 1000));
        const job = await api("GET", `/api/ingest/full-sync/${jobId}`);
        if (job.progress && progressUi) progressUi.update(job.progress);
        if (job.status === "running") continue;
        progressUi?.stop();
        if (job.status === "cancelled") {
          el.className = "alert alert-warn mt-1";
          el.textContent = job.error || "完整同步已取消";
          return;
        }
        if (job.status === "done") {
          const rendered = buildFullSyncResultHtml(job);
          el.className = rendered.className;
          el.innerHTML = rendered.html;
          loadIngestHealth();
          loadPersonaStaleBanner();
          void loadIngestPreflight();
          loadSetupWizard();
          void loadLikes();
          invalidateShellCache();
          void pollActiveJobs();
          void refreshMobileStatusBar();
          return;
        }
        throw new Error(job.detail || "同步失败");
      }
      progressUi?.stop();
      el.className = "alert alert-warn mt-1";
      el.innerHTML =
        '同步时间较长，任务可能仍在后台运行。<a href="/ingest">刷新本页</a> 或查看侧栏「后台任务」。';
    } catch (err) {
      progressUi?.stop();
      el.className = "alert alert-error mt-1";
      el.textContent = err.message;
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = "开始完整同步";
      }
    }
  });
  document.getElementById("btn-ingest-accounts-sync")?.addEventListener("click", async () => {
    const el = document.getElementById("ingest-accounts-sync-result");
    const progressEl = document.getElementById("ingest-accounts-sync-progress");
    if (!el) return;
    el.className = "alert alert-warn mt-1";
    el.textContent = "检查 Cookie…";
    let progressUi = null;
    if (progressEl) {
      progressEl.classList.remove("hidden");
      progressEl.innerHTML = "";
      progressUi = mountJobProgress(progressEl);
      progressUi.update({ phase: "preflight", detail: "检查登录态…", percent: 5 });
    }
    try {
      const pre = await api("GET", "/api/ingest/preflight");
      if (!pre.ready) {
        progressUi?.stop();
        el.className = "alert alert-error mt-1";
        el.innerHTML = `${(pre.hints || ["Cookie 未就绪"]).map(escapeHtml).join("<br>")}<br><a href="/settings">去设置页同步 Cookie</a>`;
        return;
      }
      progressUi?.update({ phase: "accounts-sync", detail: "拉取 B站/知乎…", percent: 15 });
      el.textContent = "服务端拉取中…全量约需 2–4 分钟，请勿关闭页面";
      const ctrl = new AbortController();
      const timer = setTimeout(() => ctrl.abort(), 360000);
      const res = await fetch("/api/ingest/accounts-sync", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: ctrl.signal,
      });
      clearTimeout(timer);
      progressUi?.update({ phase: "done", detail: "处理结果…", percent: 95 });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || res.statusText);
      const b = data.bilibili || {};
      const z = data.zhihu || {};
      const ok = (data.count || 0) > 0;
      el.className = ok ? "alert alert-success mt-1" : "alert alert-warn mt-1";
      let msg = `共 ${data.count || 0} 条：B站 ${b.count || 0}（观看 ${b.watch_count || 0} / 收藏 ${b.favorite_count || 0} / 点赞 ${b.like_count || 0} / 关注 ${b.following_count || 0}），知乎 ${z.count || 0}（收藏 ${z.favorite_count || 0} / 动态 ${z.activity_count || 0} / 赞同 ${z.vote_count || 0} / 浏览 ${z.browse_count || 0} / 回答 ${z.answer_count || 0}）`;
      const layers = z.layer_status;
      if (layers) {
        const layerLine = ["votes", "browse", "activity"]
          .map((k) => {
            const block = layers[k];
            if (!block) return "";
            const label = k === "votes" ? "赞同" : k === "browse" ? "浏览" : "动态";
            return `${label}:${block.status || "?"}`;
          })
          .filter(Boolean)
          .join(" · ");
        if (layerLine) msg += `<br><span class="muted">画像三要素 ${escapeHtml(layerLine)}</span>`;
      }
      if (data.python) msg += ` · Python ${escapeHtml(data.python)}`;
      msg += ` · ${formatPersonaRebuildHint(data.persona_rebuild)}`;
      if (data.warnings?.length) {
        msg += `<br><span class="muted">${data.warnings.map(escapeHtml).join("；")}</span>`;
      }
      const bs = data.browser_sync;
      if (bs && (bs.accepted != null || bs.warnings?.length)) {
        msg += `<br><span class="muted">Playwright 补洞：写入 ${bs.accepted || 0} 条</span>`;
        if (bs.warnings?.length) {
          msg += `<br><span class="muted">${bs.warnings.map(escapeHtml).join("；")}</span>`;
        }
      }
      el.innerHTML = msg;
      progressUi?.stop();
      loadIngestHealth();
      loadPersonaStaleBanner();
      void loadIngestPreflight();
      void loadLikes();
    } catch (err) {
      progressUi?.stop();
      el.className = "alert alert-error mt-1";
      el.textContent = err.name === "AbortError" ? "请求超时（>6 分钟）。请确认 Web 已启动后重试。" : err.message;
    }
  });
  document.getElementById("btn-ingest-browser-sync")?.addEventListener("click", async () => {
    const el = document.getElementById("ingest-browser-sync-result");
    const progressEl = document.getElementById("ingest-browser-sync-progress");
    if (!el) return;
    el.className = "alert alert-warn mt-1";
    el.textContent = "检查浏览器补洞环境…";
    let progressUi = null;
    if (progressEl) {
      progressEl.classList.remove("hidden");
      progressEl.innerHTML = "";
      progressUi = mountJobProgress(progressEl);
    }
    try {
      const st = await api("GET", "/api/ingest/browser-sync/status");
      if (!st.playwright_installed) {
        progressUi?.stop();
        el.className = "alert alert-error mt-1";
        el.innerHTML =
          '未安装浏览器自动化组件。请前往 <a href="/settings#deps">设置 → 环境检查</a> 点击「一键安装 Playwright」。';
        return;
      }
      progressUi?.update({ phase: "browser-sync", detail: "启动浏览器补洞…", percent: 10 });
      el.textContent = "浏览器会话同步中…（约 2–5 分钟）";
      const start = await api("POST", "/api/ingest/browser-sync", {
        platforms: ["bilibili"],
      });
      const jobId = start.job_id;
      if (!jobId) throw new Error("未返回 job_id");
      for (let i = 0; i < 120; i += 1) {
        await new Promise((r) => setTimeout(r, 2500));
        const job = await api("GET", `/api/ingest/browser-sync/${jobId}`);
        if (job.progress && progressUi) progressUi.update(job.progress);
        if (job.status === "running") continue;
        progressUi?.stop();
        if (job.status === "done") {
          const ok = (job.accepted || 0) > 0;
          el.className = ok ? "alert alert-success mt-1" : "alert alert-warn mt-1";
          let msg = `Playwright 写入 ${job.accepted || 0} 条，跳过 ${job.skipped || 0}，耗时 ${job.duration_sec || "?"}s`;
          if (job.mode_used) msg += ` · 模式 ${escapeHtml(job.mode_used)}`;
          if (job.pages_visited?.length) {
            msg += ` · 访问 ${job.pages_visited.length} 页`;
          }
          if (ok) msg += ` · ${formatPersonaRebuildHint(null)}`;
          if (job.warnings?.length) {
            msg += `<br><span class="muted">${job.warnings.map(escapeHtml).join("；")}</span>`;
          }
          el.innerHTML = msg;
          loadIngestHealth();
          void loadLikes();
          return;
        }
        throw new Error(job.detail || "同步失败");
      }
      el.className = "alert alert-error mt-1";
      el.textContent = "超时（>5 分钟）。请确认 Edge 已关闭或改用 CDP 模式。";
    } catch (err) {
      el.className = "alert alert-error mt-1";
      el.textContent = err.message;
    }
  });
  document.getElementById("btn-extension-refresh")?.addEventListener("click", () => {
    loadExtensionStatus();
    void loadLikes();
  });
  document.getElementById("btn-recognition-refresh")?.addEventListener("click", () => loadLikes());
  loadExtensionStatus();
  loadLikes();
  loadIngestCapabilities();
  void loadAicuStatus();
}

async function loadAicuStatus() {
  const el = document.getElementById("aicu-status-badge");
  if (!el) return;
  try {
    const data = await api("GET", "/api/ingest/aicu-status?probe=true");
    if (!data.enabled) {
      el.className = "aicu-status-badge preflight-badge warn";
      el.textContent = "AICU 未开启（config: sync.aicu_enabled）";
      return;
    }
    const status = data.status || "UNKNOWN";
    const labels = {
      PASS: "AICU 可用",
      WAF_BLOCKED: "AICU 被 WAF 拦截",
      DISABLE: "AICU 未就绪",
      FAIL: "AICU 探测失败",
      READY: "AICU 已配置",
    };
    const cls = status === "PASS" ? "ok" : status === "WAF_BLOCKED" ? "warn" : status === "DISABLE" ? "warn" : "fail";
    el.className = `aicu-status-badge preflight-badge ${cls}`;
    let text = labels[status] || status;
    if (data.mid) text += ` · UID ${data.mid}`;
    if (data.sample_count != null && status === "PASS") text += ` · 样本 ${data.sample_count} 条`;
    if (data.reason && status !== "PASS") text += ` · ${data.reason}`;
    el.textContent = text;
  } catch (err) {
    el.className = "aicu-status-badge preflight-badge fail";
    el.textContent = `AICU 状态未知：${err.message}`;
  }
}

async function loadExtensionStatus() {
  const el = document.getElementById("extension-status");
  if (!el) return;
  try {
    const data = await api("GET", "/api/extension/status", null, { timeoutMs: 15000 });
    const connected = data.connected;
    const total = data.extension_event_count || 0;
    const pending = data.pending_queue || 0;
    const flushErr = data.last_flush_error || "";
    const version = data.extension_version || "";
    const types = Object.entries(data.event_totals || {})
      .map(([k, v]) => `${EXT_EVENT_LABELS[k] || k} ${v}`)
      .join(" · ");
    el.className = "extension-status-card";
    let queueLine = "";
    if (pending > 0) {
      queueLine = `<div class="alert alert-warn mt-1">扩展队列待上传 <strong>${pending}</strong> 条 · 请在扩展弹窗点「上传浏览采集队列」</div>`;
    } else if (flushErr) {
      queueLine = `<div class="alert alert-error mt-1">上次上传失败：${escapeHtml(flushErr.slice(0, 120))}</div>`;
    }
    el.innerHTML = `
      <div class="preflight-row">
        <strong>${connected ? "扩展已连接" : "未检测到扩展"}</strong>
        <span class="preflight-badge ${connected ? "ok" : "warn"}">${connected ? "正常" : "待安装/离线"}</span>
      </div>
      ${version ? `<p class="muted">扩展版本 ${escapeHtml(version)}</p>` : ""}
      <p class="muted mt-1">已采集事件 <strong>${total}</strong> 条${types ? `（${escapeHtml(types)}）` : ""}</p>
      ${data.last_seen ? `<p class="muted">最近心跳 ${escapeHtml(formatRunTime(data.last_seen))}</p>` : "<p class='muted'>安装扩展后打开任意网页，再点「刷新状态」</p>"}
      ${queueLine}
      ${connected ? "" : '<p class="muted"><a href="#extension">查看安装步骤</a></p>'}`;
  } catch (err) {
    el.className = "extension-status-card";
    el.innerHTML = `<div class="alert alert-error">无法连接 Web 服务：${escapeHtml(err.message)}</div>`;
  }
}

async function loadIngestHealth() {
  const el = document.getElementById("ingest-health-content");
  if (!el) return;
  try {
    const data = await api("GET", "/api/ingest/health");
    const blockers = (data.blockers || []).map((b) => `<li class="health-blocker">${escapeHtml(b)}</li>`).join("");
    const warnings = (data.warnings || []).map((w) => `<li class="health-warn">${escapeHtml(w)}</li>`).join("");
    const auth = Object.entries(data.auth || {})
      .map(([k, v]) => {
        const label = k === "bilibili.com" ? "B站" : k === "zhihu.com" ? "知乎" : k;
        return `${escapeHtml(label)} ${v.ok ? "✓" : "✗"}`;
      })
      .join(" · ");
    const events = data.events?.total ?? 0;
    const coverage = (data.coverage || [])
      .map((p) => {
        const platformLabel =
          { bilibili: "B站", zhihu: "知乎", browser: "浏览器", extension: "扩展" }[p.platform] || p.platform;
        const withData = (p.behaviors || [])
          .filter((b) => b.count > 0)
          .map((b) => `${escapeHtml(b.behavior)} ${b.count}`)
          .join("，");
        const missing = (p.behaviors || [])
          .filter((b) => b.count === 0)
          .slice(0, 4)
          .map((b) => `<span class="health-missing">${escapeHtml(b.behavior)} 0</span>`)
          .join(" ");
        const detail = [withData, missing].filter(Boolean).join(" · ");
        return `<div class="preflight-row"><strong>${escapeHtml(platformLabel)}</strong><span>${p.total} 条${detail ? ` — ${detail}` : ""}</span></div>`;
      })
      .join("");
    const partialHint =
      (data.partial_capabilities || 0) > 0
        ? `<div class="alert alert-warn mt-1">${data.partial_capabilities} 项能力需扩展或浏览器补洞配合 · <a href="#extension">查看扩展</a> · <a href="#ingest-capabilities">能力表</a></div>`
        : "";
    const aicu = data.aicu || {};
    let aicuHint = "";
    if (aicu.enabled) {
      const mid = aicu.mid ? ` · UID ${escapeHtml(String(aicu.mid))}` : "";
      aicuHint = `<div class="alert alert-info mt-1">AICU 发评导入已开启${mid} · <a href="#aicu-section">查看 AICU 状态</a></div>`;
    }
    const statusClass = data.ok ? "alert-success" : "alert-warn";
    el.innerHTML = `
      <div class="alert ${statusClass}">${data.ok ? "数据就绪，可构建画像" : "尚有阻塞项"} · 行为事件共 ${events} 条 · ${auth}</div>
      ${blockers ? `<ul class="health-list">${blockers}</ul>` : ""}
      ${warnings ? `<ul class="health-list muted">${warnings}</ul>` : ""}
      ${partialHint}
      ${aicuHint}
      <div class="mt-1">${coverage || "<span class='muted'>暂无平台数据，请先完整同步</span>"}</div>
      <div class="muted mt-1">浏览器补洞：${data.playwright_installed ? "已安装" : '<a href="/settings#deps">未安装（去设置）</a>'} · 需扩展配合的能力 ${data.partial_capabilities || 0} 项</div>`;
  } catch (err) {
    el.textContent = `无法加载：${err.message}`;
  }
}

async function loadIngestCapabilities() {
  const el = document.getElementById("ingest-capabilities");
  if (!el) return;
  const scroll = el.querySelector(".table-scroll") || el;
  try {
    const data = await api("GET", "/api/ingest/capabilities");
    const platformLabels = { bilibili: "B站", zhihu: "知乎", browser: "浏览器", extension: "扩展", weixin: "搜狗微信公众平台" };
    const partialCount = (data.items || []).filter((i) => i.status === "partial").length;
    const rows = (data.items || [])
      .map((i) => {
        const st = i.status || "";
        const stClass = st === "supported" ? "cap-status-supported" : st === "partial" ? "cap-status-partial" : "";
        return `<tr>
          <td>${escapeHtml(platformLabels[i.platform] || i.platform)}</td>
          <td>${escapeHtml(i.behavior)}</td>
          <td class="${stClass}">${escapeHtml(formatCapabilityStatus(st))}</td>
          <td class="muted">${escapeHtml(i.note)}</td>
        </tr>`;
      })
      .join("");
    const summary =
      partialCount > 0
        ? `<p class="alert alert-warn mt-1">${partialCount} 项需扩展/浏览器补洞 · <a href="#extension">安装扩展</a></p>`
        : "";
    scroll.innerHTML = `${summary}<table class="data-table"><thead><tr><th>平台</th><th>行为</th><th>状态</th><th>说明</th></tr></thead><tbody>${rows}</tbody></table>`;
  } catch (err) {
    scroll.innerHTML = `<p class="alert alert-error">无法加载能力说明：${escapeHtml(err.message)}</p>`;
  }
}

async function runIngest(type, body, resultId, triggerBtn) {
  const el = document.getElementById(resultId);
  const btn = triggerBtn && triggerBtn instanceof HTMLElement ? triggerBtn : null;
  const prevText = btn?.textContent;
  if (btn) {
    btn.disabled = true;
    btn.textContent = "进行中…";
  }
  if (el) el.textContent = "导入中…";
  try {
    const url = type === "browser" ? "/api/ingest/browser" : `/api/ingest/${type}`;
    const data = await api("POST", url, body);
    const ok = (data.count || 0) > 0 && data.ok !== false;
    el.className = ok ? "alert alert-success" : "alert alert-warn";
    let detail = `共 ${data.count || 0} 条`;
    if (data.watch_count != null) {
      detail += `（观看 ${data.watch_count}，收藏 ${data.favorite_count || 0}，点赞 ${data.like_count || 0}，关注 ${data.following_count || 0}）`;
    } else if (data.favorite_count != null || data.vote_count != null) {
      detail += `（收藏 ${data.favorite_count || 0}，动态 ${data.activity_count || 0}，赞同 ${data.vote_count || 0}，浏览 ${data.browse_count || 0}）`;
    } else if (data.all_count != null && data.all_count > 0) {
      detail += `（AICU 索引约 ${data.all_count} 条，跳过重复 ${data.skipped || 0}）`;
    }
    if (data.ok === false && data.error) {
      el.className = "alert alert-error";
      const errMap = {
        aicu_disabled: "请先在 config 中设置 sync.aicu_enabled: true（或 ingest.aicu_enabled）",
        bilibili_not_logged_in: "需要有效的 B 站 Cookie（仅用于获取 UID）",
        aicu_waf_blocked: "AICU 拦截了程序访问：请用扩展「浏览器拉取 AICU 发评」或粘贴 JSON",
        aicu_json_empty: "JSON 中未找到 replies 数据",
      };
      if (data.error === "aicu_waf_blocked" && data.hint) {
        el.textContent = `${errMap.aicu_waf_blocked}。${data.hint}`;
        return;
      }
      el.textContent = errMap[data.error] || data.error;
      return;
    }
    let msg = `${detail} · ${formatPersonaRebuildHint(data.persona_rebuild)}`;
    if (data.warnings?.length) {
      msg += `<br><span class="muted">警告: ${data.warnings.map(escapeHtml).join("；")}</span>`;
    }
    if (!ok && !data.warnings?.length) {
      msg += `<br><span class="muted">未导入数据：请检查 Cookie 或尝试浏览器补洞。</span>`;
    }
    el.innerHTML = msg;
    loadIngestHealth();
    void loadLikes();
    return;
  } catch (err) {
    if (el) {
      el.className = "alert alert-error";
      el.textContent = err.message;
    }
  } finally {
    if (btn) {
      btn.textContent = prevText || "导入";
    }
    void loadIngestPreflight();
  }
}

let _recognitionPlatformFilter = "all";

function formatRecognitionDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso.slice(0, 10);
  const now = new Date();
  const sameDay = d.toDateString() === now.toDateString();
  if (sameDay) {
    return `今天 ${d.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" })}`;
  }
  return d.toLocaleDateString("zh-CN", { month: "short", day: "numeric" });
}

function renderRecognitionSummary(summary) {
  const el = document.getElementById("recognition-summary");
  if (!el) return;
  const chips = [];
  const platformLabels = { zhihu: "知乎", bilibili: "B站" };
  const actionLabels = {
    vote: "赞同",
    favorite: "收藏",
    like: "点赞",
    coin: "投币",
    comment: "评论",
    comment_like: "赞评论",
  };
  for (const [platform, actions] of Object.entries(summary || {})) {
    for (const [action, count] of Object.entries(actions || {})) {
      if (!count) continue;
      const pl = platformLabels[platform] || platform;
      const al = actionLabels[action] || action;
      chips.push(`<span class="recognition-stat">${escapeHtml(pl)} ${escapeHtml(al)} ${count}</span>`);
    }
  }
  if (!chips.length) {
    el.classList.add("hidden");
    el.innerHTML = "";
    return;
  }
  el.classList.remove("hidden");
  el.innerHTML = chips.join("");
}

function renderRecognitionFilters(summary, active) {
  const el = document.getElementById("recognition-filters");
  if (!el) return;
  const hasZhihu = Object.values(summary?.zhihu || {}).some((n) => n > 0);
  const hasBili = Object.values(summary?.bilibili || {}).some((n) => n > 0);
  if (!hasZhihu && !hasBili) {
    el.classList.add("hidden");
    el.innerHTML = "";
    return;
  }
  const mk = (id, label) =>
    `<button type="button" class="btn btn-sm btn-secondary recognition-filter-btn${active === id ? " active" : ""}" data-platform="${id}">${escapeHtml(label)}</button>`;
  el.classList.remove("hidden");
  el.innerHTML = [mk("all", "全部"), hasZhihu ? mk("zhihu", "知乎") : "", hasBili ? mk("bilibili", "B站") : ""]
    .filter(Boolean)
    .join("");
  el.querySelectorAll(".recognition-filter-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      _recognitionPlatformFilter = btn.getAttribute("data-platform") || "all";
      void loadLikes();
    });
  });
}

function renderRecognitionItem(r) {
  const title = escapeHtml((r.title || r.url || "未命名").slice(0, 120));
  const url = escapeHtml(r.url || "");
  const platform = escapeHtml(r.platform || "");
  const platformLabel = escapeHtml(r.platform_label || platform);
  const actionLabel = escapeHtml(r.action_label || r.action || "");
  const date = escapeHtml(formatRecognitionDate(r.created_at));
  const via = r.via
    ? ` · ${escapeHtml(r.via === "extension" ? "扩展" : r.via === "voteanswers_api" ? "赞同 API" : r.via)}`
    : "";
  const collection = r.collection ? `<span class="muted"> · 收藏夹 ${escapeHtml(r.collection)}</span>` : "";
  return `<li class="recognition-item" data-platform="${platform}">
    <div class="recognition-item-badges">
      <span class="recognition-badge recognition-badge--${platform}">${platformLabel}</span>
      <span class="recognition-badge recognition-badge--action">${actionLabel}</span>
    </div>
    <div class="recognition-item-body">
      <div class="recognition-item-title">${title}</div>
      <div class="recognition-item-meta">${date}${via}${collection}</div>
    </div>
    <div class="recognition-item-link">${url ? `<a href="${url}" target="_blank" rel="noopener">打开</a>` : ""}</div>
  </li>`;
}

function renderRecognitionList(rows, title) {
  if (!rows?.length) return "";
  const list = rows.map(renderRecognitionItem).join("");
  return `<h3 class="recognition-group-title">${escapeHtml(title)}</h3><ul class="recognition-list">${list}</ul>`;
}

async function loadLikes() {
  const el = document.getElementById("likes-list");
  if (!el) return;
  try {
    const data = await api("GET", "/api/ingest/likes");
    const filterRows = (rows) =>
      (rows || []).filter((r) =>
        _recognitionPlatformFilter === "all" ? true : r.platform === _recognitionPlatformFilter
      );
    const recent = filterRows(data.recent || data.rows);
    const inventory = filterRows(data.inventory || []);
    renderRecognitionSummary(data.summary || {});
    renderRecognitionFilters(data.summary || {}, _recognitionPlatformFilter);
    if (!(data.count > 0) && !recent.length && !inventory.length) {
      el.innerHTML = `<p class="muted">${escapeHtml(
        data.hint || "暂无行为认可。请先完成「完整同步」，并安装扩展以采集投币、评论等行为。"
      )}</p>`;
      return;
    }
    const total = data.count || 0;
    const head = `<p class="muted recognition-list-head">共 <strong>${total}</strong> 条（去重后展示近期互动与收藏库快照）</p>`;
    const hint = data.hint ? `<p class="muted recognition-hint">${escapeHtml(data.hint)}</p>` : "";
    const body =
      renderRecognitionList(recent, "近期互动（点赞 / 赞同 / 投币 / 评论）") +
      renderRecognitionList(inventory, "收藏库快照（长期偏好库，画像权重较低）");
    el.innerHTML = `${head}${hint}${body || "<p class='muted'>当前筛选下无记录。</p>"}`;
  } catch (err) {
    el.innerHTML = `<div class="alert alert-error">无法加载行为认可：${escapeHtml(err.message)}</div>`;
  }
}

/* 运行记录 */
let _runsRefreshTimer = null;
const _runsSelectedIds = new Set();
let _runsVisibleIds = [];

function initRuns() {
  void bootstrapSourceLabels();
  document.getElementById("btn-runs-refresh")?.addEventListener("click", () => loadRunsList());
  document.getElementById("runs-filter")?.addEventListener("change", () => loadRunsList());
  document.getElementById("runs-search")?.addEventListener("input", () => {
    clearTimeout(window._runsSearchTimer);
    window._runsSearchTimer = setTimeout(() => loadRunsList(), 250);
  });
  document.getElementById("btn-runs-cleanup-preview")?.addEventListener("click", () => runCleanup(true));
  document.getElementById("btn-runs-cleanup")?.addEventListener("click", () => runCleanup(false));
  document.getElementById("runs-select-all")?.addEventListener("change", (e) => {
    const checked = Boolean(e.target.checked);
    if (checked) {
      _runsVisibleIds.forEach((id) => _runsSelectedIds.add(id));
    } else {
      _runsVisibleIds.forEach((id) => _runsSelectedIds.delete(id));
    }
    syncRunsSelectionUi();
  });
  document.getElementById("btn-runs-clear-selection")?.addEventListener("click", () => {
    _runsSelectedIds.clear();
    syncRunsSelectionUi();
  });
  document.getElementById("btn-runs-batch-delete")?.addEventListener("click", () => {
    void batchDeleteRunRecords().catch((err) => {
      const el = document.getElementById("runs-list");
      el?.insertAdjacentHTML("afterbegin", `<div class="alert alert-error">${escapeHtml(err.message)}</div>`);
    });
  });
  loadRunsList();
}

function syncRunsSelectionUi() {
  const bar = document.getElementById("runs-batch-bar");
  const countEl = document.getElementById("runs-selected-count");
  const deleteBtn = document.getElementById("btn-runs-batch-delete");
  const selectAll = document.getElementById("runs-select-all");
  const count = _runsSelectedIds.size;
  if (countEl) countEl.textContent = `已选 ${count} 条`;
  if (deleteBtn) deleteBtn.disabled = count === 0;
  if (bar) bar.classList.toggle("hidden", count === 0);
  if (selectAll) {
    const visibleSelected = _runsVisibleIds.filter((id) => _runsSelectedIds.has(id)).length;
    selectAll.checked = _runsVisibleIds.length > 0 && visibleSelected === _runsVisibleIds.length;
    selectAll.indeterminate = visibleSelected > 0 && visibleSelected < _runsVisibleIds.length;
  }
  document.querySelectorAll(".runs-row-select").forEach((input) => {
    const id = input.getAttribute("data-run-id");
    if (!id) return;
    input.checked = _runsSelectedIds.has(id);
  });
}

async function batchDeleteRunRecords() {
  const ids = [..._runsSelectedIds];
  if (!ids.length) return;
  const deleteBtn = document.getElementById("btn-runs-batch-delete");
  if (deleteBtn?.disabled) return;
  const ok = window.confirm(
    `确定删除所选 ${ids.length} 条运行记录？\n将移除 ~/.osint/runs/ 下对应目录，不可恢复。`,
  );
  if (!ok) return;
  if (deleteBtn) deleteBtn.disabled = true;
  try {
    const data = await api("POST", "/api/runs/batch-delete", { run_ids: ids });
    const deleted = data.deleted || [];
    const errors = data.errors || [];
    _runsSelectedIds.clear();
    if (errors.length) {
      showToast(`已删除 ${deleted.length} 条，${errors.length} 条失败`, deleted.length ? "warn" : "error");
    } else {
      showToast(`已删除 ${deleted.length} 条运行记录`, "success");
    }
    await loadRunsList();
  } finally {
    syncRunsSelectionUi();
  }
}

async function deleteRunRecord(runId) {
  if (!runId) return;
  const ok = window.confirm(`确定删除运行记录 ${runId}？\n将移除 ~/.osint/runs/ 下该目录，不可恢复。`);
  if (!ok) return;
  await api("DELETE", `/api/runs/${encodeURIComponent(runId)}`);
  await loadRunsList();
}

async function runCleanup(dryRun) {
  const resultEl = document.getElementById("runs-cleanup-result");
  const older = parseInt(document.getElementById("cleanup-older-days")?.value, 10);
  const keep = parseInt(document.getElementById("cleanup-keep-latest")?.value, 10);
  const cleanupBody = {
    older_than_days: Number.isFinite(older) ? older : 30,
    keep_latest: Number.isFinite(keep) ? keep : 20,
    dry_run: dryRun,
  };
  if (!dryRun) {
    if (resultEl) resultEl.textContent = "正在预览…";
    try {
      const preview = await api("POST", "/api/runs/cleanup", { ...cleanupBody, dry_run: true });
      const toDelete = preview.deleted || [];
      if (!toDelete.length) {
        if (resultEl) resultEl.innerHTML = "<p class='muted'>没有符合清理条件的记录</p>";
        return;
      }
      const ok = confirm(`确定删除 ${toDelete.length} 条运行记录？此操作不可恢复。`);
      if (!ok) {
        if (resultEl) resultEl.textContent = "已取消删除";
        return;
      }
    } catch (err) {
      if (resultEl) resultEl.innerHTML = `<span class="status-fail">${escapeHtml(err.message)}</span>`;
      return;
    }
  }
  if (resultEl) resultEl.textContent = dryRun ? "正在预览…" : "正在删除…";
  try {
    const data = await api("POST", "/api/runs/cleanup", cleanupBody);
    const deleted = data.deleted || [];
    const skipped = data.skipped || [];
    const verb = dryRun ? "将删除" : "已删除";
    let html = `<p><strong>${verb} ${deleted.length} 条</strong>`;
    if (deleted.length) {
      html += `：${deleted.slice(0, 8).map((id) => escapeHtml(id)).join("、")}`;
      if (deleted.length > 8) html += ` 等 ${deleted.length} 条`;
    }
    html += `</p><p class="muted">跳过 ${skipped.length} 条（进行中或保留最近 ${keep} 条 / 未到期）</p>`;
    if (resultEl) resultEl.innerHTML = html;
    if (!dryRun && deleted.length) await loadRunsList();
  } catch (err) {
    if (resultEl) resultEl.innerHTML = `<span class="status-fail">${escapeHtml(err.message)}</span>`;
  }
}

function _runsFilterList(runs) {
  const status = document.getElementById("runs-filter")?.value || "";
  const q = (document.getElementById("runs-search")?.value || "").trim().toLowerCase();
  return runs.filter((r) => {
    if (status && (r.status || "") !== status) return false;
    if (q) {
      const hay = `${r.query || ""} ${r.run_id || ""}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
}

function _runListActions(r) {
  const st = r.status || "done";
  const parts = [];
  if (st === "running" || st === "interrupted") {
    parts.push(`<a href="/?run=${encodeURIComponent(r.run_id)}">${st === "running" ? "继续跟踪" : "查看部分结果"}</a>`);
  } else {
    parts.push(`<a href="/?run=${encodeURIComponent(r.run_id)}">打开结果</a>`);
  }
  parts.push(`<a href="/runs/${r.run_id}">详情</a>`);
  if (r.has_report) {
    parts.push(`<a href="/api/runs/${r.run_id}/report/download" download>导出报告</a>`);
  }
  if (st !== "running") {
    parts.push(`<button type="button" class="btn-link btn-delete-run" data-run-id="${escapeHtml(r.run_id)}">删除</button>`);
  }
  return parts.join(" · ");
}

async function loadRunsList() {
  const el = document.getElementById("runs-list");
  if (!el) return;
  el.innerHTML = "<p class='muted'>加载中…</p>";
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 45000);
  try {
    const res = await fetch(`/api/runs?limit=80`, { signal: controller.signal });
    clearTimeout(timeout);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || res.statusText || `HTTP ${res.status}`);
    const runs = _runsFilterList(data.runs || []);
    clearTimeout(_runsRefreshTimer);
    const hasRunning = (data.runs || []).some((r) => r.status === "running");
    if (hasRunning) {
      _runsRefreshTimer = setTimeout(() => loadRunsList(), 12000);
    }
    if (!runs.length) {
      _runsVisibleIds = [];
      syncRunsSelectionUi();
      el.innerHTML = renderEmptyStateRich("runs", "暂无匹配的运行记录", "完成一次搜罗后会出现；可调整上方筛选条件");
      return;
    }
    _runsVisibleIds = runs.map((r) => r.run_id).filter(Boolean);
    el.innerHTML = `<div class="ui-inset-group runs-list-group">${runs.map((r) => {
        const st = r.status || "done";
        const errCount = Number(r.source_error_count) || 0;
        const warnCount = Number(r.source_warning_count) || 0;
        const sub = st === "running" && r.phase_detail
          ? `${escapeHtml(r.phase || "")} — ${escapeHtml((r.phase_detail || "").slice(0, 80))}`
          : (errCount || warnCount
            ? [
              errCount ? `信源错误 ${errCount} 条` : "",
              warnCount ? `信源警告 ${warnCount} 条` : "",
            ].filter(Boolean).join(" · ")
            : "");
        const sources = formatSourceLabels(r.collect_sources || r.sources);
        const profileLine = r.profile ? `模式：${escapeHtml(profileLabel(r.profile))}` : "";
        const srcLine = sources ? `实采：${escapeHtml(sources)}` : "";
        const meta = [profileLine, srcLine, sub].filter(Boolean).join(" · ");
        const runId = r.run_id || "";
        const checked = _runsSelectedIds.has(runId) ? " checked" : "";
        const runningHint = st === "running" ? " title=\"进行中的任务删除前将先尝试取消\"" : "";
        return `<div class="ui-list-row runs-list-row">
          <label class="runs-row-check" aria-label="选择运行记录">
            <input type="checkbox" class="runs-row-select" data-run-id="${escapeHtml(runId)}"${checked}${runningHint}>
          </label>
          <div class="ui-list-row-main">
            <div class="ui-list-row-meta muted">${escapeHtml(formatRunTime(r.started_at))}</div>
            <a class="ui-list-row-title" href="/runs/${r.run_id}">${escapeHtml(r.query || "（无话题）")}</a>
            ${meta ? `<div class="ui-list-row-sub muted">${meta}</div>` : ""}
          </div>
          <div class="ui-list-row-side">
            <span class="run-status-pill ${runStatusClass(st)}">${escapeHtml(formatRunStatus(st))}</span>
            <span class="muted ui-list-row-sub">${r.item_count != null ? `${r.item_count} 条` : "—"}${r.has_report ? " · 有报告" : ""}</span>
            <span class="muted ui-list-row-sub">${escapeHtml(formatDurationSec(r.duration_sec))}</span>
          </div>
          <div class="ui-list-row-actions">${_runListActions(r)}</div>
        </div>`;
      }).join("")}</div>`;
    el.querySelectorAll(".runs-row-select").forEach((input) => {
      input.addEventListener("change", () => {
        const id = input.getAttribute("data-run-id");
        if (!id) return;
        if (input.checked) _runsSelectedIds.add(id);
        else _runsSelectedIds.delete(id);
        syncRunsSelectionUi();
      });
    });
    el.querySelectorAll(".btn-delete-run").forEach((btn) => {
      btn.addEventListener("click", () => {
        void deleteRunRecord(btn.getAttribute("data-run-id")).catch((err) => {
          el.insertAdjacentHTML("afterbegin", `<div class="alert alert-error">${escapeHtml(err.message)}</div>`);
        });
      });
    });
    syncRunsSelectionUi();
  } catch (err) {
    clearTimeout(timeout);
    const msg = err.name === "AbortError"
      ? "加载超时。可能有搜罗任务占用服务，请稍后点「刷新」，或先取消进行中的搜罗。"
      : err.message;
    el.innerHTML = `<div class="alert alert-error">${escapeHtml(msg)}</div>`;
  }
}

function initRunDetail(runId) {
  void bootstrapSourceLabels().then(() => loadRunDetail(runId));
  if (window.location.hash === "#report") {
    setTimeout(() => document.getElementById("run-report")?.scrollIntoView({ behavior: "smooth" }), 400);
  }
}

function _runDetailActions(runId, data) {
  const status = data.status || "unknown";
  const actions = document.getElementById("run-detail-actions");
  if (!actions) return;
  const btns = [];
  btns.push(`<a class="btn btn-sm" href="/?run=${encodeURIComponent(runId)}">在搜罗页打开</a>`);
  if (data.report || data.summary?.has_report) {
    btns.push(`<a class="btn btn-sm btn-secondary" href="/api/runs/${runId}/report/download" download>导出报告</a>`);
    btns.push(`<a class="btn btn-sm btn-secondary" href="#report">页内查看</a>`);
  }
  if (status === "running") {
    btns.push(`<button type="button" class="btn btn-sm btn-secondary" id="btn-run-cancel">取消任务</button>`);
  } else {
    btns.push(`<button type="button" class="btn btn-sm btn-secondary" id="btn-run-delete">删除记录</button>`);
  }
  btns.push(`<button type="button" class="btn btn-sm btn-ghost" id="btn-run-refresh">刷新</button>`);
  actions.innerHTML = btns.join(" ");
  document.getElementById("btn-run-refresh")?.addEventListener("click", () => loadRunDetail(runId));
  document.getElementById("btn-run-delete")?.addEventListener("click", async () => {
    try {
      await deleteRunRecord(runId);
      window.location.href = "/runs";
    } catch (err) {
      showToast(err.message || "删除失败", "error");
    }
  });
  document.getElementById("btn-run-cancel")?.addEventListener("click", async () => {
    try {
      await api("POST", `/api/search/${runId}/cancel`);
      await loadRunDetail(runId);
    } catch (err) {
      showToast(err.message || "取消失败", "error");
    }
  });
}

async function loadRunDetail(runId) {
  const el = document.getElementById("run-detail");
  if (!el) return;
  try {
    const data = await api("GET", `/api/runs/${runId}`);
    _runDetailActions(runId, data);
    const steps = data.steps || [];
    const status = data.status || "unknown";
    const progress = data.progress || {};
    const summary = data.summary || {};
    const sources = formatSourceLabels(summary.collect_sources || data.collect_sources || summary.sources || data.sources);
    let html = `<div class="ui-inset-group run-detail-sections"><div class="run-summary-card"><h2>概况</h2><dl class="run-meta-grid">`;
    html += `<dt>状态</dt><dd class="${runStatusClass(status)}">${escapeHtml(formatRunStatus(status))}</dd>`;
    html += `<dt>话题</dt><dd>${escapeHtml(data.query || summary.query || "—")}</dd>`;
    if (sources) html += `<dt>实采信源</dt><dd>${escapeHtml(sources)}</dd>`;
    if (summary.profile) html += `<dt>模式</dt><dd>${escapeHtml(profileLabel(summary.profile))}</dd>`;
    const errCount = Number(summary.source_error_count ?? data.source_error_count) || 0;
    const warnCount = Number(summary.source_warning_count ?? data.source_warning_count) || 0;
    if (errCount || warnCount) {
      const bits = [];
      if (errCount) bits.push(`信源错误 ${errCount} 条`);
      if (warnCount) bits.push(`信源警告 ${warnCount} 条`);
      html += `<dt>采集问题</dt><dd class="muted">${escapeHtml(bits.join(" · "))}</dd>`;
    }
    html += `<dt>开始</dt><dd>${escapeHtml(formatRunTime(summary.started_at || data.started_at))}</dd>`;
    if (summary.finished_at || data.finished_at) {
      html += `<dt>结束</dt><dd>${escapeHtml(formatRunTime(summary.finished_at || data.finished_at))}</dd>`;
    }
    html += `<dt>耗时</dt><dd>${escapeHtml(formatDurationSec(summary.duration_sec))}</dd>`;
    html += `<dt>结果</dt><dd>${summary.item_count != null ? `${summary.item_count} 条` : "—"}${summary.has_report ? " · 含情报报告" : ""}</dd>`;
    html += `</dl>`;
    if (data.error) html += `<p class="status-fail">${escapeHtml(data.error)}</p>`;
    const warnBlock = formatSourceWarningsHtml(data.source_warnings);
    const errBlock = formatSourceErrorsHtml(data.source_errors);
    if (warnBlock || errBlock) {
      html += `<div class="run-collect-issues">${warnBlock}${errBlock}</div>`;
    }
    if (progress.phase && status === "running") {
      html += `<p class="muted">当前：${escapeHtml(formatStepLabel(progress.phase))} — ${escapeHtml(progress.detail || "")}</p>`;
    }
    html += `</div>`;

    const req = data.request || summary.request || {};
    const reqBits = [];
    if (req.disabled_ai_steps?.length) {
      reqBits.push(`跳过 AI 步骤：${req.disabled_ai_steps.map((s) => formatStepLabel(s)).join("、")}`);
    }
    if (req.ai_instruct) reqBits.push(`指令：${req.ai_instruct}`);
    if (req.source_overrides?.force?.length) {
      reqBits.push(`强制必采：${req.source_overrides.force.map((s) => SOURCE_LABELS[s] || s).join("、")}`);
    }
    if (req.source_overrides?.block?.length) {
      reqBits.push(`强制排除：${req.source_overrides.block.map((s) => SOURCE_LABELS[s] || s).join("、")}`);
    }
    if (req.trace) reqBits.push("trace 已开启");
    if (reqBits.length) {
      html += `<div class="card"><h2>搜罗选项</h2><ul class="run-request-list">${reqBits
        .map((line) => `<li class="muted">${escapeHtml(line)}</li>`)
        .join("")}</ul></div>`;
    }
    const queries = data.queries_used || req.queries_used;
    if (Array.isArray(queries) && queries.length > 1) {
      html += `<div class="card"><h2>扩展查询</h2><div class="chip-group">${queries.map((q) =>
        `<span class="chip chip-readonly">${escapeHtml(q)}</span>`
      ).join("")}</div></div>`;
    }

    const qa = data.query_analysis || {};
    const plan = qa.source_plan || {};
    const routing = qa.source_routing || {};
    if (plan.reasoning_chain?.length || routing.score_breakdown) {
      html += `<div class="card"><h2>AI 信源规划</h2><div id="run-source-plan-mount"></div></div>`;
    }

    html += `<div class="card"><h2>Pipeline 步骤 <span class="muted">(${steps.length})</span></h2>`;
    if (steps.length) {
      html += `<table class="data-table"><thead><tr><th>步骤</th><th>状态</th><th>耗时</th><th>说明</th></tr></thead><tbody>${
        steps.map((s) => `<tr>
          <td><strong>${escapeHtml(formatStepLabel(s.step))}</strong><div class="muted" style="font-size:0.78rem">${escapeHtml(s.step || s._file || "")}</div></td>
          <td class="${s.status === "error" ? "status-fail" : s.status === "running" ? "status-warn" : ""}">${escapeHtml(s.status || "")}</td>
          <td>${s.duration_ms != null ? `${s.duration_ms}ms` : ""}</td>
          <td class="muted">${escapeHtml((s.issues || []).join("; ") || s.output_summary || s.input_summary || "")}</td>
        </tr>`).join("")
      }</tbody></table>`;
    } else {
      html += `<p class="muted">暂无步骤快照。任务可能刚开始、仍在长跑阶段，或曾被中断。请刷新或查看下方产出文件。</p>`;
    }
    html += `</div>`;

    if (data.report) {
      html += `<div class="card" id="report"><h2>情报报告</h2><div class="markdown-body" id="run-report"></div></div>`;
    }

    const artifacts = (data.artifacts || []).filter((a) => !/^(manifest|request|progress)\.json$/.test(a));
    if (artifacts.length) {
      const main = artifacts.filter((a) => /^(report\.md|query_analysis|source_plan|alias_discover|items_dedup)/.test(a) || a.endsWith(".md"));
      const rest = artifacts.filter((a) => !main.includes(a));
      html += `<div class="card"><h2>产出文件</h2>`;
      if (main.length) {
        html += `<p class="toolbar-label">主要</p><ul>${main.map((a) =>
          `<li><a href="/api/runs/${runId}/artifacts/${a}" target="_blank">${escapeHtml(a)}</a></li>`
        ).join("")}</ul>`;
      }
      if (rest.length) {
        html += `<details class="mt-1"><summary>全部文件 (${rest.length})</summary><ul>${rest.map((a) =>
          `<li><a href="/api/runs/${runId}/artifacts/${a}" target="_blank">${escapeHtml(a)}</a></li>`
        ).join("")}</ul></details>`;
      }
      html += `</div>`;
    }

    if (data.trace) {
      html += `<details class="card"><summary><h2 style="display:inline">Trace 日志</h2></summary><pre class="trace-log">${escapeHtml(data.trace)}</pre></details>`;
    }

    el.innerHTML = html;
    const planMount = document.getElementById("run-source-plan-mount");
    if (planMount) {
      planMount.innerHTML = buildSourcePlanInnerHtml(plan, routing);
    }
    if (data.report) renderMarkdown(document.getElementById("run-report"), data.report);

    if (status === "running") {
      clearTimeout(window._runDetailPoll);
      window._runDetailPoll = setTimeout(() => loadRunDetail(runId), 8000);
    }
  } catch (err) {
    el.innerHTML = `<div class="alert alert-error">${escapeHtml(err.message)}</div>`;
  }
}

/* AI 控制 */
function initAI() {
  loadAiStatusSummary();
  loadAiCallSummary();
  loadDirectives();
  loadPromptList();
  const tabs = document.querySelectorAll("#ai-tabs .tab, .tabs .tab");
  const panels = document.querySelectorAll(".tab-panel");
  tabs.forEach((tab, idx) => {
    const panelId = tab.dataset.panel;
    if (!tab.hasAttribute("role")) tab.setAttribute("role", "tab");
    if (panelId) tab.setAttribute("aria-controls", panelId);
    tab.setAttribute("tabindex", tab.classList.contains("active") ? "0" : "-1");
    tab.setAttribute("aria-selected", tab.classList.contains("active") ? "true" : "false");
    tab.addEventListener("click", () => activateAiTab(tab, tabs, panels));
    tab.addEventListener("keydown", (ev) => {
      if (ev.key !== "ArrowLeft" && ev.key !== "ArrowRight") return;
      ev.preventDefault();
      const next = ev.key === "ArrowRight" ? (idx + 1) % tabs.length : (idx - 1 + tabs.length) % tabs.length;
      activateAiTab(tabs[next], tabs, panels);
      tabs[next].focus();
    });
  });
  panels.forEach((panel) => {
    panel.setAttribute("role", "tabpanel");
    panel.setAttribute("aria-hidden", panel.classList.contains("active") ? "false" : "true");
  });
  document.getElementById("btn-save-directives")?.addEventListener("click", saveDirectives);
  document.getElementById("btn-save-prompt")?.addEventListener("click", savePrompt);
  document.getElementById("btn-reset-prompt")?.addEventListener("click", resetPrompt);
  document.getElementById("prompt-select")?.addEventListener("change", loadPrompt);
}

async function loadAiStatusSummary() {
  const el = document.getElementById("ai-status-summary");
  if (!el) return;
  try {
    const data = await api("GET", "/api/ai/status");
    const recent = data.recent_activity || {};
    el.innerHTML = `
      <div class="grid-2">
        <div>
          <div><strong>当前模型</strong></div>
          <div class="muted">${escapeHtml(data.provider || "")} · ${escapeHtml(data.model || "")}</div>
          <div class="muted">API Key ${data.api_key_configured ? "已配置" : "未配置"}</div>
        </div>
        <div>
          <div><strong>近期概况</strong></div>
          <div class="muted">最近 ${escapeHtml(String(recent.total_calls || 0))} 次调用，成功率 ${escapeHtml(String(Math.round((Number(recent.success_rate || 0) * 1000)) / 10))}%</div>
          <div class="muted">平均耗时 ${escapeHtml(String(recent.avg_duration_ms || 0))}ms</div>
        </div>
      </div>
      <div class="toggle-row mt-1">
        <span class="muted">启用步骤 ${escapeHtml(String(data.enabled_step_count || 0))}/${escapeHtml(String(data.total_step_count || 0))}</span>
        <span class="muted">Prompt 覆盖 ${escapeHtml(String(data.prompt_overrides || 0))}</span>
        <span class="muted">自动画像 ${escapeHtml(String(data.auto_persona_rebuild || ""))}</span>
      </div>
    `;
  } catch (err) {
    el.innerHTML = `<div class="alert alert-error">${escapeHtml(err.message || "无法加载 AI 状态")}</div>`;
  }
}

async function loadAiCallSummary() {
  const el = document.getElementById("ai-calls-summary");
  if (!el) return;
  try {
    const data = await api("GET", "/api/ai/calls?limit=12");
    const rows = data.calls || [];
    el.innerHTML = rows.length
      ? `<div class="ui-inset-group">${rows.map((call) => `
          <div class="ui-list-row">
            <div class="ui-list-row-main">
              <div class="ui-list-row-title">${escapeHtml(call.task || "unknown")} · ${escapeHtml(call.model || "")}</div>
              <p class="ui-list-row-sub muted">${escapeHtml(call.created_at || "")} · ${escapeHtml(String(call.duration_ms || 0))}ms · 输入 ${escapeHtml(String(call.prompt_chars || 0))} / 输出 ${escapeHtml(String(call.response_chars || 0))}</p>
            </div>
            <div class="ui-list-row-actions">
              <span class="source-badge ${call.success ? "source-web" : "source-bad"}">${call.success ? "成功" : "失败"}</span>
            </div>
          </div>
        `).join("")}</div>`
      : `<p class="muted">暂无 AI 调用记录。执行一次摘要、问答或搜罗后会在这里出现。</p>`;
  } catch (err) {
    el.innerHTML = `<div class="alert alert-error">${escapeHtml(err.message || "无法加载 AI 台账")}</div>`;
  }
}

function activateAiTab(tab, tabs, panels) {
  tabs.forEach((t) => {
    t.classList.remove("active");
    t.setAttribute("aria-selected", "false");
    t.setAttribute("tabindex", "-1");
  });
  panels.forEach((p) => {
    p.classList.remove("active");
    p.setAttribute("aria-hidden", "true");
  });
  tab.classList.add("active");
  tab.setAttribute("aria-selected", "true");
  tab.setAttribute("tabindex", "0");
  const panel = document.getElementById(tab.dataset.panel);
  if (panel) {
    panel.classList.add("active");
    panel.setAttribute("aria-hidden", "false");
  }
}

async function loadDirectives() {
  const el = document.getElementById("directives-editor");
  const summary = document.getElementById("hard-constraints");
  if (!el) return;
  try {
    const data = await api("GET", "/api/ai/directives");
    el.value = JSON.stringify(data, null, 2);
    if (summary) {
      const hc = data.hard_constraints;
      summary.textContent = hc
        ? `硬约束: ${JSON.stringify(hc)}`
        : "硬约束: （未设置）";
    }
  } catch (err) {
    el.value = err.message;
    if (summary) summary.textContent = "加载失败";
  }
}

async function saveDirectives() {
  try {
    const data = JSON.parse(document.getElementById("directives-editor").value);
    await api("PUT", "/api/ai/directives", { data });
    showToast("指令已保存", "success");
  } catch (err) { showToast(err.message, "error"); }
}

async function loadPromptList() {
  const sel = document.getElementById("prompt-select");
  if (!sel) return;
  try {
    const data = await api("GET", "/api/ai/prompts");
    sel.innerHTML = (data.prompts || []).map((p) =>
      `<option value="${escapeHtml(p.name)}">${escapeHtml(p.name)} (${escapeHtml(p.source)})</option>`
    ).join("");
    loadPrompt();
  } catch (err) {
    sel.innerHTML = `<option value="">加载失败</option>`;
    showToast(err.message, "error");
  }
}

async function loadPrompt() {
  const name = document.getElementById("prompt-select").value;
  const data = await api("GET", `/api/ai/prompts/${name}`);
  document.getElementById("prompt-editor").value = data.text;
  document.getElementById("prompt-source").textContent = `来源: ${data.source}`;
}

async function savePrompt() {
  const name = document.getElementById("prompt-select").value;
  const text = document.getElementById("prompt-editor").value;
  await api("PUT", `/api/ai/prompts/${name}`, { text });
  showToast("Prompt 已保存", "success");
  loadPromptList();
}

async function resetPrompt() {
  const name = document.getElementById("prompt-select").value;
  await api("POST", `/api/ai/prompts/${name}/reset`);
  showToast("已恢复内置 Prompt", "success");
  loadPromptList();
}

async function loadWatches() {
  const listEl = document.getElementById("watches-list");
  const countEl = document.getElementById("watches-count");
  if (!listEl) return;
  try {
    const data = await api("GET", "/api/watches");
    const watches = data.watches || [];
    if (countEl) countEl.textContent = watches.length ? `（${watches.length}）` : "";
    if (!watches.length) {
      listEl.innerHTML =
        "<p class='muted'>未配置监视。在 <code>~/.osint/config.yaml</code> 的 <code>watches</code> 段添加后刷新页面。</p>";
      return;
    }
    listEl.innerHTML = watches
      .map((w) => {
        const last = w.last_run_at ? ` · 上次 ${escapeHtml(formatRunTime(w.last_run_at))}` : "";
        const diff =
          w.last_new_count != null ? ` · 新增 ${Number(w.last_new_count) || 0} 条` : "";
        return `<div class="watch-row mb-1">
          <strong>${escapeHtml(w.id)}</strong> · ${escapeHtml(w.query || "")}
          <span class="muted"> · ${escapeHtml(w.schedule || "—")} · ${w.enabled ? "启用" : "停用"}${last}${diff}</span>
          <button type="button" class="btn btn-sm btn-secondary" data-watch-run="${escapeHtml(w.id)}">立即运行</button>
        </div>`;
      })
      .join("");
    listEl.querySelectorAll("[data-watch-run]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const watchId = btn.dataset.watchRun;
        if (!watchId) return;
        btn.disabled = true;
        try {
          const res = await api("POST", `/api/watches/${encodeURIComponent(watchId)}/run`);
          showToast(
            `监视已触发：新增 ${res.new_count ?? 0} 条 · run ${res.run_id || ""}`,
            "success",
          );
          void loadWatches();
        } catch (err) {
          showToast(err.message || "监视运行失败", "error");
        } finally {
          btn.disabled = false;
        }
      });
    });
  } catch (err) {
    listEl.textContent = `加载失败：${err.message}`;
  }
}

/* 设置 */
let tunableSettingsCache = { groups: [] };
let tunableSettingsEditingGroupId = null;

const TUNABLE_SECTION_ORDER = ["search", "ai", "knowledge"];
const TUNABLE_SECTION_META = {
  search: {
    title: "搜罗工作台",
    desc: "影响搜罗任务的速度、深度、站内限流和国际信源访问。",
  },
  ai: {
    title: "画像与 AI",
    desc: "影响画像注入、自动重建和与画像相关的 AI 行为。",
  },
  knowledge: {
    title: "知识库与云同步",
    desc: "影响 Markdown vault 输出和跨设备可用性。",
  },
};

function initSettings() {
  loadSetupWizard();
  initThemeSettings();
  loadApiKeysPanel();
  loadTunableSettingsPanel();
  loadDependenciesChecklist();
  loadOperationsRunbook();
  loadAuthStatus();
  loadPaths();
  document.getElementById("btn-refresh-auth")?.addEventListener("click", loadAuthStatus);
  document.getElementById("btn-sync-cookies")?.addEventListener("click", syncCookies);
  document.getElementById("btn-domain-lookup")?.addEventListener("click", lookupDomain);
  document.getElementById("btn-copy-edge-cdp")?.addEventListener("click", () => {
    const pre = document.getElementById("edge-cdp-cmd");
    if (!pre) return;
    const text = pre.textContent.replace(/&amp;/g, "&");
    navigator.clipboard.writeText(text).then(() => {
      const el = document.getElementById("sync-result");
      if (el) {
        el.className = "alert alert-success mt-1";
        el.textContent = "已复制 Edge 调试启动命令";
      }
    });
  });
  initTunableSettingsModal();
}

function renderTunableFieldInput(field) {
  const id = `tunable-field-${field.key.replace(/\./g, "-")}`;
  const desc = field.description
    ? `<p class="tunable-field-desc muted">${escapeHtml(field.description)}</p>`
    : "";
  if (field.type === "bool") {
    const checked = field.value ? " checked" : "";
    return `<div class="tunable-field" data-field-key="${escapeHtml(field.key)}">
      <label class="toggle-row"><input type="checkbox" id="${id}" data-field-key="${escapeHtml(field.key)}"${checked}> ${escapeHtml(field.label)}</label>
      ${desc}
    </div>`;
  }
  if (field.type === "select" && field.options?.length) {
    const opts = field.options
      .map((opt) => {
        const sel = String(opt.value) === String(field.value) ? " selected" : "";
        return `<option value="${escapeHtml(String(opt.value))}"${sel}>${escapeHtml(opt.label)}</option>`;
      })
      .join("");
    return `<div class="tunable-field" data-field-key="${escapeHtml(field.key)}">
      <label for="${id}">${escapeHtml(field.label)}</label>
      ${desc}
      <select id="${id}" data-field-key="${escapeHtml(field.key)}">${opts}</select>
    </div>`;
  }
  if (field.type === "text") {
    return `<div class="tunable-field" data-field-key="${escapeHtml(field.key)}">
      <label for="${id}">${escapeHtml(field.label)}</label>
      ${desc}
      <input type="text" id="${id}" data-field-key="${escapeHtml(field.key)}" value="${escapeHtml(String(field.value ?? ""))}" autocomplete="off" spellcheck="false">
    </div>`;
  }
  const inputType = field.type === "float" ? "number" : "number";
  const step = field.step != null ? ` step="${field.step}"` : field.type === "float" ? ' step="0.1"' : "";
  const min = field.min != null ? ` min="${field.min}"` : "";
  const max = field.max != null ? ` max="${field.max}"` : "";
  return `<div class="tunable-field" data-field-key="${escapeHtml(field.key)}">
    <label for="${id}">${escapeHtml(field.label)}</label>
    ${desc}
    <input type="${inputType}" id="${id}" data-field-key="${escapeHtml(field.key)}" value="${escapeHtml(String(field.value ?? ""))}"${step}${min}${max}>
  </div>`;
}

function openTunableSettingsGroup(groupId) {
  const group = (tunableSettingsCache.groups || []).find((g) => g.id === groupId);
  const dialog = document.getElementById("tunable-settings-modal");
  const titleEl = document.getElementById("tunable-settings-modal-title");
  const descEl = document.getElementById("tunable-settings-modal-desc");
  const fieldsEl = document.getElementById("tunable-settings-fields");
  const resultEl = document.getElementById("tunable-settings-result");
  if (!group || !dialog || !fieldsEl) return;
  tunableSettingsEditingGroupId = groupId;
  if (titleEl) titleEl.textContent = group.title || "调整参数";
  if (descEl) {
    const summary = group.summary ? `当前：${group.summary}` : "";
    descEl.textContent = [group.description || "", summary].filter(Boolean).join("  ");
  }
  if (resultEl) resultEl.textContent = "";
  let extraHtml = "";
  if (groupId === "source_network") {
    extraHtml = `<div class="tunable-intl-check mt-1">
      <button type="button" class="btn btn-sm btn-secondary" id="btn-intl-reachability-check">检测国际网络</button>
      <div id="intl-reachability-result" class="muted mt-1"></div>
    </div>`;
  }
  fieldsEl.innerHTML = (group.fields || []).map(renderTunableFieldInput).join("") + extraHtml;
  if (groupId === "source_network") {
    document.getElementById("btn-intl-reachability-check")?.addEventListener("click", runIntlReachabilityCheck);
  }
  if (!dialog.hasAttribute("aria-labelledby")) {
    dialog.setAttribute("aria-labelledby", "tunable-settings-modal-title");
  }
  dialog.showModal();
}

async function runIntlReachabilityCheck() {
  const resultEl = document.getElementById("intl-reachability-result");
  const btn = document.getElementById("btn-intl-reachability-check");
  if (!resultEl) return;
  if (btn) btn.disabled = true;
  resultEl.textContent = "检测中…";
  try {
    const data = await api("GET", "/api/health/intl-reachability?force=true");
    const ok = data.reachable || data.proxy_configured;
    const parts = [];
    if (data.proxy_configured) parts.push("已配置代理");
    if (data.github_ok) parts.push("GitHub 可达");
    if (data.detail) parts.push(data.detail);
    resultEl.innerHTML = `<span class="${ok ? "status-ok" : "status-fail"}">${escapeHtml(parts.join(" · ") || (ok ? "国际网络可用" : "国际网络不可用"))}</span>`;
  } catch (err) {
    resultEl.innerHTML = `<span class="status-fail">${escapeHtml(err.message)}</span>`;
  } finally {
    if (btn) btn.disabled = false;
  }
}

function validateTunableFormValues(groupId) {
  const group = (tunableSettingsCache.groups || []).find((g) => g.id === groupId);
  if (!group) return { ok: false, error: "未知参数组" };
  for (const field of group.fields || []) {
    const input = document.querySelector(
      `input[data-field-key="${CSS.escape(field.key)}"], select[data-field-key="${CSS.escape(field.key)}"]`,
    );
    if (!input) continue;
    if (field.type === "int") {
      const value = parseInt(input.value, 10);
      if (Number.isNaN(value)) return { ok: false, error: `${field.label} 需要整数` };
      if (field.min != null && value < field.min) return { ok: false, error: `${field.label} 不能小于 ${field.min}` };
      if (field.max != null && value > field.max) return { ok: false, error: `${field.label} 不能大于 ${field.max}` };
    } else if (field.type === "float") {
      const value = parseFloat(input.value);
      if (Number.isNaN(value)) return { ok: false, error: `${field.label} 需要数字` };
      if (field.min != null && value < field.min) return { ok: false, error: `${field.label} 不能小于 ${field.min}` };
      if (field.max != null && value > field.max) return { ok: false, error: `${field.label} 不能大于 ${field.max}` };
    }
  }
  return { ok: true };
}

function collectTunableFormValues(groupId) {
  const group = (tunableSettingsCache.groups || []).find((g) => g.id === groupId);
  if (!group) return {};
  const values = {};
  (group.fields || []).forEach((field) => {
    const input = document.querySelector(
      `input[data-field-key="${CSS.escape(field.key)}"], select[data-field-key="${CSS.escape(field.key)}"]`,
    );
    if (!input) return;
    if (field.type === "bool") {
      values[field.key] = input.checked;
    } else if (field.type === "int") {
      values[field.key] = parseInt(input.value, 10);
    } else if (field.type === "float") {
      values[field.key] = parseFloat(input.value);
    } else if (field.type === "text") {
      values[field.key] = input.value;
    } else {
      values[field.key] = input.value;
    }
  });
  return values;
}

async function loadTunableSettingsPanel() {
  const el = document.getElementById("tunables-panel");
  if (!el) return;
  try {
    const data = await api("GET", "/api/config/tunables");
    tunableSettingsCache = data;
    const groups = data.groups || [];
    if (!groups.length) {
      el.innerHTML = "<p class=\"muted\">暂无可调参数。</p>";
      return;
    }
    const sectionMap = {};
    groups.forEach((group) => {
      const section = group.id === "knowledge_cloud"
        ? "knowledge"
        : group.id === "persona_ai"
          ? "ai"
          : "search";
      if (!sectionMap[section]) sectionMap[section] = [];
      sectionMap[section].push(group);
    });
    el.innerHTML = TUNABLE_SECTION_ORDER
      .filter((section) => (sectionMap[section] || []).length)
      .map((section) => {
        const meta = TUNABLE_SECTION_META[section] || { title: section, desc: "" };
        const cards = (sectionMap[section] || [])
          .map(
            (group) => `<section class="tunable-card">
              <div class="tunable-card-head">
                <div class="tunable-card-title-wrap">
                  <strong>${escapeHtml(group.title)}</strong>
                  <div class="tunable-group-summary muted">${escapeHtml(group.summary || "")}</div>
                </div>
                <button type="button" class="btn btn-sm btn-secondary btn-edit-tunable" data-tunable-group="${escapeHtml(group.id)}">调整</button>
              </div>
              <p class="tunable-card-desc muted">${escapeHtml(group.description || "")}</p>
            </section>`,
          )
          .join("");
        return `<section class="tunable-section">
          <div class="tunable-section-head">
            <h3>${escapeHtml(meta.title)}</h3>
            <p class="muted">${escapeHtml(meta.desc || "")}</p>
          </div>
          <div class="tunable-card-grid">${cards}</div>
        </section>`;
      })
      .join("");
    el.querySelectorAll(".btn-edit-tunable").forEach((btn) => {
      btn.addEventListener("click", () => openTunableSettingsGroup(btn.dataset.tunableGroup));
    });
  } catch (err) {
    el.textContent = err.message;
  }
}

function initTunableSettingsModal() {
  const dialog = document.getElementById("tunable-settings-modal");
  if (!dialog) return;
  const form = dialog.querySelector("form");
  form?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const resultEl = document.getElementById("tunable-settings-result");
    const groupId = tunableSettingsEditingGroupId;
    if (!groupId) return;
    const validation = validateTunableFormValues(groupId);
    if (!validation.ok) {
      if (resultEl) resultEl.innerHTML = `<span class="status-fail">${escapeHtml(validation.error)}</span>`;
      return;
    }
    const values = collectTunableFormValues(groupId);
    if (resultEl) resultEl.textContent = "保存中…";
    try {
      const data = await api("PATCH", "/api/config/tunables", { values });
      tunableSettingsCache = { groups: data.groups || [] };
      if (resultEl) {
        resultEl.innerHTML = `<span class="status-ok">已保存到 ${escapeHtml(data.config_path || "本机配置")}</span>`;
      }
      showToast("运行参数已更新", "success");
      await loadTunableSettingsPanel();
      setTimeout(() => dialog.close(), 400);
    } catch (err) {
      if (resultEl) {
        resultEl.innerHTML = `<span class="status-fail">${escapeHtml(err.message)}</span>`;
      }
    }
  });
  dialog.querySelector('button[value="cancel"]')?.addEventListener("click", () => dialog.close());
}

async function loadApiKeysPanel() {
  const el = document.getElementById("api-keys-panel");
  if (!el) return;
  try {
    const data = await api("GET", "/api/config/secrets");
    const rows = (data.items || []).map((item) => {
      const status = item.configured
        ? `<span class="status-ok">已配置</span> · 来源 ${escapeHtml(item.source)}${item.last4 ? ` · …${escapeHtml(item.last4)}` : ""}`
        : `<span class="status-fail">未配置</span>`;
      return `<div class="api-key-row" data-secret-id="${escapeHtml(item.id)}">
        <div class="api-key-head">
          <strong>${escapeHtml(item.label)}</strong>
          <span class="muted">${status}</span>
        </div>
        <p class="muted api-key-desc">${escapeHtml(item.description || "")}</p>
        <div class="api-key-form">
          <input type="password" class="api-key-input" autocomplete="off" placeholder="粘贴 ${escapeHtml(item.env_var)}（留空不修改）" data-env="${escapeHtml(item.env_var)}">
          <button type="button" class="btn btn-sm btn-save-secret">保存</button>
          <button type="button" class="btn btn-sm btn-test-secret">测试连接</button>
        </div>
        <div class="api-key-result muted"></div>
      </div>`;
    }).join("");
    el.innerHTML = rows || "<p class=\"muted\">暂无需要配置的 API 密钥。</p>";
    el.querySelectorAll(".btn-save-secret").forEach((btn) => {
      btn.addEventListener("click", () => saveApiSecret(btn.closest(".api-key-row")));
    });
    el.querySelectorAll(".btn-test-secret").forEach((btn) => {
      btn.addEventListener("click", () => testApiSecret(btn.closest(".api-key-row")));
    });
  } catch (err) {
    el.textContent = err.message;
  }
}

async function saveApiSecret(row) {
  if (!row) return;
  const id = row.dataset.secretId;
  const input = row.querySelector(".api-key-input");
  const resultEl = row.querySelector(".api-key-result");
  const value = (input?.value || "").trim();
  if (!value) {
    resultEl.innerHTML = `<span class="status-fail">请输入密钥后再保存</span>`;
    return;
  }
  resultEl.textContent = "保存中…";
  try {
    const data = await api("POST", `/api/config/secrets/${encodeURIComponent(id)}`, { value });
    input.value = "";
    const probe = data.probe || {};
    const probeText = probe.detail ? ` · 探针：${probe.detail}` : "";
    resultEl.innerHTML = `<span class="${probe.ok !== false ? "status-ok" : "status-fail"}">已保存到本机配置${escapeHtml(probeText)}</span>`;
    loadApiKeysPanel();
    loadDependenciesChecklist();
    loadAuthStatus();
  } catch (err) {
    resultEl.innerHTML = `<span class="status-fail">${escapeHtml(err.message)}</span>`;
  }
}

async function testApiSecret(row) {
  if (!row) return;
  const id = row.dataset.secretId;
  const resultEl = row.querySelector(".api-key-result");
  resultEl.textContent = "测试中…";
  try {
    const input = row.querySelector(".api-key-input");
    const pending = (input?.value || "").trim();
    if (pending) {
      await api("POST", `/api/config/secrets/${encodeURIComponent(id)}`, { value: pending });
      input.value = "";
      loadApiKeysPanel();
    }
    const data = await api("POST", `/api/config/secrets/${encodeURIComponent(id)}/test`, {});
    resultEl.innerHTML = `<span class="${data.ok ? "status-ok" : "status-fail"}">${escapeHtml(data.detail || (data.ok ? "连接正常" : "连接失败"))}</span>`;
    loadAuthStatus();
    loadDependenciesChecklist();
  } catch (err) {
    resultEl.innerHTML = `<span class="status-fail">${escapeHtml(err.message)}</span>`;
  }
}

function renderDepItem(item) {
  const statusClass = item.ok ? "ok" : "fail";
  const statusText = item.ok ? "就绪" : "待配置";
  const forLine = item.required_for?.length
    ? `<div class="dep-meta">影响：${item.required_for.map(escapeHtml).join("、")}</div>`
    : "";
  let actions = "";
  if (!item.ok && item.action === "install_playwright") {
    actions = `<div class="dep-actions"><button type="button" class="btn btn-sm btn-install-playwright">一键安装 Playwright</button></div>`;
  } else if (!item.ok && item.action === "sync_cookies") {
    actions = `<div class="dep-actions"><button type="button" class="btn btn-sm btn-sync-cookies-inline">同步 Cookie</button></div>`;
  }
  return `<li class="dep-item ${statusClass}">
    <div class="dep-head">
      <span class="dep-title">${escapeHtml(item.label)}</span>
      <span class="${item.ok ? "status-ok" : "status-fail"}">${statusText}</span>
    </div>
    <div class="dep-meta">${escapeHtml(item.detail || "")}</div>
    ${forLine}
    ${item.hint ? `<div class="dep-hint">${escapeHtml(item.hint)}</div>` : ""}
    ${actions}
  </li>`;
}

async function pollPlaywrightInstall(jobId, resultEl) {
  const progressWrap = document.createElement("div");
  progressWrap.className = "playwright-install-progress";
  resultEl.innerHTML = "";
  resultEl.appendChild(progressWrap);
  const progressUi = mountJobProgress(progressWrap, {
    labelFn: (name) =>
      ({ pip: "pip 安装", playwright: "Edge 驱动", done: "完成" }[name] || name),
  });
  for (let i = 0; i < 120; i += 1) {
    await new Promise((r) => setTimeout(r, 1500));
    const job = await api("GET", `/api/setup/install-playwright/${jobId}`);
    if (job.progress) progressUi.update(job.progress);
    const logTail = (job.log || []).slice(-2).map(escapeHtml).join("<br>");
    if (logTail && progressWrap.querySelector(".search-progress-detail")) {
      const detailEl = progressWrap.querySelector(".search-progress-detail");
      if (detailEl && !job.progress?.detail) detailEl.textContent = logTail.replace(/<[^>]+>/g, " ");
    }
    if (job.status === "running") continue;
    progressUi.stop();
    if (job.status === "done") {
      resultEl.innerHTML = `<div class="alert alert-success">Playwright 安装完成。请重新搜罗或同步 Cookie 测试。</div>`;
      loadDependenciesChecklist();
      loadAuthStatus();
      return;
    }
    resultEl.innerHTML = `<div class="alert alert-error">${escapeHtml(job.error || "安装失败")}</div>`;
    return;
  }
  progressUi.stop();
  resultEl.innerHTML = `<div class="alert alert-error">安装超时（>3 分钟），请查看 Web 启动窗口或手动运行 scripts/install-browser-sync.ps1</div>`;
}

async function installPlaywrightFromSettings(resultEl) {
  resultEl.innerHTML = `<div class="alert alert-warn">正在安装 Playwright（pip + Edge 驱动），约 1–3 分钟…</div>`;
  const start = await api("POST", "/api/setup/install-playwright", {});
  if (!start.job_id) throw new Error("未返回 job_id");
  await pollPlaywrightInstall(start.job_id, resultEl);
}

async function loadDependenciesChecklist() {
  const listEl = document.getElementById("deps-checklist");
  const actionsEl = document.getElementById("deps-actions");
  if (!listEl) return;
  try {
    const data = await api("GET", "/api/setup/dependencies");
    const blockers = (data.blockers || []).filter(Boolean);
    const summary = blockers.length
      ? `<div class="alert alert-warn mb-1">${blockers.map(escapeHtml).join("<br>")}</div>`
      : `<div class="alert alert-success mb-1">核心环境就绪，可开始搜罗（个别来源仍可能需要 Cookie）。</div>`;
    listEl.innerHTML = `${summary}<ul class="dep-list">${(data.items || []).map(renderDepItem).join("")}</ul>`;
    if (actionsEl) {
      actionsEl.innerHTML = `<div id="playwright-install-result"></div>`;
    }
    listEl.querySelectorAll(".btn-install-playwright").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const resultEl = document.getElementById("playwright-install-result") || actionsEl;
        try {
          await installPlaywrightFromSettings(resultEl);
        } catch (err) {
          resultEl.innerHTML = `<div class="alert alert-error">${escapeHtml(err.message)}</div>`;
        }
      });
    });
    listEl.querySelectorAll(".btn-sync-cookies-inline").forEach((btn) => {
      btn.addEventListener("click", syncCookies);
    });
  } catch (err) {
    listEl.textContent = err.message;
  }
}

async function loadOperationsRunbook() {
  const el = document.getElementById("ops-runbook");
  if (!el) return;
  try {
    const data = await api("GET", "/api/setup/operations");
    const steps = (data.recommended || []).map((s) => {
      const parts = [];
      if (s.cli) parts.push(`CLI: <code>${escapeHtml(s.cli)}</code>`);
      if (s.web) parts.push(escapeHtml(s.web));
      if (s.note) parts.push(`<span class="muted">${escapeHtml(s.note)}</span>`);
      return `<li><strong>${s.step}. ${escapeHtml(s.title)}</strong> — ${parts.join(" · ")}</li>`;
    }).join("");
    const tagline = data.tagline ? `<p class="muted">${escapeHtml(data.tagline)}</p>` : "";
    el.innerHTML = `${tagline}<ol class="install-steps">${steps}</ol>`;
  } catch (err) {
    el.textContent = err.message;
  }
}

async function loadAuthStatus() {
  const el = document.getElementById("auth-status");
  if (!el) return;
  el.innerHTML = "<p class='muted'>检测中…</p>";
  try {
    const data = await api("GET", "/api/auth/status?live_probe=1", null, { timeoutMs: 25000 });
    el.innerHTML = `<table class="table"><thead><tr><th>项目</th><th>状态</th><th>说明</th><th>操作</th></tr></thead><tbody>${
      data.items.map((i) => {
        const fixKey = (i.key || i.name || "").toLowerCase();
        const fixHref = AUTH_FIX_LINKS[fixKey] || "/settings";
        const action = i.ok
          ? '<span class="muted">—</span>'
          : `<a href="${fixHref}">去修复</a>`;
        return `<tr><td>${escapeHtml(i.name)}</td>
        <td class="${i.ok ? "status-ok" : "status-fail"}">${i.ok ? "通过" : "未通过"}</td>
        <td>${escapeHtml(i.detail || "")}</td>
        <td>${action}</td></tr>`;
      }).join("")
    }</tbody></table>`;
  } catch (err) {
    el.innerHTML = `<div class="alert alert-error">${escapeHtml(err.message)}</div>`;
  }
}

async function loadPaths() {
  const el = document.getElementById("paths-info");
  if (!el) return;
  try {
    const data = await api("GET", "/api/auth/paths");
    el.innerHTML = `<ul>
    <li>${escapeHtml(data.api_key_hint)}</li>
    <li>Cookie: ${escapeHtml(data.cookies_dir)}</li>
    <li>Data: ${escapeHtml(data.data_dir)}</li>
    <li>Directives: ${escapeHtml(data.directives_path)}</li>
  </ul>`;
  } catch (err) {
    el.innerHTML = `<div class="alert alert-error">${escapeHtml(err.message)}</div>`;
  }
}

async function syncCookies() {
  const el = document.getElementById("sync-result");
  el.textContent = "同步中…";
  try {
    const data = await api("POST", "/api/auth/sync-cookies", { browser: "edge" });
    el.className = "alert alert-success";
    const synced = (data.domains_synced || []).join(", ") || "无";
    if (data.errors?.length) {
      el.className = "alert alert-error";
      const hint = (data.errors.join("; ") || "").toLowerCase().includes("appbound")
        ? "请改用扩展弹窗「从浏览器同步 Cookie」（推荐）；只有磁盘读取确实必须时，再以管理员运行 sync-cookies-admin.bat"
        : "请先双击 启动情报台.bat 启动 Web，或使用扩展同步 Cookie";
      el.textContent = `同步失败: ${data.errors.join("; ")}。${hint}`;
    } else if (!data.domains_synced?.length) {
      el.className = "alert alert-error";
      el.textContent = "未同步到任何域名。请先完全关闭 Edge，再点同步。";
    } else {
      el.textContent = `已同步: ${synced}`;
    }
    loadAuthStatus();
    loadDependenciesChecklist();
  } catch (err) {
    el.className = "alert alert-error";
    el.textContent = err.message;
  }
}

async function lookupDomain() {
  const domain = document.getElementById("domain-input").value.trim();
  const el = document.getElementById("domain-result");
  if (!domain) return;
  try {
    const data = await api("GET", `/api/tools/domain/${encodeURIComponent(domain)}`);
    el.innerHTML = `<pre>${escapeHtml(JSON.stringify(data, null, 2))}</pre>`;
  } catch (err) {
    el.textContent = err.message;
  }
}
