async function loadStatus() {
  const statusEl = document.getElementById("status");
  const enabledEl = document.getElementById("enabled");
  const passiveEl = document.getElementById("passive");
  const bgEl = document.getElementById("background-sync");
  const platformsEl = document.getElementById("platforms");

  const resp = await chrome.runtime.sendMessage({ kind: "get_status" });
  enabledEl.checked = resp.enabled !== false;
  passiveEl.checked = resp.passiveCollect !== false;
  bgEl.checked = resp.backgroundSync !== false;

  const stats = resp.stats || {};
  const pending = resp.pendingQueue || 0;
  statusEl.textContent = [
    `API: ${resp.apiBase || "http://127.0.0.1:8787"}`,
    `待上传 ${pending} 条`,
    stats.lastFlush ? `上次上传 ${stats.lastFlush.slice(0, 19)}` : "",
    stats.lastAccepted != null ? `写入 ${stats.lastAccepted}` : "",
  ]
    .filter(Boolean)
    .join(" · ");

  if (resp.platforms) {
    platformsEl.textContent = `覆盖: ${resp.platforms.join("、")}`;
  }
}

document.getElementById("enabled").addEventListener("change", async (e) => {
  await chrome.runtime.sendMessage({ kind: "set_enabled", enabled: e.target.checked });
});

document.getElementById("passive").addEventListener("change", async (e) => {
  await chrome.runtime.sendMessage({ kind: "set_passive", enabled: e.target.checked });
});

document.getElementById("background-sync").addEventListener("change", async (e) => {
  await chrome.runtime.sendMessage({ kind: "set_background_sync", enabled: e.target.checked });
});

document.getElementById("sync-cookies").addEventListener("click", async () => {
  const statusEl = document.getElementById("status");
  statusEl.title = "";
  statusEl.textContent = "从 Edge 读取 Cookie 并写入本机…";
  const result = await chrome.runtime.sendMessage({ kind: "sync_cookies" });
  if (!result) {
    statusEl.textContent = "无响应：请重载扩展 v0.2.6+";
    return;
  }
  if (result.error) {
    statusEl.textContent = result.error;
    return;
  }
  const synced = (result.domains_synced || []).join("、") || "无";
  statusEl.textContent = `Cookie 已同步: ${synced}`;
});

document.getElementById("flush").addEventListener("click", async () => {
  const statusEl = document.getElementById("status");
  statusEl.textContent = "上传浏览采集队列…";
  const result = await chrome.runtime.sendMessage({ kind: "flush_now" });
  if (result.error) {
    let hint = "";
    if (/HTTP 5\d\d/i.test(result.error)) {
      hint = "（Web 已在运行但处理出错：请重启情报台并重新加载扩展 v0.2.9+）";
    } else if (/fetch|failed|network|连接|refused|timeout/i.test(result.error)) {
      hint = "（请先运行 start-osint-web.bat）";
    }
    statusEl.textContent = `失败: ${result.error}${hint}`;
    return;
  }
  if (result.empty) {
    statusEl.textContent =
      "队列为空（正常）。服务端拉取的数据已直接写入；请刷 B站/知乎 后再上传，或等每分钟自动上传。";
    loadStatus();
    return;
  }
  statusEl.textContent = `上传完成：写入 ${result.accepted || 0}，跳过重复 ${result.skipped || 0}`;
  if (result.saved_to_knowledge) {
    statusEl.textContent += `，知识库 ${result.saved_to_knowledge}`;
  }
  loadStatus();
});

document.getElementById("sync-aicu").addEventListener("click", async () => {
  const statusEl = document.getElementById("status");
  statusEl.textContent = "从 AICU 拉取发评中…将使用 aicu.cc 页面会话（若未打开会自动打开该站）";
  const result = await chrome.runtime.sendMessage({ kind: "sync_aicu" });
  if (!result) {
    statusEl.textContent = "无响应：请在 chrome://extensions 重载扩展 v0.2.7+";
    return;
  }
  if (result.error) {
    statusEl.textContent = result.error;
    return;
  }
  if (result.ok === false) {
    statusEl.textContent = result.error || "导入失败";
    return;
  }
  statusEl.textContent = `AICU 导入 ${result.count || 0} 条（跳过重复 ${result.skipped || 0}，UID ${result.mid || "?"})`;
});

document.getElementById("sync-now").addEventListener("click", async () => {
  const statusEl = document.getElementById("status");
  statusEl.title = "";
  statusEl.textContent = "服务端 Cookie 拉取中…（需先启动本机 Web 并同步 Cookie）";
  let result;
  try {
    result = await chrome.runtime.sendMessage({ kind: "sync_now" });
  } catch (e) {
    statusEl.textContent = `失败: ${e.message || e}`;
    return;
  }
  if (!result) {
    statusEl.textContent = "无响应：请重载扩展后重试";
    return;
  }
  if (result.error) {
    statusEl.textContent = result.error;
    return;
  }
  const bili = result?.stats?.server?.bilibili;
  const zh = result?.stats?.server?.zhihu;
  const parts = [];
  if (bili) {
    const d = [`B站 ${bili.count ?? 0}`];
    if (bili.following_count != null) d.push(`关注${bili.following_count}`);
    parts.push(d.join("/"));
  }
  if (zh) {
    const d = [`知乎 ${zh.count ?? 0}`];
    if (zh.activity_count != null) d.push(`动态${zh.activity_count}`);
    parts.push(d.join("/"));
  }
  if (result?.stats?.scroll?.pages) parts.push(`自动补洞 ${result.stats.scroll.pages} 页`);
  statusEl.textContent = parts.length ? `拉取完成：${parts.join("，")}` : "拉取完成（0 条，请先设置页同步 Cookie）";
  if (result?.warnings?.length) {
    statusEl.textContent += ` · 警告 ${result.warnings.length}`;
    statusEl.title = result.warnings.join("\n");
  }
  loadStatus();
});

loadStatus();
