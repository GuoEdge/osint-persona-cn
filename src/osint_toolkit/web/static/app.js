/* 全局工具 / Global utilities */

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function renderMarkdown(el, text) {
  if (!el || !text) return;
  if (typeof marked !== "undefined") {
    el.innerHTML = marked.parse(text);
  } else {
    el.textContent = text;
  }
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

function itemSectionFlags(item, sim) {
  const flags = [];
  if (item.summary || item.key_points?.length) flags.push("摘要");
  if (item.layers?.comments_summary) flags.push("观点");
  const raw = (item.content || item.layers?.subtitle?.text || "").trim();
  if (raw) flags.push("原文");
  if (item.layers?.comments?.length) flags.push(`热评 ${item.layers.comments.length}`);
  if (sim && !sim.raw) flags.push("模拟");
  return flags;
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

function bindResultsToolbar(container) {
  const expandBtn = container.querySelector("[data-expand-all]");
  const collapseBtn = container.querySelector("[data-collapse-all]");
  const cardsHost = container.querySelector(".item-card-list");
  if (!cardsHost) return;
  const setAll = (expanded) => {
    cardsHost.querySelectorAll(".item-card").forEach((card) => {
      card.classList.toggle("is-expanded", expanded);
      card.classList.toggle("is-collapsed", !expanded);
      const header = card.querySelector(".item-card-header");
      if (header) header.setAttribute("aria-expanded", expanded ? "true" : "false");
    });
  };
  expandBtn?.addEventListener("click", () => setAll(true));
  collapseBtn?.addEventListener("click", () => setAll(false));
}

function renderResultsToolbar(count) {
  return `<div class="results-toolbar">
    <span class="muted results-toolbar-count">${count} 条结果 · 默认收起，点击标题展开</span>
    <div class="results-toolbar-actions">
      <button type="button" class="btn btn-sm btn-ghost" data-expand-all>全部展开</button>
      <button type="button" class="btn btn-sm btn-ghost" data-collapse-all>全部收起</button>
    </div>
  </div>`;
}

function formatCommentsSection(comments) {
  const rows = comments
    .slice(0, 10)
    .map(
      (c) => `<div class="comment-row">
      <div class="comment-meta">${escapeHtml(c.author || "匿名")} · 👍 ${Number(c.likes) || 0}</div>
      <div class="comment-text">${escapeHtml(c.content || "")}</div>
    </div>`
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
  return `<p class="muted section-hint">B 站简介通常只有一句；亲测讨论多在评论区或口播字幕。请确认已勾选「挖掘 B 站热评」并在<a href="/settings">设置</a>同步 B 站 Cookie 后重试。</p>`;
}

function hydrateItemCards(container, items) {
  const byId = Object.fromEntries(items.map((i) => [i.id, i]));
  container.querySelectorAll(".item-card[data-item-id]").forEach((card) => {
    const item = byId[card.dataset.itemId];
    if (!item) return;
    const raw = card.querySelector(".raw-body");
    const rawText = (item.content || item.layers?.subtitle?.text || "").trim();
    if (raw && rawText) renderMarkdown(raw, rawText);
    const summary = card.querySelector(".summary-body");
    if (summary && item.summary) renderMarkdown(summary, item.summary);
    const cs = card.querySelector(".comments-summary-body");
    if (cs && item.layers?.comments_summary) renderMarkdown(cs, item.layers.comments_summary);
  });
}

async function api(method, url, body) {
  const opts = { method, headers: { "Content-Type": "application/json" } };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(url, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || res.statusText);
  return data;
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
  bilibili_favorite: "B站收藏",
  bilibili_watch: "B站观看",
  bilibili_comment_post: "B站发评",
  bilibili_comment_like: "B站评论赞",
  zhihu_vote: "知乎赞同",
  zhihu_favorite: "知乎收藏",
  zhihu_browse: "知乎浏览",
  extension_flush: "扩展上报",
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
    const ext = await api("GET", "/api/extension/status");
    parts.push(
      ext.connected
        ? "扩展已连接"
        : '<a href="/ingest#extension">扩展未连接</a>',
    );
  } catch (_) {
    parts.push("Web 未就绪");
  }
  try {
    const jobs = await api("GET", "/api/jobs/active");
    const running = jobs.jobs || [];
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
  } catch (_) {}
  try {
    const setup = await api("GET", "/api/setup/status");
    const steps = setup.steps || [];
    const done = steps.filter((s) => s.done).length;
    if (!setup.ready && !setup.dismissed) {
      parts.push(`<a href="/settings">入门 ${done}/${steps.length}</a>`);
    }
  } catch (_) {}
  if (!parts.length) {
    bar.classList.add("hidden");
    return;
  }
  bar.innerHTML = parts.join(" · ");
  bar.classList.remove("hidden");
}

async function initGlobalSidebar() {
  const extChip = document.getElementById("sidebar-extension-chip");
  if (extChip) {
    try {
      const data = await api("GET", "/api/extension/status");
      if (data.connected) {
        extChip.textContent = `扩展 ● 已连接`;
        extChip.classList.add("ok");
      } else {
        extChip.innerHTML = `扩展 ○ 未连接 · <a href="/ingest#extension">安装</a>`;
        extChip.classList.add("warn");
      }
    } catch (_) {
      extChip.textContent = "扩展状态未知";
    }
  }
  const setupChip = document.getElementById("sidebar-setup-chip");
  if (setupChip) {
    try {
      const data = await api("GET", "/api/setup/status");
      if (data.ready || data.dismissed) {
        setupChip.classList.add("hidden");
      } else {
        const done = (data.steps || []).filter((s) => s.done).length;
        const total = (data.steps || []).length;
        setupChip.classList.remove("hidden");
        setupChip.innerHTML = `入门 <a href="/ingest">${done}/${total}</a>`;
      }
    } catch (_) {}
  }
  pollActiveJobs();
  setInterval(() => {
    pollActiveJobs();
    void refreshMobileStatusBar();
  }, 5000);
  void refreshMobileStatusBar();
}

function switchWorkspacePanel(panel) {
  const layout = document.querySelector(".results-layout");
  const tabs = document.querySelector(".workspace-panel-tabs");
  if (!layout || !tabs) return;
  const isNarrow = window.matchMedia("(max-width: 960px)").matches;
  if (!isNarrow) {
    layout.classList.remove("panel-results", "panel-report", "panel-research");
    return;
  }
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
}

function initWorkspacePanelTabs() {
  const tabs = document.querySelector(".workspace-panel-tabs");
  const layout = document.querySelector(".results-layout");
  if (!tabs || !layout) return;
  const mq = window.matchMedia("(max-width: 960px)");

  tabs.querySelectorAll(".workspace-panel-tab").forEach((btn) => {
    btn.addEventListener("click", () => switchWorkspacePanel(btn.dataset.panel));
  });

  function onBreakpointChange() {
    if (mq.matches) {
      let saved = "results";
      try {
        saved = localStorage.getItem("workspacePanel") || "results";
      } catch (_) {}
      switchWorkspacePanel(saved);
    } else {
      layout.classList.remove("panel-results", "panel-report", "panel-research");
    }
  }

  mq.addEventListener("change", onBreakpointChange);
  onBreakpointChange();
}

const workspaceSession = {
  treeId: sessionStorage.getItem("researchTreeId") || null,
  parentNodeId: null,
  activeRunId: sessionStorage.getItem("activeSearchRunId") || null,
  forkFromRunId: null,
  currentRunId: null,
  currentTree: null,
};

const RUN_STATUS_LABELS = {
  running: "进行中",
  done: "已完成",
  error: "失败",
  cancelled: "已取消",
  interrupted: "已中断",
  unknown: "未知",
};

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
  workspaceSession.currentRunId = runId || workspaceSession.currentRunId;
  if (runId) sessionStorage.setItem("activeSearchRunId", runId);
  else sessionStorage.removeItem("activeSearchRunId");
}

function setResearchTreeId(treeId) {
  workspaceSession.treeId = treeId || null;
  if (treeId) sessionStorage.setItem("researchTreeId", treeId);
  else sessionStorage.removeItem("researchTreeId");
}

async function pollActiveJobs() {
  const chip = document.getElementById("sidebar-active-jobs");
  if (!chip) return;
  try {
    const data = await api("GET", "/api/jobs/active");
    const jobs = data.jobs || [];
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
  for (let i = 0; i < 360; i += 1) {
    await new Promise((r) => setTimeout(r, 2000));
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
          if (data.items?.length) {
            await renderSearchResults(data, resultsEl, reportEl, runId);
            prependResultsBanner(resultsEl, "warn", data.error || "任务已中断，以下为已落盘部分结果");
          } else {
            resultsEl.innerHTML = `<div class="alert alert-warn">${escapeHtml(data.error || "任务已中断")}</div>`;
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
      if (err.message && !String(err.message).includes("404")) break;
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
  setSearchBusy(true);
  switchWorkspacePanel("results");
  resultsEl.innerHTML = "";
  const progressUi = mountSearchProgress(resultsEl);
  progressUi.setRunId(runId);
  stepsEl.innerHTML = "<span class='step-pill active'>恢复跟踪…</span>";
  if (runLink) {
    runLink.href = `/runs/${runId}`;
    runLink.classList.remove("hidden");
    runLink.textContent = "查看运行记录";
  }
  setActiveSearchRunId(runId);
  try {
    const data = await api("GET", `/api/search/${runId}`);
    if (data.status === "done" || data.status === "interrupted") {
      finishSearchRun(progressUi, async () => {
        if (data.items?.length) {
          await renderSearchResults(data, resultsEl, reportEl, runId);
          if (data.status === "interrupted") {
            prependResultsBanner(resultsEl, "warn", data.error || "任务已中断，以下为已落盘部分结果");
          }
        } else if (data.status === "interrupted") {
          resultsEl.innerHTML = `<div class="alert alert-warn">${escapeHtml(data.error || "任务已中断，以下为已落盘部分结果")}</div>`;
        }
      });
      setActiveSearchRunId(null);
      return;
    }
    if (data.status === "cancelled" || data.status === "error") {
      finishSearchRun(progressUi, () => {
        resultsEl.innerHTML = `<div class="alert alert-error">${escapeHtml(data.error || data.detail || "搜罗失败")}</div>`;
      });
      setActiveSearchRunId(null);
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
    return;
  }
  el.classList.remove("hidden");
  const kindLabel = RESEARCH_KIND_LABELS[node.kind] || node.kind;
  el.innerHTML = `<div class="research-node-detail-inner">
    <strong>${escapeHtml(node.title || kindLabel)}</strong>
    <p class="research-node-payload">${escapeHtml(node.payload)}</p>
  </div>`;
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
  if (!panel || !workspaceSession.treeId) return;
  clearResearchFeedback();
  try {
    const data = await api("GET", `/api/research/trees/${workspaceSession.treeId}`);
    const tree = data.tree;
    workspaceSession.currentTree = tree;
    panel.innerHTML = buildResearchTreeHtml(tree, selectedNodeId);
    const selectedNode = selectedNodeId ? findResearchNode(tree, selectedNodeId) : null;
    showResearchNodeDetail(selectedNode);
    panel.querySelectorAll(".research-tree-node").forEach((el) => {
      el.addEventListener("click", () => {
        const runId = el.dataset.runId;
        const nodeId = el.dataset.nodeId;
        workspaceSession.parentNodeId = nodeId;
        const node = findResearchNode(workspaceSession.currentTree, nodeId);
        refreshResearchTree(nodeId);
        showResearchNodeDetail(node);
        if (runId) void loadRunIntoWorkspace(runId);
      });
    });
    if (actions) {
      const runId = workspaceSession.currentRunId || "";
      actions.innerHTML = `
        <button type="button" class="btn btn-sm btn-secondary" id="btn-research-note" title="在当前选中节点下添加笔记">添加笔记</button>
        <button type="button" class="btn btn-sm btn-secondary" id="btn-research-fork" ${runId ? "" : "disabled"} title="继承上轮报告与反馈，细化关键词再搜罗">分叉深挖</button>
        <button type="button" class="btn btn-sm btn-secondary" id="btn-research-insight" ${runId && workspaceSession.treeId ? "" : "disabled"} title="AI 归纳本轮要点">归纳要点</button>
        <button type="button" class="btn btn-sm btn-ghost" id="btn-research-suggest" ${runId ? "" : "disabled"} title="生成后续搜罗建议">建议查询</button>`;
      document.getElementById("btn-research-note")?.addEventListener("click", () => toggleResearchNoteForm(true));
      document.getElementById("btn-research-fork")?.addEventListener("click", () => forkSearchFromRun(runId));
      document.getElementById("btn-research-insight")?.addEventListener("click", () => generateResearchInsight(runId));
      document.getElementById("btn-research-suggest")?.addEventListener("click", () => suggestResearchQueries(runId));
    }
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
    const md = await api("GET", `/api/research/trees/${tree.id}/markmap`);
    el.innerHTML = `<pre class="markmap">${escapeHtml(md.markdown || "")}</pre>`;
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
  workspaceSession.currentRunId = runId;
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
      if (data.status === "interrupted" && data.items?.length) {
        await renderSearchResults(data, resultsEl, reportEl, runId);
        prependResultsBanner(resultsEl, "warn", data.error || "任务已中断");
      } else if (data.status === "interrupted") {
        resultsEl.innerHTML = `<div class="alert alert-warn">${escapeHtml(data.error || "任务已中断")}</div>`;
      } else {
        await renderSearchResults(data, resultsEl, reportEl, runId);
      }
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
  if (!workspaceSession.treeId || !runId) return;
  const btn = document.getElementById("btn-research-insight");
  if (btn) {
    btn.disabled = true;
    btn.textContent = "归纳中…";
  }
  clearResearchFeedback();
  try {
    await api("POST", "/api/research/insight", {
      tree_id: workspaceSession.treeId,
      run_id: runId,
      parent_node_id: workspaceSession.parentNodeId,
    });
    await refreshResearchTree(workspaceSession.parentNodeId);
  } catch (err) {
    showResearchFeedback(err.message);
    await refreshResearchTree();
  }
}

async function suggestResearchQueries(runId) {
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
    const wrap = document.getElementById("suggested-queries");
    if (!wrap || !(data.queries || []).length) {
      showResearchFeedback("暂无建议，请稍后再试或手动输入关键词", "warn");
      return;
    }
    wrap.innerHTML = `<span class="toolbar-label">建议深挖（点击填入）</span>${data.queries
      .map((q) => `<button type="button" class="chip chip-btn" data-suggest-query="${escapeHtml(q)}">${escapeHtml(q)}</button>`)
      .join("")}`;
    wrap.querySelectorAll("[data-suggest-query]").forEach((chipBtn) => {
      chipBtn.addEventListener("click", () => {
        const input = document.getElementById("search-query");
        if (input) {
          input.value = chipBtn.dataset.suggestQuery;
          input.focus();
          input.scrollIntoView({ behavior: "smooth", block: "center" });
        }
      });
    });
    document.getElementById("search-form")?.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (err) {
    showResearchFeedback(err.message);
  } finally {
    await refreshResearchTree();
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
  if (!banner) return;
  try {
    const data = await api("GET", "/api/auth/status");
    const fails = data.items.filter((i) => !i.ok && (i.key === "zhihu" || i.key === "bilibili"));
    if (fails.length) {
      banner.classList.remove("hidden");
      banner.innerHTML = `部分来源未登录：${fails.map((f) => f.name).join("、")}。<a href="/settings">去设置同步 Cookie</a>`;
    } else {
      banner.classList.add("hidden");
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
      const at = n.at ? String(n.at).slice(0, 19).replace("T", " ") : "";
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
      el.classList.remove("hidden");
      el.className = "alert alert-warn";
      el.innerHTML = `画像可能已过时（新增行为数据已达阈值）。<button type="button" class="btn btn-sm" id="btn-persona-rebuild-inline">立即重建</button> <a href="/persona">详情</a>`;
      document.getElementById("btn-persona-rebuild-inline")?.addEventListener("click", async () => {
        try {
          await api("POST", "/api/persona/build?review=true");
          el.classList.add("hidden");
          alert("画像已重建");
        } catch (err) {
          alert(err.message);
        }
      });
      return;
    }
    el.classList.add("hidden");
  } catch (_) {
    el.classList.add("hidden");
  }
}

const STEP_LABELS = {
  starting: "准备",
  collect_all: "多源采集",
  alias_discover: "联网发现关联词",
  ai_query_analyze: "查询分析",
  dedup: "去重打分",
  mine_comments: "评论挖掘",
  ai_summarize: "AI 摘要",
  persona_simulate: "画像模拟",
  ai_report: "情报报告",
};

function stepLabel(name) {
  return STEP_LABELS[name] || name;
}

const SOURCE_LABELS = {
  zhihu: "知乎",
  bilibili: "B站",
  web: "网页",
  v2ex: "V2EX",
  rss: "RSS",
};

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
  if (!btn) return;
  btn.disabled = busy;
  btn.textContent = busy ? "搜罗中…" : "开始搜罗";
  btn.setAttribute("aria-busy", busy ? "true" : "false");
}

function normalizeStepName(raw) {
  return String(raw || "")
    .replace(/^\d+_/, "")
    .replace(/\.json$/, "");
}

function renderJobProgressPanel(container, state, options = {}) {
  if (!container) return;
  const {
    labelFn = stepLabel,
    showCancel = false,
    cancelUrl = "",
    showPartial = false,
    forcePercent = null,
  } = options;
  const phase = normalizeStepName(state.phase);
  const label = labelFn(phase);
  const detail = state.detail || "";
  const startedAt = state.startedAt ? new Date(state.startedAt).getTime() : Date.now();
  const elapsed = formatElapsedMs(Date.now() - startedAt);
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
            `<li><a href="${escapeHtml(r.url)}" target="_blank" rel="noopener">${escapeHtml((r.title || r.url || "").slice(0, 60))}</a></li>`
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
            const link = item.url
              ? `<a href="${escapeHtml(item.url)}" target="_blank" rel="noopener">${title}</a>`
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
    <div class="search-progress card card-flat">
      <div class="search-progress-head">
        <span class="search-progress-spinner" aria-hidden="true"></span>
        <div class="search-progress-main">
          <div class="search-progress-phase">${escapeHtml(label)}</div>
          <div class="search-progress-detail muted">${escapeHtml(detail || "处理中…")}</div>
        </div>
        ${cancelHtml}
        <span class="search-progress-elapsed muted" title="已用时间">${escapeHtml(elapsed)}</span>
      </div>
      ${barHtml}
      ${statsHtml}
      ${urlHtml}
      ${recentHtml}
      ${partialHtml}
      ${stepsHtml ? `<ol class="search-progress-steps">${stepsHtml}</ol>` : ""}
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
  const state = {
    runId,
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
      clearInterval(timer);
      return;
    }
    renderSearchProgressPanel(container, state);
  }, 1000);
  return {
    setRunId(id) {
      state.runId = id;
      renderSearchProgressPanel(container, state);
    },
    update(progress) {
      applyProgressPatch(state, progress);
      renderSearchProgressPanel(container, state);
    },
    stop() {
      clearInterval(timer);
    },
  };
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
  if (sim.raw) {
    return `<div class="sim-block"><p class="muted">未能结构化，请重新构建画像或关闭模拟</p></div>`;
  }
  const interest = sim.interest || "neutral";
  const conf = sim.confidence != null ? ` · ${Math.round(Number(sim.confidence) * 100)}%` : "";
  const verdict = sim.verdict ? escapeHtml(sim.verdict) : interest;
  const reason = sim.reason ? `<p class="sim-reason">${escapeHtml(sim.reason)}</p>` : "";
  const simRating = feedbackMap[`simulation:${itemId}`] || "";
  const feedback = itemId
    ? `<div class="sim-feedback">
        <button class="${feedbackBtnClass(simRating === "useful")}" data-base-label="模拟👍" data-sim-feedback="useful" data-id="${escapeHtml(itemId)}" data-verdict="${escapeHtml(sim.verdict || interest)}">${feedbackLabel("模拟👍", simRating === "useful")}</button>
        <button class="${feedbackBtnClass(simRating === "noise")}" data-base-label="模拟👎" data-sim-feedback="noise" data-id="${escapeHtml(itemId)}" data-verdict="${escapeHtml(sim.verdict || interest)}">${feedbackLabel("模拟👎", simRating === "noise")}</button>
      </div>`
    : "";
  return `<div class="sim-block"><span class="sim-badge sim-${escapeHtml(interest)}">${verdict}${conf}</span>${reason}${feedback}</div>`;
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
          return `<li class="${s.done ? "done" : "pending"}"><a href="${s.href}">${escapeHtml(s.label)}</a>${badge}<span class="muted">${escapeHtml(s.detail)}</span></li>`;
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
    });
  } catch (_) {}
}

/* 搜罗工作台 */
function initWorkspace(profiles, sources) {
  const form = document.getElementById("search-form");
  if (!form) return;

  const params = new URLSearchParams(window.location.search);
  const q = params.get("q");
  const runParam = params.get("run");
  if (q) document.getElementById("search-query").value = q;

  checkAuthBanner();
  loadSetupWizard();
  loadPersonaStaleBanner();
  loadSuggestedQueries();
  applyWorkspaceDefaults();
  initResearchViewToggle();
  initResearchNoteForm();
  initWorkspacePanelTabs();
  if (workspaceSession.treeId) void refreshResearchTree();

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    await runSearch();
  });

  const queryInput = document.getElementById("search-query");
  let expandTimer = null;
  queryInput?.addEventListener("input", () => {
    clearTimeout(expandTimer);
    expandTimer = setTimeout(() => refreshExpandedQueries(), 400);
  });
  document.getElementById("opt-include-slurs")?.addEventListener("change", () => refreshExpandedQueries());
  document.getElementById("opt-no-ai")?.addEventListener("change", () => refreshExpandedQueries());
  queryInput?.addEventListener("blur", () => refreshExpandedQueries());

  if (runParam) {
    void resumeSearchRun(runParam);
  } else if (workspaceSession.activeRunId && !q) {
    void resumeSearchRun(workspaceSession.activeRunId);
  } else if (q) {
    runSearch();
  }
}

