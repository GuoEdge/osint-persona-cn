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
  return `<section class="content-section comments-raw-section">
    <h4 class="section-label">原始热评 (${comments.length})</h4>
    <div class="comments-list">${rows}</div>
  </section>`;
}

function hydrateItemCards(container, items) {
  const byId = Object.fromEntries(items.map((i) => [i.id, i]));
  container.querySelectorAll(".item-card[data-item-id]").forEach((card) => {
    const item = byId[card.dataset.itemId];
    if (!item) return;
    const raw = card.querySelector(".raw-body");
    if (raw && item.content) renderMarkdown(raw, item.content);
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
        setupChip.innerHTML = `入门 <a href="/">${done}/${total}</a>`;
      }
    } catch (_) {}
  }
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
  collect_all: "多源采集",
  alias_discover: "联网发现关联词",
  ai_query_analyze: "查询分析",
  dedup: "去重",
  mine_comments: "评论挖掘",
  ai_summarize: "AI 摘要",
  persona_simulate: "画像模拟",
};

const SOURCE_LABELS = {
  zhihu: "知乎",
  bilibili: "B站",
  web: "网页",
  v2ex: "V2EX",
  rss: "RSS",
};

function stepLabel(name) {
  return STEP_LABELS[name] || name;
}

function sourceLabel(name) {
  return SOURCE_LABELS[name] || name;
}

