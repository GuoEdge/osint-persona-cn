# 个人情报系统架构

本地优先的个人 OSINT 工作台：浏览器/账号数据 → 行为事件库 → 心智画像 → AI 赋能搜罗/问答/简报 → 知识沉淀与审计。

## 数据流

```
浏览器扩展 / 行为导入 / 手动收录
        ↓
  SQLite events + intel_items (~/.osint/knowledge.db)
        ↓
  心智画像 persona/ (mental_model + brief)
        ↓
  搜罗 pipeline → runs/{run_id}/ (manifest, steps, report.md)
        ↓
  Web UI (:8787) / CLI (osint)
```

## 入口

| 入口 | 路径 | 启动 |
|------|------|------|
| CLI | `src/osint_toolkit/cli.py` | `osint` |
| Web | `src/osint_toolkit/web/app.py` | `osint web` → `http://127.0.0.1:8787` |
| 扩展 | `extension/` | 加载已解压扩展，POST `/api/extension/events` |

## 核心模块

| 层级 | 模块 |
|------|------|
| 采集 | `services/extension.py`, `services/ingest.py`, `ingest/*` |
| 存储 | `storage/sqlite.py`, `storage/knowledge.py` |
| 画像 | `persona/context.py`, `persona/builder.py`, `persona/auto_rebuild.py` |
| 情报 | `services/search.py`, `services/ask.py`, `ai/*` |
| Web | `web/routes/pages.py`, `web/routes/api.py`, `web/static/app.js` |

## 页面 → API

| 页面 | 主要 API |
|------|----------|
| 搜罗 `/` | `POST /api/search`, `GET /api/search/{id}/events`, `POST /api/ask` |
| 收录 `/save` | `POST /api/save` |
| 知识库 `/knowledge` | `GET /api/knowledge/items`, `GET /api/knowledge/recall` |
| 简报 `/digest` | `GET /api/digest/daily`, `GET /api/digest/reports` |
| 扩展与导入 `/ingest` | `POST /api/ingest/*`, `GET /api/extension/status` |
| 行为时间线 `/behavior` | `GET /api/events/recent`, `GET /api/events/insights` |
| 心智画像 `/persona` | `GET/POST /api/persona/*` |
| 运行记录 `/runs` | `GET /api/runs`, `GET /api/runs/{id}` |
| AI 控制 `/ai` | `GET/PUT /api/ai/*` |
| 设置 `/settings` | `GET /api/auth/*` |

## 查询扩展 (Query Expansion)

搜罗前通过 **联网发现 + 合并扩展** 决定关联词：

0. **联网探针**（`ai/alias_discover.py`）：用原查询在 B站/知乎/Web/V2EX 各取若干条标题摘要 → 启发式抽词 + AI **仅从证据**归纳当代称呼（禁编造）→ 合并写入 `~/.osint/entities/discovered.yaml` 供下次复用
1. **实体词表** `~/.osint/entities/*.yaml`（静态补充，示例见 `docs/examples/entities/`）
2. **规则兜底**（中文名简称、小X、酱/碳/女士后缀）
3. **AI query_analyze**（意图与信源策略；扩展词优先级低于联网发现）

配置：`search.discover_aliases`、`discover_probe_limit`、`discover_sources`（含 v2ex）、`persist_discovered_aliases`

`services/search.py` 对 `queries_used` 中每个词并行采集，合并去重后写入 `item.personal.matched_queries`。

预览 API：`POST /api/search/expand`

## 扩展混合同步 (Hybrid Ingest)

**统一配置**：`sync` 段合并原 `extension.sync` 与 `ingest.browser_sync_*`；扩展通过 `GET /api/setup/sync-config` 拉取并写入 `chrome.storage.local.syncConfig`。

**一键完整同步**（Web ingest 页 / `POST /api/ingest/full-sync`）：

1. Cookie preflight
2. `POST /api/ingest/accounts-sync`（B站/知乎 Cookie API）
3. `POST /api/ingest/browser-sync`（Playwright 补洞，可选）
4. AICU 发评（仅 `ingest.aicu_enabled` 且 probe PASS）
5. 提示扩展 flush 上报队列

扩展「服务端拉取 + 轻量补洞」：

1. `POST /api/ingest/bilibili`、`POST /api/ingest/zhihu`（历史/收藏/WBI 点赞/voteanswers/关注）
2. 知乎浏览：服务端 API + browser-sync `recent-viewed` 拦截
3. **Playwright 浏览器会话补洞**：打开 space/dynamic/recent-viewed 页，复用 `capture_patterns` + `extension_events.parse_api_capture`

**AICU 策略**：默认关闭；`scripts/probe_aicu.py` 探测 PASS 后再开启。WAF 拦截时改用 space 页 + reply API 补洞。

验收：`scripts/web_acceptance.py` → `~/.osint/acceptance/latest.json`

健康面板：`GET /api/ingest/health`（Cookie、Playwright、events 覆盖度）

### Playwright 补洞

- 安装：`scripts/install-browser-sync.ps1` 或 `pip install -e ".[browser]"`
- CLI：`osint ingest browser-sync` / `browser-sync.bat`
- **auto**（默认）：Persistent 失败时自动 Cookie 模式
- **CDP**：`sync.browser_sync_mode: cdp`，Edge `--remote-debugging-port=9222`
- `sync.browser_sync_after_api: true` 时 accounts-sync 后自动补洞

```yaml
sync:
  prefer_server_api: true
  browser_sync_after_api: true
  browser_sync_mode: auto
  max_pages_per_run: 6
  scroll_rounds: 4
  page_gap_ms: 8000
  aicu_enabled: false

profiles:
  default:
    sources: [zhihu, bilibili, web, v2ex]
  full:
    sources: [zhihu, bilibili, web, v2ex, rss]
```

## 评论挖掘 (Comment Mining)

搜索流水线：`dedup → mine_comments → summarize → report`

- 默认对 top N 条结果按信源分配配额拉取热评（`search.comment_mine_top`）
- 支持 **B站**（视频 type=1、专栏 type=12、opus type=17）与 **知乎**（回答/文章 comment_v5）
- `services/save.py` 的 `with_comments` 同样支持双平台

## 配置 (`~/.osint/config.yaml` 或 `config/config.yaml`)

```yaml
sync:
  prefer_server_api: true
  browser_sync_after_api: true
  browser_sync_mode: auto
  max_pages_per_run: 6
  aicu_enabled: false

ai:
  persona_inject: true
  dwell_save_no_ai: true
  auto_persona_rebuild: prompt
  auto_persona_rebuild_threshold: 50

search:
  max_expanded_queries: 8
  comment_mine_top: 3
  discover_sources: [bilibili, zhihu, web, v2ex]

ingest:
  aicu_enabled: false
  browser_sync_enabled: true
```

配置加载顺序：内置默认值 → 项目 `config/config.yaml` → 用户 `~/.osint/config.yaml`（后者覆盖叶子节点）。Legacy `extension.sync` / `ingest.browser_sync_*` 只读合并到 `load_sync_config()`。

## 扩展安装

1. `osint web` 启动本地服务（8787）
2. Edge/Chrome → 扩展 → 加载已解压 → 选择仓库 `extension/` 目录
3. 保持弹窗开关开启；日常浏览自动同步事件

## 用户旅程

1. **采集**：安装扩展 + 可选批量导入（B站/知乎/浏览器历史）
2. **画像**：构建心智画像（行为达阈值后 prompt/auto 重建）
3. **搜罗**：多源采集 + AI 摘要 + 画像模拟 + 情报报告
4. **沉淀**：收录到知识库、生成每日简报、审计运行记录