async function refreshExpandedQueries() {
  const wrap = document.getElementById("expanded-queries-wrap");
  const chips = document.getElementById("expanded-queries");
  const countEl = document.getElementById("expanded-queries-count");
  const query = document.getElementById("search-query")?.value.trim();
  if (!wrap || !chips || !query) {
    wrap?.classList.add("hidden");
    return;
  }
  try {
    const sources = [...document.querySelectorAll("input[name='sources']:checked")].map((el) => el.value);
    const data = await api("POST", "/api/search/expand", {
      query,
      sources,
      no_ai: document.getElementById("opt-no-ai")?.checked || false,
      include_slurs: document.getElementById("opt-include-slurs")?.checked !== false,
    });
    const terms = data.queries_used || data.expanded_queries || [query];
    if (terms.length <= 1) {
      wrap.classList.add("hidden");
      return;
    }
    wrap.classList.remove("hidden");
    if (countEl) {
      const persisted = data.discover_meta?.persist?.saved;
      const added = (data.discover_meta?.persist?.added_aliases || []).length
        + (data.discover_meta?.persist?.added_slurs || []).length;
      countEl.textContent = persisted && added
        ? `(${terms.length}，新沉淀 ${added} 个)`
        : `(${terms.length})`;
    }
    const network = new Set(data.network_aliases || data.discover_meta?.discovered_aliases || []);
    chips.innerHTML = terms
      .map((t) => {
        const tag = network.has(t) ? "chip chip-network" : "chip chip-static";
        const label = network.has(t) ? `${escapeHtml(t)} · 联网` : escapeHtml(t);
        return `<span class="${tag}">${label}</span>`;
      })
      .join("");
  } catch (_) {
    wrap.classList.add("hidden");
  }
}