function formatSimulation(sim, itemId, runId, feedbackMap = {}) {
  if (!sim) return "";
  if (sim.raw) {
    return `<div class="sim-block"><strong>画像模拟</strong><p class="muted">未能结构化，请重新构建画像或关闭模拟</p></div>`;
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
        (s) =>
          `<li class="${s.done ? "done" : "pending"}"><a href="${s.href}">${escapeHtml(s.label)}</a><span class="muted">${escapeHtml(s.detail)}</span></li>`
      )
      .join("");
    el.innerHTML = `
      <div class="setup-header">
        <h2>首次使用向导</h2>
        <button type="button" class="btn btn-ghost btn-sm" id="setup-dismiss">稍后再说</button>
      </div>
      <p class="muted">建议按顺序完成以下步骤，画像模拟与个性化搜罗才准确。</p>
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
  if (q) document.getElementById("search-query").value = q;

  checkAuthBanner();
  loadSetupWizard();
  loadPersonaStaleBanner();
  loadSuggestedQueries();
  applyWorkspaceDefaults();

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

  if (q) runSearch();
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

  resultsEl.innerHTML = "<div class='empty-state'>正在搜罗，请稍候…</div>";
  stepsEl.innerHTML = "<span class='step-pill active'>准备中</span>";
  if (countEl) countEl.textContent = "";
  if (reportEl) {
    reportEl.innerHTML = "<p class='muted'>报告生成中…</p>";
  }
  if (askSection) askSection.classList.add("hidden");

  const sources = [...document.querySelectorAll("input[name='sources']:checked")].map((el) => el.value);
  const body = {
    query: document.getElementById("search-query").value.trim(),
    sources,
    limit: parseInt(document.getElementById("search-limit").value, 10) || 10,
    digest: document.getElementById("opt-digest").checked,
    trace: document.getElementById("opt-trace").checked,
    profile: document.getElementById("search-profile").value,
    no_ai: document.getElementById("opt-no-ai").checked,
    no_simulate: document.getElementById("opt-no-simulate").checked,
    ai_instruct: document.getElementById("ai-instruct").value,
    mine_comments: document.getElementById("opt-mine-comments")?.checked !== false,
    comment_mine_top: parseInt(document.getElementById("comment-mine-top")?.value, 10) || 0,
    include_slurs: document.getElementById("opt-include-slurs")?.checked !== false,
    disabled_ai_steps: [...document.querySelectorAll("input[name='no-ai-step']:checked")].map((el) => el.value),
  };

  try {
    const { run_id } = await api("POST", "/api/search", body);
    runLink.href = `/runs/${run_id}`;
    runLink.classList.remove("hidden");
    runLink.textContent = "查看运行记录";

    subscribeSearchEvents(run_id, resultsEl, stepsEl, reportEl);
  } catch (err) {
    resultsEl.innerHTML = `<div class="alert alert-error">${escapeHtml(err.message)}</div>`;
    stepsEl.innerHTML = "";
  }
}

function subscribeSearchEvents(runId, resultsEl, stepsEl, reportEl) {
  const seen = new Set();
  const es = new EventSource(`/api/search/${runId}/events`);

  es.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.type === "step") {
      const step = msg.step?.step || msg.file;
      if (!seen.has(step)) {
        seen.add(step);
        const pill = document.createElement("span");
        pill.className = "step-pill done";
        pill.textContent = stepLabel(String(step).replace(/^\d+_/, "").replace(/\.json$/, ""));
        stepsEl.appendChild(pill);
      }
    }
    if (msg.type === "source_error") {
      showSourceErrors(msg.errors || [], resultsEl);
    }
    if (msg.type === "done") {
      es.close();
      void renderSearchResults(msg.result, resultsEl, reportEl, runId);
    }
    if (msg.type === "error") {
      es.close();
      resultsEl.innerHTML = `<div class="alert alert-error">${escapeHtml(msg.error)}</div>`;
    }
  };

  es.onerror = () => {
    fetch(`/api/search/${runId}`)
      .then((r) => r.json())
      .then((data) => {
        if (data.status === "done" && data.items) {
          es.close();
          void renderSearchResults(data, resultsEl, reportEl, runId);
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
    banner.className = "alert alert-warn";
    resultsEl.prepend(banner);
  }
  banner.innerHTML = `部分来源采集失败：${errors.map((e) => `${escapeHtml(e.source)}: ${escapeHtml(e.error)}`).join("；")}`;
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
  resultsEl.innerHTML = items
    .map((item) => renderItemCard(item, simMap[item.id], runId, feedbackMap))
    .join("");

  hydrateItemCards(resultsEl, items);

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

function renderItemCard(item, sim, runId, feedbackMap = {}) {
  const src = item.source || "web";
  const fold = item.signals?.fold_reason
    ? `<div class="fold-reason">折叠原因: ${escapeHtml(item.signals.fold_reason)}</div>` : "";
  const seenBadge = item.personal?.already_seen
    ? `<span class="source-badge">已关注</span>` : "";
  const simHtml = formatSimulation(sim, item.id, runId, feedbackMap);
  const itemRating = feedbackMap[`item:${item.id}`] || "";
  const isShort = (item.content?.length || 0) <= 400 || item.type === "comment";
  const sections = [];

  if (item.content) {
    sections.push(`<section class="content-section raw-section${isShort ? " raw-prominent" : ""}">
      <h4 class="section-label">原始内容</h4>
      <div class="md-content raw-body"></div>
    </section>`);
  }

  const aiParts = [];
  if (item.summary) {
    aiParts.push(`<section class="content-section ai-section">
      <h4 class="section-label">AI 摘要</h4>
      <div class="md-content summary-body"></div>
    </section>`);
  }
  if (item.key_points?.length) {
    aiParts.push(`<ul class="key-points">${item.key_points.map((p) => `<li>${escapeHtml(p)}</li>`).join("")}</ul>`);
  }
  if (item.layers?.comments_summary) {
    aiParts.push(`<section class="content-section">
      <h4 class="section-label">社区观点归纳</h4>
      <div class="md-content comments-summary-body"></div>
      <p class="muted section-hint">以上为 AI 归纳，非事实陈述；下方可查看原始热评。</p>
    </section>`);
  }
  if (item.personal?.matched_queries?.length > 1) {
    aiParts.push(`<p class="muted">命中关联词: ${item.personal.matched_queries.map((q) => escapeHtml(q)).join("、")}</p>`);
  }
  if (item.layers?.comments?.length) {
    aiParts.push(formatCommentsSection(item.layers.comments));
  }
  if (aiParts.length) {
    sections.push(`<div class="analysis-block">${aiParts.join("")}</div>`);
  }

  return `<article class="card item-card" data-item-id="${escapeHtml(item.id)}">
    <div class="meta">
      <span class="source-badge source-${escapeHtml(src)}">${escapeHtml(sourceLabel(src))}</span>
      ${seenBadge}
      <span>相关度 ${item.signals?.relevance ?? "-"}</span>
      ${item.metrics?.likes ? `<span>👍 ${item.metrics.likes}</span>` : ""}
    </div>
    <div class="title">${escapeHtml(item.title)}</div>
    ${fold}
    <div class="layers">${sections.join("")}${simHtml}</div>
    <div class="actions">
      <a class="btn btn-sm" href="${escapeHtml(item.url)}" target="_blank" rel="noopener">原文</a>
      <button class="btn btn-sm btn-secondary" data-save="${escapeHtml(item.url)}">收录</button>
      <button class="${feedbackBtnClass(itemRating === "useful", "btn btn-sm btn-secondary")}" data-base-label="有用" data-feedback="useful" data-id="${item.id}">${feedbackLabel("有用", itemRating === "useful")}</button>
      <button class="${feedbackBtnClass(itemRating === "noise")}" data-base-label="噪音" data-feedback="noise" data-id="${item.id}">${feedbackLabel("噪音", itemRating === "noise")}</button>
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
      const data = await api("POST", "/api/ask", { question: q, run_id: runId });
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
        <td>${escapeHtml(row.event_type)}</td>
        <td>${escapeHtml(row.source || "")}</td>
        <td>${title}</td>
        <td>${row.score}</td>
      </tr>`;
    }).join("")}</tbody></table>`;
  } catch (err) {
    el.innerHTML = `<div class="alert alert-error">${escapeHtml(err.message)}</div>`;
  }
}