async function applyWorkspaceDefaults() {
  try {
    const auth = await api("GET", "/api/auth/status");
    const deepseek = auth.items.find((i) => i.key === "deepseek");
    if (deepseek?.ok) {
      const digest = document.getElementById("opt-digest");
      if (digest && !digest.dataset.userTouched) digest.checked = true;
    }
    const persona = await api("GET", "/api/persona/status");
    if (persona.version && persona.version > 0) {
      const noSim = document.getElementById("opt-no-simulate");
      if (noSim && !noSim.dataset.userTouched) noSim.checked = false;
    }
  } catch (_) {}
  document.getElementById("opt-digest")?.addEventListener("change", (e) => {
    e.target.dataset.userTouched = "1";
  });
  document.getElementById("opt-no-simulate")?.addEventListener("change", (e) => {
    e.target.dataset.userTouched = "1";
  });
}

async function runSearch() {
  const resultsEl = document.getElementById("search-results");
  const stepsEl = document.getElementById("steps-bar");
  const reportEl = document.getElementById("report-panel");
  const runLink = document.getElementById("run-link");
  const countEl = document.getElementById("results-count");
  const askSection = document.getElementById("ask-section");

  const query = document.getElementById("search-query").value.trim();
  const sources = [...document.querySelectorAll("input[name='sources']:checked")].map((el) => el.value);
  if (!query) {
    resultsEl.innerHTML = "<div class='alert alert-warn'>请输入要搜罗的话题</div>";
    return;
  }
  if (!sources.length) {
    resultsEl.innerHTML = "<div class='alert alert-warn'>请至少勾选一个来源</div>";
    return;
  }

  setSearchBusy(true);
  switchWorkspacePanel("results");
  resultsEl.innerHTML = "";
  const progressUi = mountSearchProgress(resultsEl);
  stepsEl.innerHTML = "<span class='step-pill active'>准备中</span>";
  if (countEl) countEl.textContent = "";
  const digestOn = document.getElementById("opt-digest").checked;
  if (reportEl) {
    reportEl.innerHTML = digestOn
      ? "<p class='muted'>情报报告将在搜罗完成后生成…</p>"
      : "<p class='muted'>未勾选「生成情报报告」；完成后可逐条查看结果与反馈。</p>";
  }
  if (askSection) askSection.classList.add("hidden");

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

  try {
    const start = await api("POST", "/api/search", body);
    const run_id = start.run_id;
    if (start.tree_id) setResearchTreeId(start.tree_id);
    setActiveSearchRunId(run_id);
    workspaceSession.currentRunId = run_id;
    progressUi.setRunId(run_id);
    runLink.href = `/runs/${run_id}`;
    runLink.classList.remove("hidden");
    runLink.textContent = "查看运行记录";

    subscribeSearchEvents(run_id, resultsEl, stepsEl, reportEl, progressUi);
  } catch (err) {
    progressUi?.stop();
    setSearchBusy(false);
    resultsEl.innerHTML = `<div class="alert alert-error">${escapeHtml(err.message)}</div>`;
    stepsEl.innerHTML = "";
  }
}

function finishSearchRun(progressUi, onDone) {
  progressUi?.stop();
  setSearchBusy(false);
  if (typeof onDone === "function") onDone();
}

function subscribeSearchEvents(runId, resultsEl, stepsEl, reportEl, progressUi) {
  const seen = new Set();
  let activePill = stepsEl.querySelector(".step-pill.active");
  const es = new EventSource(`/api/search/${runId}/events`);

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
    const msg = JSON.parse(ev.data);
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
    if (msg.type === "source_error") {
      showSourceErrors(msg.errors || [], resultsEl);
    }
    if (msg.type === "done") {
      finishSearchRun(progressUi, () => {
        es.close();
        if (activePill) {
          activePill.classList.remove("active");
          activePill.classList.add("done");
          activePill.textContent = "完成";
        }
        setActiveSearchRunId(null);
        void renderSearchResults(msg.result, resultsEl, reportEl, runId);
        void refreshResearchTree();
      });
    }
    if (msg.type === "cancelled") {
      finishSearchRun(progressUi, () => {
        es.close();
        resultsEl.innerHTML = `<div class="alert alert-warn">${escapeHtml(msg.error || "搜罗已取消")}</div>`;
        stepsEl.innerHTML = "";
      });
    }
    if (msg.type === "error") {
      finishSearchRun(progressUi, () => {
        es.close();
        resultsEl.innerHTML = `<div class="alert alert-error">${escapeHtml(msg.error)}</div>`;
        stepsEl.innerHTML = "";
      });
    }
    if (msg.type === "timeout") {
      es.close();
      void pollUntilSearchDone(runId, resultsEl, stepsEl, reportEl, progressUi);
    }
  };

  es.onerror = () => {
    fetch(`/api/search/${runId}`)
      .then((r) => r.json())
      .then((data) => {
        if (data.status === "done" && data.items) {
          finishSearchRun(progressUi, () => {
            es.close();
            void renderSearchResults(data, resultsEl, reportEl, runId);
          });
        }
      })
      .catch(() => {});
  };
}