/* 画像 */
function initPersona() {
  loadPersona();
  loadPersonaStaleBanner();
  document.getElementById("btn-build-persona")?.addEventListener("click", async () => {
    try {
      const data = await api("POST", "/api/persona/build?review=true");
      showPersonaReview(data);
      alert(`Persona v${data.version} 已生成。可到搜罗页试试画像模拟。`);
      loadPersona();
    } catch (err) { alert(err.message); }
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
      <div class="card"><h2>心智模型</h2><pre>${escapeHtml(JSON.stringify(data.mental_model, null, 2))}</pre></div>
      <div class="card"><h2>Brief</h2><div class="markdown-body" id="persona-brief"></div></div>
      <div class="mt-1">${versions}</div>`;
    renderMarkdown(document.getElementById("persona-brief"), data.brief || "（暂无）");
  } catch (err) {
    el.innerHTML = `<div class="alert alert-error">${escapeHtml(err.message)}</div>`;
  }
}

async function rollbackPersona(version) {
  if (!confirm(`确认回滚到 v${version}？`)) return;
  try {
    const data = await api("POST", "/api/persona/rollback", { version });
    if (data.ok) { alert("回滚成功"); loadPersona(); }
    else alert("版本不存在");
  } catch (err) { alert(err.message); }
}

/* 导入 */
function initIngest() {
  checkAuthBanner();
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
    const progress = document.getElementById("ingest-full-sync-progress");
    if (!el) return;
    el.className = "alert alert-warn mt-1";
    el.textContent = "启动完整同步…";
    if (progress) {
      progress.classList.remove("hidden");
      progress.innerHTML = "";
    }
    const stepLabels = {
      preflight: "Cookie 预检",
      "accounts-sync": "服务端拉取",
      "browser-sync": "浏览器补洞",
      aicu: "AICU 发评",
      "extension-flush": "扩展上报",
    };
    const renderSteps = (steps) => {
      if (!progress || !steps?.length) return;
      progress.innerHTML = steps
        .map((s) => {
          const label = stepLabels[s.step] || s.step;
          const icon = s.ok ? "✓" : s.skipped ? "○" : "…";
          let detail = "";
          if (s.step === "accounts-sync" && s.count != null) detail = ` ${s.count} 条`;
          if (s.step === "browser-sync" && s.accepted != null) {
            detail = ` ${s.accepted} 条`;
            if (s.mode_used) detail += ` (${s.mode_used})`;
          }
          if (s.skipped) detail = ` 跳过`;
          return `<div>${icon} ${escapeHtml(label)}${escapeHtml(detail)}</div>`;
        })
        .join("");
    };
    try {
      const start = await api("POST", "/api/ingest/full-sync");
      const jobId = start.job_id;
      if (!jobId) throw new Error("未返回 job_id");
      for (let i = 0; i < 180; i += 1) {
        await new Promise((r) => setTimeout(r, 2500));
        const job = await api("GET", `/api/ingest/full-sync/${jobId}`);
        if (job.steps?.length) renderSteps(job.steps);
        if (job.status === "running") continue;
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
          if (job.steps?.length) renderSteps(job.steps);
          loadIngestHealth();
          return;
        }
        throw new Error(job.detail || "同步失败");
      }
      el.className = "alert alert-error mt-1";
      el.textContent = "超时（>7.5 分钟）。请稍后重试。";
    } catch (err) {
      el.className = "alert alert-error mt-1";
      el.textContent = err.message;
    }
  });
  document.getElementById("btn-ingest-accounts-sync")?.addEventListener("click", async () => {
    const el = document.getElementById("ingest-accounts-sync-result");
    if (!el) return;
    el.className = "alert alert-warn mt-1";
    el.textContent = "检查 Cookie…";
    try {
      const pre = await api("GET", "/api/ingest/preflight");
      if (!pre.ready) {
        el.className = "alert alert-error mt-1";
        el.innerHTML = `${(pre.hints || ["Cookie 未就绪"]).map(escapeHtml).join("<br>")}<br><a href="/settings">去设置页同步 Cookie</a>（需先完全关闭 Edge）`;
        return;
      }
      el.textContent = "服务端拉取中…全量约需 2–4 分钟，请耐心等待";
      const ctrl = new AbortController();
      const timer = setTimeout(() => ctrl.abort(), 360000);
      const res = await fetch("/api/ingest/accounts-sync", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: ctrl.signal,
      });
      clearTimeout(timer);
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
    } catch (err) {
      el.className = "alert alert-error mt-1";
      el.textContent = err.name === "AbortError" ? "请求超时（>6 分钟）。请确认用 start-osint-web.bat 启动后重试。" : err.message;
    }
  });
  document.getElementById("btn-ingest-browser-sync")?.addEventListener("click", async () => {
    const el = document.getElementById("ingest-browser-sync-result");
    if (!el) return;
    el.className = "alert alert-warn mt-1";
    el.textContent = "检查 Playwright…";
    try {
      const st = await api("GET", "/api/ingest/browser-sync/status");
      if (!st.playwright_installed) {
        el.className = "alert alert-error mt-1";
        el.innerHTML =
          "未安装 Playwright。请运行 <code>scripts/install-browser-sync.ps1</code> 后重试。";
        return;
      }
      el.textContent = "浏览器会话同步中…（Edge 开着也能用，约 2–5 分钟）";
      const start = await api("POST", "/api/ingest/browser-sync", {
        platforms: ["bilibili", "zhihu"],
      });
      const jobId = start.job_id;
      if (!jobId) throw new Error("未返回 job_id");
      for (let i = 0; i < 120; i += 1) {
        await new Promise((r) => setTimeout(r, 2500));
        const job = await api("GET", `/api/ingest/browser-sync/${jobId}`);
        if (job.status === "running") continue;
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
    const connected = data.connected ? "已连接" : "未检测到扩展";
    const total = data.extension_event_count || 0;
    const types = Object.entries(data.event_totals || {})
      .map(([k, v]) => `${k}:${v}`)
      .join("，");
    el.innerHTML = `<strong>${connected}</strong> · 扩展事件 ${total} 条${types ? `<br><span class="muted">${escapeHtml(types)}</span>` : ""}${data.last_seen ? `<br><span class="muted">最近同步 ${escapeHtml(String(data.last_seen).slice(0, 19))}</span>` : ""}`;
  } catch (err) {
    el.textContent = `无法连接 Web 服务：${err.message}`;
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
      .map(([k, v]) => `${escapeHtml(k)}: ${v.ok ? "✓" : "✗"}`)
      .join(" · ");
    const events = data.events?.total ?? 0;
    const coverage = (data.coverage || [])
      .map((p) => {
        const behaviors = (p.behaviors || [])
          .filter((b) => b.count > 0)
          .map((b) => `${escapeHtml(b.behavior)} ${b.count}`)
          .join("，");
        return `<div><strong>${escapeHtml(p.platform)}</strong> ${p.total} 条${behaviors ? ` — ${behaviors}` : ""}</div>`;
      })
      .join("");
    const statusClass = data.ok ? "alert-success" : "alert-warn";
    el.innerHTML = `
      <div class="alert ${statusClass}">${data.ok ? "就绪" : "存在阻塞项"} · 事件 ${events} 条 · ${auth}</div>
      ${blockers ? `<ul class="health-list">${blockers}</ul>` : ""}
      ${warnings ? `<ul class="health-list muted">${warnings}</ul>` : ""}
      <div class="mt-1">${coverage || "<span class='muted'>暂无平台覆盖数据，请先完整同步</span>"}</div>
      <div class="muted mt-1">Playwright: ${data.playwright_installed ? "已安装" : "未安装"} · partial 能力 ${data.partial_capabilities || 0} 项</div>`;
  } catch (err) {
    el.textContent = `无法加载健康状态：${err.message}`;
  }
}

async function loadIngestCapabilities() {
  const el = document.getElementById("ingest-capabilities");
  if (!el) return;
  try {
    const data = await api("GET", "/api/ingest/capabilities");
    const rows = (data.items || [])
      .map(
        (i) =>
          `<tr><td>${escapeHtml(i.platform)}</td><td>${escapeHtml(i.behavior)}</td><td>${escapeHtml(i.status)}</td><td class="muted">${escapeHtml(i.note)}</td></tr>`
      )
      .join("");
    el.innerHTML = `<table class="data-table"><thead><tr><th>平台</th><th>行为</th><th>状态</th><th>说明</th></tr></thead><tbody>${rows}</tbody></table>`;
  } catch (_) {
    el.textContent = "无法加载能力说明";
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
        aicu_disabled: "请先在 config 中设置 ingest.aicu_enabled: true",
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
    el.innerHTML = `<table class="table"><thead><tr><th>Run ID</th><th>命令</th><th>话题</th></tr></thead><tbody>${
      data.runs.map((r) =>
        `<tr><td><a href="/runs/${r.run_id}">${escapeHtml(r.run_id)}</a></td>
        <td>${escapeHtml(r.command || "")}</td><td>${escapeHtml(r.query || "")}</td></tr>`
      ).join("")
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
  loadAuthStatus();
  loadPaths();
  document.getElementById("btn-sync-cookies")?.addEventListener("click", syncCookies);
  document.getElementById("btn-domain-lookup")?.addEventListener("click", lookupDomain);
  document.getElementById("btn-copy-edge-cdp")?.addEventListener("click", () => {
    const pre = document.getElementById("edge-cdp-cmd");
    if (!pre) return;
    const text = pre.textContent.replace(/&amp;/g, "&");
    navigator.clipboard.writeText(text).then(() => alert("已复制 Edge CDP 启动命令"));
  });
}

async function loadAuthStatus() {
  const el = document.getElementById("auth-status");
  if (!el) return;
  try {
    const data = await api("GET", "/api/auth/status");
    el.innerHTML = `<table class="table"><thead><tr><th>项目</th><th>状态</th><th>说明</th></tr></thead><tbody>${
      data.items.map((i) =>
        `<tr><td>${escapeHtml(i.name)}</td>
        <td class="${i.ok ? "status-ok" : "status-fail"}">${i.ok ? "通过" : "失败"}</td>
        <td>${escapeHtml(i.detail || "")}</td></tr>`
      ).join("")
    }</tbody></table>`;
  } catch (err) {
    el.innerHTML = err.message;
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