function showSourceErrors(errors, resultsEl) {
  if (!errors.length) return;
  const id = "source-error-banner";
  let banner = document.getElementById(id);
  if (!banner) {
    banner = document.createElement("div");
    banner.id = id;
    banner.className = "alert alert-warn search-source-errors";
    const host = resultsEl.querySelector(".search-progress") || resultsEl;
    host.appendChild(banner);
  }
  const needsPlaywright = errors.some((e) => /playwright/i.test(String(e.error || "")));
  const needsCookie = errors.some((e) => /cookie|401|403|z_c0|SESSDATA/i.test(String(e.error || "")));
  let extra = "";
  if (needsPlaywright) extra += ' <a href="/settings#deps">去设置一键安装 Playwright</a>';
  if (needsCookie) extra += ' <a href="/settings">去设置同步 Cookie</a>';
  banner.innerHTML = `部分来源采集失败：${errors.map((e) => `${escapeHtml(e.source)}: ${escapeHtml(e.error)}`).join("；")}。${extra}`;
}

async function renderSearchResults(result, resultsEl, reportEl, runId) {
  if (result.source_errors?.length) showSourceErrors(result.source_errors, resultsEl);
  const items = result.items || [];
  const sims = result.simulations || [];
  const simMap = {};
  sims.forEach((s) => { if (s.item_id) simMap[s.item_id] = s; });
  const countEl = document.getElementById("results-count");
  const askSection = document.getElementById("ask-section");

  if (countEl) {
    countEl.textContent = items.length ? `共 ${items.length} 条` : "";
  }

  if (!items.length) {
    resultsEl.innerHTML = "<div class='empty-state'>未找到结果，可尝试换关键词、增加来源或检查 Cookie 设置</div>";
    if (reportEl && !result.report) {
      reportEl.innerHTML = "<p class='muted'>无报告内容</p>";
    }
    return;
  }

  const feedbackMap = await loadFeedbackMap(items.map((i) => i.id));
  resultsEl.innerHTML = `${renderResultsToolbar(items.length)}<div class="item-card-list">${items
    .map((item, idx) => renderItemCard(item, simMap[item.id], runId, feedbackMap, idx === 0))
    .join("")}</div>`;

  hydrateItemCards(resultsEl, items);
  initItemCardInteractions(resultsEl);
  bindResultsToolbar(resultsEl);

  resultsEl.querySelectorAll("[data-feedback]").forEach((btn) => {
    btn.addEventListener("click", () => submitFeedback(btn.dataset.feedback, btn.dataset.id, runId, btn));
  });
  resultsEl.querySelectorAll("[data-sim-feedback]").forEach((btn) => {
    btn.addEventListener("click", () =>
      submitSimFeedback(btn.dataset.simFeedback, btn.dataset.id, btn.dataset.verdict, runId, btn));
  });
  resultsEl.querySelectorAll("[data-save]").forEach((btn) => {
    btn.addEventListener("click", () => saveFromCard(btn.dataset.save));
  });

  if (reportEl && result.report) {
    renderMarkdown(reportEl, result.report);
    if (askSection) askSection.classList.remove("hidden");
    initAskPanel(runId);
  } else if (reportEl) {
    reportEl.innerHTML = "<p class='muted'>未生成报告。勾选「生成情报报告」或在高级选项中关闭「跳过 AI」。</p>";
  }
}

function renderItemCard(item, sim, runId, feedbackMap = {}, expandedDefault = false) {
  const src = item.source || "web";
  const fold = item.signals?.fold_reason
    ? `<div class="fold-reason">${escapeHtml(item.signals.fold_reason)}</div>` : "";
  const seenBadge = item.personal?.already_seen
    ? `<span class="source-badge source-seen">已关注</span>` : "";
  const simHtml = formatSimulation(sim, item.id, runId, feedbackMap);
  const itemRating = feedbackMap[`item:${item.id}`] || "";
  const rawText = (item.content || item.layers?.subtitle?.text || "").trim();
  const teaser = escapeHtml(itemCardTeaser(item));
  const flags = itemSectionFlags(item, sim);
  const flagsHtml = flags.length
    ? `<div class="item-card-flags">${flags.map((f) => `<span class="item-flag">${escapeHtml(f)}</span>`).join("")}</div>`
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
  }

  if (simHtml) {
    sections.push(`<details class="item-section item-section-sim">
      <summary class="item-section-summary">画像模拟</summary>
      <div class="item-section-body">${simHtml}</div>
    </details>`);
  }

  const metrics = [];
  if (item.metrics?.likes) metrics.push(`👍 ${item.metrics.likes}`);
  if (item.metrics?.comments) metrics.push(`💬 ${item.metrics.comments}`);
  if (item.author) metrics.push(escapeHtml(item.author));

  return `<article class="card item-card item-source-${escapeHtml(src)} ${expandedClass}" data-item-id="${escapeHtml(item.id)}">
    <div class="item-card-header" role="button" tabindex="0" aria-expanded="${ariaExpanded}">
      <span class="item-card-chevron" aria-hidden="true"></span>
      <div class="item-card-head-content">
        <div class="item-card-meta">
          <span class="source-badge source-${escapeHtml(src)}">${escapeHtml(sourceLabel(src))}</span>
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
        <a class="btn btn-sm btn-secondary" href="${escapeHtml(item.url)}" target="_blank" rel="noopener">原文</a>
      </div>
    </div>
    <div class="item-card-body">
      <div class="item-card-sections">${sections.join("")}</div>
      <div class="actions">
        <a class="btn btn-sm" href="${escapeHtml(item.url)}" target="_blank" rel="noopener">打开原文</a>
        <button class="btn btn-sm btn-secondary" data-save="${escapeHtml(item.url)}">收录</button>
        <button class="${feedbackBtnClass(itemRating === "useful", "btn btn-sm btn-secondary")}" data-base-label="有用" data-feedback="useful" data-id="${item.id}">${feedbackLabel("有用", itemRating === "useful")}</button>
        <button class="${feedbackBtnClass(itemRating === "noise")}" data-base-label="噪音" data-feedback="noise" data-id="${item.id}">${feedbackLabel("噪音", itemRating === "noise")}</button>
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

async function loadSuggestedQueries() {
  const el = document.getElementById("suggested-queries");
  if (!el) return;
  try {
    const data = await api("GET", "/api/persona/suggested-queries");
    const queries = data.queries || [];
    if (!queries.length) {
      el.innerHTML = "";
      return;
    }
    el.innerHTML = `<span class="toolbar-label">推荐搜罗</span>${queries
      .map((q) => `<button type="button" class="chip chip-btn" data-suggest-query="${escapeHtml(q)}">${escapeHtml(q)}</button>`)
      .join("")}`;
    el.querySelectorAll("[data-suggest-query]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const input = document.getElementById("search-query");
        if (input) input.value = btn.dataset.suggestQuery;
      });
    });
  } catch (_) {
    el.innerHTML = "";
  }
}

async function saveFromCard(url) {
  try {
    const data = await api("POST", "/api/save", { url });
    alert(`已收录: ${data.item.title}`);
  } catch (err) {
    alert(err.message);
  }
}

function initAskPanel(runId) {
  const form = document.getElementById("ask-form");
  const history = document.getElementById("ask-history");
  if (!form) return;
  form.onsubmit = async (e) => {
    e.preventDefault();
    const input = document.getElementById("ask-question");
    const q = input.value.trim();
    if (!q) return;
    try {
      const data = await api("POST", "/api/ask", {
        question: q,
        run_id: runId,
        tree_id: workspaceSession.treeId,
        parent_node_id: workspaceSession.parentNodeId,
      });
      const block = document.createElement("div");
      block.className = "card";
      if (data.ok === false) {
        block.innerHTML = `<p><strong>问:</strong> ${escapeHtml(q)}</p><p class="alert alert-error">${escapeHtml(data.error || "追问失败")}</p>`;
        history.appendChild(block);
        input.value = "";
        return;
      }
      block.innerHTML = `<p><strong>问:</strong> ${escapeHtml(q)}</p><div class="markdown-body"></div>`;
      renderMarkdown(block.querySelector(".markdown-body"), data.answer);
      history.appendChild(block);
      input.value = "";
      void refreshResearchTree(workspaceSession.parentNodeId);
    } catch (err) {
      alert(err.message);
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
      `<div class="card"><a href="${escapeHtml(i.url)}" target="_blank">${escapeHtml(i.title)}</a><div class="muted">[${i.source}]</div></div>`
    ).join("") || "<p class='muted'>暂无收录</p>";
  } catch (_) {
    el.innerHTML = "<p class='muted'>加载失败</p>";
  }
}

/* 知识库 */
function initKnowledge() {
  const params = new URLSearchParams(window.location.search);
  const q = params.get("q") || "";
  const tab = params.get("tab") || "search";
  const url = params.get("url") || "";
  const input = document.getElementById("knowledge-query");
  if (input && q) input.value = q;
  document.querySelectorAll("[data-knowledge-tab]").forEach((btn) => {
    btn.addEventListener("click", () => switchKnowledgeTab(btn.dataset.knowledgeTab));
  });
  if (tab === "save") switchKnowledgeTab("save");
  const saveForm = document.getElementById("save-form");
  if (saveForm) {
    if (url) document.getElementById("save-url").value = url;
    saveForm.addEventListener("submit", async (e) => {
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
  const form = document.getElementById("knowledge-form");
  if (form) {
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      await searchKnowledge();
    });
    if (q) searchKnowledge();
  }
}

function switchKnowledgeTab(name) {
  document.querySelectorAll("[data-knowledge-tab]").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.knowledgeTab === name);
  });
  document.getElementById("knowledge-tab-search")?.classList.toggle("active", name === "search");
  document.getElementById("knowledge-tab-search")?.classList.toggle("hidden", name !== "search");
  document.getElementById("knowledge-tab-save")?.classList.toggle("active", name === "save");
  document.getElementById("knowledge-tab-save")?.classList.toggle("hidden", name !== "save");
}

async function searchKnowledge() {
  const el = document.getElementById("knowledge-results");
  const q = document.getElementById("knowledge-query").value.trim();
  const source = document.getElementById("knowledge-source").value;
  const mode = document.querySelector("input[name='knowledge-mode']:checked")?.value || "keyword";
  let url = mode === "semantic"
    ? `/api/knowledge/recall?q=${encodeURIComponent(q)}&limit=50`
    : `/api/knowledge/items?q=${encodeURIComponent(q)}&limit=50`;
  if (source && mode === "keyword") url += `&source=${encodeURIComponent(source)}`;
  try {
    const data = await api("GET", url);
    el.innerHTML = data.items.map((i) =>
      `<div class="card item-card">
        <div class="meta">[${escapeHtml(i.source)}]</div>
        <div class="title">${escapeHtml(i.title)}</div>
        <p class="summary">${escapeHtml(i.summary || i.content?.slice(0, 200) || "")}</p>
        <a class="btn btn-sm" href="${escapeHtml(i.url)}" target="_blank">原文</a>
      </div>`
    ).join("") || "<p class='muted'>未找到匹配条目</p>";
  } catch (err) {
    el.innerHTML = `<div class="alert alert-error">${escapeHtml(err.message)}</div>`;
  }
}

/* 简报 */
function initDigest() {
  document.getElementById("btn-daily")?.addEventListener("click", async () => {
    const el = document.getElementById("daily-content");
    const useAi = document.getElementById("opt-digest-ai")?.checked;
    el.innerHTML = "<p class='muted'>生成中…</p>";
    try {
      const url = useAi ? "/api/digest/daily?ai=1" : "/api/digest/daily";
      const data = await api("GET", url);
      renderMarkdown(el, data.content);
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
      ? `<ul>${items.map((d) => `<li><strong>${escapeHtml(d.date)}</strong> — ${escapeHtml(d.preview || "")}</li>`).join("")}</ul>`
      : "<p class='muted'>暂无存档。生成今日简报后会保存在 ~/.osint/digests/</p>";
  } catch (_) {
    el.textContent = "无法加载简报存档";
  }
}

async function loadReportList() {
  const el = document.getElementById("report-list");
  if (!el) return;
  try {
    const data = await api("GET", "/api/digest/reports");
    el.innerHTML = `<table class="table"><thead><tr><th>Run ID</th><th>话题</th><th>操作</th></tr></thead><tbody>${
      data.reports.map((r) =>
        `<tr><td>${escapeHtml(r.run_id)}</td><td>${escapeHtml(r.query || "")}</td>
        <td><a href="/runs/${r.run_id}">详情</a></td></tr>`
      ).join("")
    }</tbody></table>` || "<p class='muted'>暂无历史报告</p>";
  } catch (_) {}
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
    el.innerHTML = `<div class="card card-flat"><h3>AI 行为解读</h3><div class="markdown-body"></div>${data.cached ? "<p class='muted'>（缓存）</p>" : ""}</div>`;
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
    el.innerHTML = `<table class="data-table"><thead><tr>
      <th>时间</th><th>类型</th><th>来源</th><th>标题</th><th>权重</th>
    </tr></thead><tbody>${data.items.map((row) => {
      const dwell = row.duration_ms ? ` · ${Math.round(row.duration_ms / 1000)}s` : "";
      const title = row.url
        ? `<a href="${escapeHtml(row.url)}" target="_blank">${escapeHtml((row.title || row.url).slice(0, 80))}</a>${dwell}`
        : escapeHtml((row.title || "—").slice(0, 80));
      return `<tr>
        <td class="muted">${escapeHtml(String(row.created_at || "").slice(0, 16))}</td>
        <td>${escapeHtml(formatEventType(row.event_type))}</td>
        <td>${escapeHtml(row.source || "")}</td>
        <td>${title}</td>
        <td>${row.score}</td>
      </tr>`;
    }).join("")}</tbody></table>`;
  } catch (err) {
    el.innerHTML = `<div class="alert alert-error">${escapeHtml(err.message)}</div>`;
  }
}

function renderPersonaModel(model) {
  if (!model || typeof model !== "object") return "<p class='muted'>暂无心智模型，请先完成行为同步并构建画像。</p>";
  const parts = [];
  if (model.version != null) {
    parts.push(`<div class="persona-summary-grid"><div class="persona-stat">版本<strong>v${escapeHtml(String(model.version))}</strong></div></div>`);
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
      showPageNotice(
        "persona-notice",
        `画像 v${data.version} 已生成。<a href="/">去搜罗页试试画像模拟</a>`,
        "success",
      );
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
    <details open><summary>构建前</summary><pre>${escapeHtml(r.brief_before || "")}</pre></details>
    <details open><summary>构建后</summary><pre>${escapeHtml(r.brief_after || "")}</pre></details>
    <p class="mt-1"><a href="/" class="btn btn-sm">去搜罗试试</a></p>`;
}

async function loadPersona() {
  const el = document.getElementById("persona-content");
  if (!el) return;
  try {
    const data = await api("GET", "/api/persona");
    const versions = (data.versions || []).map((v) => {
      const ver = v.replace("v", "");
      return `<button class="btn btn-sm btn-secondary" onclick="rollbackPersona(${ver})">回滚 ${v}</button>`;
    }).join(" ");
    el.innerHTML = `
      <div class="card"><h2>心智模型</h2>${renderPersonaModel(data.mental_model)}</div>
      <div class="card"><h2>可读摘要（Brief）</h2><div class="markdown-body" id="persona-brief"></div></div>
      <div class="mt-1">${versions || "<span class='muted'>暂无历史版本</span>"}</div>`;
    renderMarkdown(document.getElementById("persona-brief"), data.brief || "（暂无）");
  } catch (err) {
    el.innerHTML = `<div class="alert alert-error">${escapeHtml(err.message)}</div>`;
  }
}

async function rollbackPersona(version) {
  const ok = window.confirm(`确认回滚到 v${version}？当前画像将被替换。`);
  if (!ok) return;
  try {
    const data = await api("POST", "/api/persona/rollback", { version });
    if (data.ok) {
      showPageNotice("persona-notice", `已回滚到 v${version}`, "success");
      loadPersona();
    } else {
      showPageNotice("persona-notice", "版本不存在", "error");
    }
  } catch (err) {
    showPageNotice("persona-notice", escapeHtml(err.message), "error");
  }
}

/* 导入 */
async function loadIngestPreflight() {
  const el = document.getElementById("ingest-preflight-content");
  const btn = document.getElementById("btn-ingest-full-sync");
  if (!el) return false;
  try {
    const [pre, ext] = await Promise.all([
      api("GET", "/api/ingest/preflight"),
      api("GET", "/api/extension/status").catch(() => ({ connected: false })),
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
        btn.disabled = false;
        btn.title = "Cookie 未完全就绪，同步可能部分失败";
      }
    } else {
      hints = `<div class="alert alert-success mt-1">可以开始完整同步（约 2–5 分钟）。</div>`;
      if (btn) {
        btn.disabled = false;
        btn.title = "";
      }
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
  void loadIngestPreflight();
  loadIngestHealth();
  document.getElementById("btn-ingest-browser")?.addEventListener("click", async () => {
    const days = parseInt(document.getElementById("browser-since").value, 10) || 90;
    await runIngest("browser", { since_days: days }, "ingest-browser-result");
  });
  document.getElementById("btn-ingest-bilibili")?.addEventListener("click", () =>
    runIngest("bilibili", null, "ingest-bilibili-result"));
  document.getElementById("btn-ingest-aicu")?.addEventListener("click", () =>
    runIngest("aicu-comments", null, "ingest-aicu-result"));
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
  document.getElementById("btn-ingest-zhihu")?.addEventListener("click", () =>
    runIngest("zhihu", null, "ingest-zhihu-result"));
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
        el.className = "alert alert-warn mt-1";
        el.innerHTML = `${(pre.hints || ["Cookie 未就绪，仍可尝试但可能失败"]).map(escapeHtml).join("<br>")}<br><a href="/settings">去设置页</a>`;
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
          const ok = job.ok || (job.count || 0) > 0;
          el.className = ok ? "alert alert-success mt-1" : "alert alert-warn mt-1";
          let msg = `完整同步完成：共 ${job.count || 0} 条`;
          if (ok) msg += ' <a href="/persona">去构建画像</a>';
          if (job.warnings?.length) {
            msg += `<br><span class="muted">${job.warnings.map(escapeHtml).join("；")}</span>`;
          }
          const hint = job.extension_flush_hint;
          if (hint?.message) {
            msg += `<br><span class="muted">${escapeHtml(hint.message)}</span>`;
          }
          el.innerHTML = msg;
          loadIngestHealth();
          void loadIngestPreflight();
          loadSetupWizard();
          initGlobalSidebar();
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
      el.className = ok ? "alert alert-success mt-1" : "alert alert-error mt-1";
      let msg = `共 ${data.count || 0} 条：B站 ${b.count || 0}（观看 ${b.watch_count || 0} / 收藏 ${b.favorite_count || 0} / 点赞 ${b.like_count || 0} / 关注 ${b.following_count || 0}），知乎 ${z.count || 0}（收藏 ${z.favorite_count || 0} / 动态 ${z.activity_count || 0} / 赞同 ${z.vote_count || 0} / 浏览 ${z.browse_count || 0}）`;
      if (data.python) msg += ` · Python ${escapeHtml(data.python)}`;
      if (ok) msg += ' <a href="/persona">去构建画像</a>';
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
      void loadIngestPreflight();
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
        platforms: ["bilibili", "zhihu"],
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
          if (ok) msg += ' <a href="/persona">去构建画像</a>';
          if (job.warnings?.length) {
            msg += `<br><span class="muted">${job.warnings.map(escapeHtml).join("；")}</span>`;
          }
          el.innerHTML = msg;
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
  document.getElementById("btn-extension-refresh")?.addEventListener("click", loadExtensionStatus);
  loadExtensionStatus();
  loadLikes();
  loadIngestCapabilities();
}

async function loadExtensionStatus() {
  const el = document.getElementById("extension-status");
  if (!el) return;
  try {
    const data = await api("GET", "/api/extension/status");
    const connected = data.connected;
    const total = data.extension_event_count || 0;
    const types = Object.entries(data.event_totals || {})
      .map(([k, v]) => `${EXT_EVENT_LABELS[k] || k} ${v}`)
      .join(" · ");
    el.className = "extension-status-card";
    el.innerHTML = `
      <div class="preflight-row">
        <strong>${connected ? "扩展已连接" : "未检测到扩展"}</strong>
        <span class="preflight-badge ${connected ? "ok" : "warn"}">${connected ? "正常" : "待安装"}</span>
      </div>
      <p class="muted mt-1">已采集事件 <strong>${total}</strong> 条${types ? `（${escapeHtml(types)}）` : ""}</p>
      ${data.last_seen ? `<p class="muted">最近心跳 ${escapeHtml(String(data.last_seen).slice(0, 19))}</p>` : "<p class='muted'>安装扩展后打开任意网页，再点「刷新状态」</p>"}
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
        const behaviors = (p.behaviors || [])
          .filter((b) => b.count > 0)
          .map((b) => `${escapeHtml(b.behavior)} ${b.count}`)
          .join("，");
        return `<div class="preflight-row"><strong>${escapeHtml(platformLabel)}</strong><span>${p.total} 条${behaviors ? ` — ${behaviors}` : ""}</span></div>`;
      })
      .join("");
    const statusClass = data.ok ? "alert-success" : "alert-warn";
    el.innerHTML = `
      <div class="alert ${statusClass}">${data.ok ? "数据就绪，可构建画像" : "尚有阻塞项"} · 行为事件共 ${events} 条 · ${auth}</div>
      ${blockers ? `<ul class="health-list">${blockers}</ul>` : ""}
      ${warnings ? `<ul class="health-list muted">${warnings}</ul>` : ""}
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
    const platformLabels = { bilibili: "B站", zhihu: "知乎", browser: "浏览器", extension: "扩展", weixin: "微信" };
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
    scroll.innerHTML = `<table class="data-table"><thead><tr><th>平台</th><th>行为</th><th>状态</th><th>说明</th></tr></thead><tbody>${rows}</tbody></table>`;
  } catch (_) {
    scroll.innerHTML = "<p class='muted'>无法加载能力说明</p>";
  }
}

async function runIngest(type, body, resultId) {
  const el = document.getElementById(resultId);
  el.textContent = "导入中…";
  try {
    const url = type === "browser" ? "/api/ingest/browser" : `/api/ingest/${type}`;
    const data = await api("POST", url, body);
    el.className = "alert alert-success";
    let detail = `共 ${data.count} 条`;
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
    let msg = `${detail}。<a href="/persona">去构建画像</a>`;
    if (data.warnings?.length) {
      msg += `<br><span class="muted">警告: ${data.warnings.map(escapeHtml).join("；")}</span>`;
    }
    el.innerHTML = msg;
    return;
  } catch (err) {
    el.className = "alert alert-error";
    el.textContent = err.message;
  }
}

async function loadLikes() {
  const el = document.getElementById("likes-list");
  if (!el) return;
  try {
    const data = await api("GET", "/api/ingest/likes");
    el.textContent = `认可记录: ${data.count} 条`;
  } catch (_) {}
}

/* 运行记录 */
function initRuns() {
  loadRunsList();
}

async function loadRunsList() {
  const el = document.getElementById("runs-list");
  if (!el) return;
  try {
    const data = await api("GET", "/api/runs?limit=50");
    el.innerHTML = `<table class="table"><thead><tr><th>Run ID</th><th>命令</th><th>话题</th><th>状态</th><th>操作</th></tr></thead><tbody>${
      data.runs.map((r) => {
        const st = r.status || "done";
        const stClass = `run-status-${st}`;
        const track =
          st === "running"
            ? `<a href="/?run=${encodeURIComponent(r.run_id)}">继续跟踪</a>`
            : st === "interrupted"
              ? `<a href="/?run=${encodeURIComponent(r.run_id)}">查看部分结果</a>`
              : `<a href="/runs/${r.run_id}">详情</a>`;
        return `<tr>
        <td><a href="/runs/${r.run_id}">${escapeHtml(r.run_id)}</a></td>
        <td>${escapeHtml(r.command || "")}</td>
        <td>${escapeHtml(r.query || "")}</td>
        <td class="${stClass}">${escapeHtml(formatRunStatus(st))}</td>
        <td>${track}</td></tr>`;
      }).join("")
    }</tbody></table>`;
  } catch (err) {
    el.innerHTML = `<div class="alert alert-error">${escapeHtml(err.message)}</div>`;
  }
}

function initRunDetail(runId) {
  loadRunDetail(runId);
}

async function loadRunDetail(runId) {
  const el = document.getElementById("run-detail");
  if (!el) return;
  try {
    const data = await api("GET", `/api/runs/${runId}`);
    const steps = data.steps || [];
    let html = `<div class="card"><h2>Pipeline 步骤</h2>`;
    if (steps.length) {
      html += `<table class="data-table"><thead><tr><th>步骤</th><th>状态</th><th>耗时</th><th>说明</th></tr></thead><tbody>${
        steps.map((s) => `<tr>
          <td>${escapeHtml(s.step || s._file || "")}</td>
          <td class="${s.status === "error" ? "status-fail" : ""}">${escapeHtml(s.status || "")}</td>
          <td>${s.duration_ms != null ? `${s.duration_ms}ms` : ""}</td>
          <td class="muted">${escapeHtml((s.issues || []).join("; ") || s.output_summary || "")}</td>
        </tr>`).join("")
      }</tbody></table>`;
    } else {
      html += `<p class="muted">无步骤记录</p>`;
    }
    html += `</div>`;
    if (data.report) {
      html += `<div class="card"><h2>报告</h2><div class="markdown-body" id="run-report"></div></div>`;
    }
    if (data.artifacts?.length) {
      html += `<div class="card"><h2>Artifacts</h2><ul>${data.artifacts.map((a) =>
        `<li><a href="/api/runs/${runId}/artifacts/${a}" target="_blank">${escapeHtml(a)}</a></li>`
      ).join("")}</ul></div>`;
    }
    el.innerHTML = html;
    if (data.report) renderMarkdown(document.getElementById("run-report"), data.report);
  } catch (err) {
    el.innerHTML = `<div class="alert alert-error">${escapeHtml(err.message)}</div>`;
  }
}

/* AI 控制 */
function initAI() {
  loadDirectives();
  loadPromptList();
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
      document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
      tab.classList.add("active");
      document.getElementById(tab.dataset.panel).classList.add("active");
    });
  });
  document.getElementById("btn-save-directives")?.addEventListener("click", saveDirectives);
  document.getElementById("btn-save-prompt")?.addEventListener("click", savePrompt);
  document.getElementById("btn-reset-prompt")?.addEventListener("click", resetPrompt);
  document.getElementById("prompt-select")?.addEventListener("change", loadPrompt);
}

async function loadDirectives() {
  const el = document.getElementById("directives-editor");
  const summary = document.getElementById("hard-constraints");
  if (!el) return;
  try {
    const data = await api("GET", "/api/ai/directives");
    el.value = JSON.stringify(data, null, 2);
    const hc = data.hard_constraints || data.get?.hard_constraints;
    if (summary && data.hard_constraints) {
      summary.textContent = `硬约束: ${JSON.stringify(data.hard_constraints)}`;
    }
  } catch (err) { el.value = err.message; }
}

async function saveDirectives() {
  try {
    const data = JSON.parse(document.getElementById("directives-editor").value);
    await api("PUT", "/api/ai/directives", { data });
    alert("已保存");
  } catch (err) { alert(err.message); }
}

async function loadPromptList() {
  const sel = document.getElementById("prompt-select");
  if (!sel) return;
  const data = await api("GET", "/api/ai/prompts");
  sel.innerHTML = data.prompts.map((p) =>
    `<option value="${p.name}">${p.name} (${p.source})</option>`
  ).join("");
  loadPrompt();
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
  alert("已保存");
  loadPromptList();
}

async function resetPrompt() {
  const name = document.getElementById("prompt-select").value;
  await api("POST", `/api/ai/prompts/${name}/reset`);
  alert("已恢复内置");
  loadPromptList();
}

/* 设置 */
function initSettings() {
  loadApiKeysPanel();
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
    const data = await api("GET", "/api/auth/status");
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
  const data = await api("GET", "/api/auth/paths");
  el.innerHTML = `<ul>
    <li>${escapeHtml(data.api_key_hint)}</li>
    <li>Cookie: ${escapeHtml(data.cookies_dir)}</li>
    <li>Data: ${escapeHtml(data.data_dir)}</li>
    <li>Directives: ${escapeHtml(data.directives_path)}</li>
  </ul>`;
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
        ? "请改用扩展弹窗「从浏览器同步 Cookie」（推荐），或以管理员运行 sync-cookies-admin.bat"
        : "请用 start-osint-web.bat 启动 Web，或扩展同步 Cookie";
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
