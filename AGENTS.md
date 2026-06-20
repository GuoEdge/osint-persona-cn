# AI / Maintainer Guide — OSINT Toolkit（个人情报台）

本文档面向 **继续用 AI 或人工维护本仓库的开发者**。阅读顺序建议：本文件 → `docs/ARCHITECTURE.md` → `docs/CAPABILITIES.md`。

## 项目是什么

**OSINT Toolkit（个人情报台 / osint-persona-cn）** 是本地优先的中文互联网个人情报工作台：

- 从知乎、B站、微信（搜狗）、Web、V2EX、RSS 等多源 **搜罗** 话题相关信息
- 将浏览器行为、账号 API、扩展拦截 **导入** 为 SQLite 事件库
- 用 DeepSeek 做摘要、情报报告、画像模拟、研究树归纳
- 通过 Web UI（`:8787`）与 CLI（`osint`）操作，数据落在 `~/.osint/`

**不是**：多用户 SaaS、推荐系统、或无法审计的黑盒 Agent。搜罗 pipeline 的每一步产物写入 `runs/{run_id}/`。

## 仓库结构

```
gochj/
├── src/osint_toolkit/          # Python 包（pip install -e .）
│   ├── cli.py                  # Click CLI 入口
│   ├── collectors/             # 各信源搜罗实现
│   ├── ingest/                 # 行为/账号导入、扩展事件解析
│   ├── pipeline/               # 进度、trace、runner
│   ├── services/               # search, ingest, persona, extension, save…
│   ├── ai/                     # DeepSeek 客户端与各 AI 步骤
│   ├── persona/                # 心智画像构建与注入
│   ├── research/               # 研究树 JSON 持久化
│   ├── storage/                # SQLite + FTS 知识库
│   ├── web/                    # FastAPI + Jinja + app.js
│   └── auth/                   # Cookie 同步、数据目录
├── extension/                  # Chrome MV3 扩展（被动采集 + Cookie 同步）
├── config/config.example.yaml  # 配置模板（复制到 ~/.osint/config.yaml）
├── docs/                       # 架构、能力、贡献、隐私
├── tests/                      # pytest（目标：改动后全绿）
└── scripts/                    # 验收、探测脚本
```

## 开发环境

```bash
cd gochj
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -e ".[dev,web,bilibili]"   # 按需加 [browser]
pytest
ruff check src tests
ruff format src tests
```

- **Python**：`>=3.10,<3.14`（推荐 3.12；3.14 下 `rookiepy` 可能不可用）
- **Web**：`osint web` 或 `启动情报台.bat` → http://127.0.0.1:8787
- **扩展**：`chrome://extensions` 加载 `extension/` 目录

## 本地数据（勿提交 Git）

| 路径 | 内容 |
|------|------|
| `~/.osint/config.yaml` | API Key、用户配置 |
| `~/.osint/cookies/` | 各域 Cookie JSON |
| `~/.osint/knowledge.db` | 事件、知识库 FTS |
| `~/.osint/runs/{run_id}/` | 搜罗产物（manifest、steps、report.md） |
| `~/.osint/persona/` | mental_model.yaml、brief |
| `~/.osint/research/trees/` | 研究树 JSON |
| `~/.osint/entities/` | 实体词表、联网发现别名 |

环境变量 `OSINT_DATA_DIR` 可覆盖默认 `~/.osint`。

## 搜罗 Pipeline（修改搜索行为时必读）

入口：`services/search.py` → `pipeline/runner.py`

典型步骤顺序：

1. `alias_discover` — 联网探针 + AI 归纳别名（可 `--no-ai-step` 禁用）
2. `foreign_expand` — 国际信源英文检索词拓展与国际网络探针（`search.foreign_expand.*`、`http.proxy`；可在 **设置 → 运行参数 → 外文信源** 调整）
3. `ai_query_analyze` — 意图与信源策略（含外文词合并进 `queries_by_source`）
4. `collect_all` — 各 collector 并行，多 `queries_used` 合并去重
5. `dedup` — `analyzers/dedup.py`
6. `mine_comments` — B站字幕/弹幕/热评、知乎评论（`comment_mine_top`）
7. `ai_summarize` — 条目摘要
8. `persona_simulate` — 画像模拟点击（需已构建 persona）
9. `ai_report` — 情报报告（需 `--digest` / Web 勾选）

**会话字段与 pipeline 参数分离**：`tree_id`、`parent_node_id`、`fork_from_run_id` 等属于 session，不得传入 `run_search()`。边界在 `services/search_params.py` 的 `strip_session_keys()`。

**进度与恢复**：`services/run_session.py` + `pipeline/progress.py`；Web 通过 SSE `GET /api/search/{id}/events` 与轮询 `progress.json`。

## Web API 约定

- 路由定义：`web/routes/api.py`（前缀 `/api`）
- 请求体模型：`web/schemas.py`
- 长任务：`web/tasks.py` 注册 job；`GET /api/jobs/active` 查进行中任务
- 扩展批次：`POST /api/extension/events`（`services/extension.py`）

新增 API 时：补 Pydantic schema、在 `api.py` 注册、必要时在 `app.js` 接前端、加 `tests/test_*_api.py`。

## 行为导入（Ingest）

| 模式 | 入口 | 说明 |
|------|------|------|
| 完整同步 | `osint sync` / `POST /api/ingest/full-sync` | preflight → accounts-sync → browser-sync → 可选 AICU |
| 账号 API | `ingest/bilibili_account.py`, `zhihu_account.py` | Cookie 拉取历史/收藏/点赞/关注 |
| 增量游标 | `ingest/account_sync_state.py` | B站 accounts-sync 只导入新事件 |
| 扩展 | `ingest/extension_events.py` | 解析拦截 API、page_visit、dwell_save |
| Playwright 补洞 | `ingest/browser_sync.py` | 打开空间页拦截 JSON |

## 研究树

- 存储：`research/tree.py` → `~/.osint/research/trees/{id}.json`
- 节点类型：`topic` | `search` | `note` | `insight` | `ask`
- AI：`services/research_ai.py`（归纳要点、建议查询）
- 前端：`web/static/app.js` 中 `workspaceSession`、`refreshResearchTree`
- 搜罗挂载：`POST /api/search` 传 `tree_id` / `create_tree`；分叉用 `fork_from_run_id` + `search_fork.py`

## 常见修改场景

| 目标 | 主要文件 |
|------|----------|
| 新搜罗源 | `collectors/new.py` + `registry.py` + `config.example.yaml` profiles |
| 新 ingest 行为 | `ingest/` + `extension_events.py` + `ingest_capabilities.py` |
| 调整 AI 提示 | `ai/prompt_loader.py`、`~/.osint/prompts/*.md`、`ai/steering.py` |
| B站字幕/弹幕 | `ingest/bilibili_sdk.py` `fetch_subtitle_for_url`、collectors `enrich_video` |
| 扩展新平台 | `extension/lib/platforms.js` + `capture_patterns.py` |
| 工作台 UI | `workspace.html` + `app.js` + `app.css` |

## 测试

测试分三层，AI 修改代码后**必须跑对应层**，不能只跑 lint。

### 第一层：代码健全（任何修改后必跑）

覆盖：系统可导入、pipeline 参数不泄漏、搜索排队、认证门禁、信源路由/规划、信号/去重、AI 客户端/导向、存储/连接池、Web API/鉴权、配置读写、画像构建/注入、搜索端到端产出、HTTP 反爬、画像模拟。

```bash
pytest tests/test_system_consistency.py tests/test_config.py \
       tests/test_search_session.py tests/test_search_task_queue.py \
       tests/test_source_preflight.py tests/test_source_routing.py \
       tests/test_source_planner.py tests/test_analyzers.py \
       tests/test_ai_client.py tests/test_steering.py \
       tests/test_storage.py tests/test_sqlite_pool.py \
       tests/test_web_api.py tests/test_web_token.py \
       tests/test_tunable_config.py tests/test_persona_builder.py \
       tests/test_persona_context.py tests/test_delivery_api_smoke.py \
       tests/test_http_client_referer.py tests/test_pipeline.py \
       tests/test_pipeline_integration.py tests/test_persona_sim.py \
       tests/test_search_service.py -q
```

### 第二层：数据质量（改了采集/解析/过滤/相关度打分后必跑）

覆盖：去重精度、域名提取、字幕选取、SERP 过滤/解析、知乎 URL 归一化/抓取决策、GitHub 拦截、音乐漂移、微信搜狗解析、别名发现、Composer 路由、AI 相关度精炼、信源规划改进、外文扩展。

```bash
pytest tests/test_dedup.py tests/test_domain.py \
       tests/test_subtitle_pick.py tests/test_serp_filters.py \
       tests/test_serp.py tests/test_zhihu_urls.py \
       tests/test_zhihu_fetch_gate.py tests/test_github_filters.py \
       tests/test_music_drift_filter.py tests/test_weixin_sogou.py \
       tests/test_alias_discover.py tests/test_composer_source_routing.py \
       tests/test_plan_improvements.py tests/test_ai_relevance.py \
       tests/test_foreign_expand.py -q
```

### 第三层：评论抓取 & 行为事件（改了 ingest/扩展/评论/弹幕/微信质量后必跑）

覆盖：知乎评论、B站弹幕、扩展事件解析、行为信号、微信互动。

```bash
pytest tests/test_zhihu_comments.py tests/test_bilibili_danmaku_legacy.py \
       tests/test_extension_events.py tests/test_behavior_signals.py \
       tests/test_weixin_quality.py -q
```

### 全量 & 集成

```bash
pytest                                    # 全量
pytest tests/test_bilibili_sdk.py -q      # B站 SDK
pytest tests/test_bilibili_wbi.py -q      # B站 WBI 签名
pytest tests/test_search_session.py -q    # 会话相关
pytest tests/test_extension_events.py -q  # 扩展解析
```

- 新增逻辑应有单元测试；API 用 `TestClient`（见 `tests/test_web_api.py`）
- 依赖真实 Edge/Playwright 的用 `@pytest.mark.integration`
- 改 `app.js` 后提醒用户 **Ctrl+F5**；改扩展需 **重新加载扩展**

## 提交与 PR 规范

- Conventional Commits：`feat:` / `fix:` / `docs:` / `test:` / `refactor:`
- **提交粒度要小**：每个 commit 只改一件事（如 `fix: B站 auth 短路` + `docs: 同步文档` 分开），方便 `git revert` 回滚
- 运行对应层测试 + `ruff check` 后再 PR
- **绝不提交**：`.env`、`~/.osint` 内容、真实 API Key、Cookie 文件
- 配置示例只改 `config/config.example.yaml`，用 `${ENV_VAR}` 占位

## AI 维护时的注意点

> 以下每一行都是踩坑记录，修改前务必扫描一遍，避免踩已修复的坑。

### Pipeline 参数与接口边界

1. **搜罗参数泄漏**：`tree_id`、`parent_node_id`、`fork_from_run_id` 等 session 字段不得传入 `run_search()`。改 `search.py` 入参前先看 `services/search_params.py` 的 `strip_session_keys()`，新字段必须在其中剥离。

2. **分页安全上限**：所有分页循环必须加页数上限（如 `if page > 50: break`），防止 API 返回全重复数据时死循环。B站/知乎收藏/关注、浏览历史等 API 均有实测出现过无限翻页。

### AI 步骤与 Prompt

3. **DeepSeekClient 构造在 try 内**：`DeepSeekClient()` 可能因 API Key 缺失抛异常，必须在 try 块内构造，否则崩溃整条搜索。

4. **AI prompt 必须防幻觉**：所有 AI 摘要/归纳/报告 prompt 必须显式约束模型仅基于提供的正文内容生成，不得引入原文未提及的事件、人物、产品。参见 `prompt_loader.py` 中 `summarize` 和 `report` prompt 的"严格遵守"段落，以及 `steering.py` 的硬约束第 5 条。

5. **AI 返回空内容的兜底**：AI 可能因限流、超时或其他原因返回空字符串或纯空白。存储前必须验证长度（如 `len(summary.strip()) > 10`），空内容不可写入 `item.layers["comments_summary"]` 或 `item.summary`，应回退为原始内容截断或原始评论列表。参见 `analyzers/comments.py` 的 `if not result or not result.strip()` 检查。

6. **注释挖掘的评论归纳必须防幻觉**：评论归纳 prompt 同样需要约束 "仅基于提供的评论内容归纳，不得引入评论中不存在的信息"。AI 返回空时回退到原始评论精选列表，不可造成前端空的"社区观点归纳"区块。

### 外部 API 与网络

7. **Cookie 与 WBI**：B站/知乎接口常变；失败时优先 WBI 回退、扩展补洞，而非硬爬页面。B站 `code=-101` 用 `_check_reply_auth()` 检测。

8. **B站 auth 短路**：首次检测到认证失败（`code=-101/-400/12002` 或含"权限"关键词）后，必须在 class 级别设 `_auth_failed = True` 标记。后续所有评论/弹幕/子回复请求直接返回空，不再发 WBI 或 legacy API。同时用 `_auth_warning_shown` 抑制重复告警，只打一次警告。参见 `collectors/bilibili.py` 的 `_fetch_reply_page` 入口短路和 `_check_reply_auth` 逻辑。

9. **HTTP Referer 反爬**：知乎等平台校验 Referer 头，爬取类请求须附带正确来源。改 `HttpClient` 或 collector 时检查 referer 是否被剥离或错置。参见 `tests/test_http_client_referer.py`。

### 并发与异步

10. **async 端点必须 `asyncio.to_thread`**：`web/routes/api.py` 中所有 `async def` 端点调用同步函数（SQLite、文件 I/O、HTTP）时必须用 `await asyncio.to_thread(fn, ...)` 包裹，否则阻塞事件循环（曾导致行为时间线页超时）。

11. **SQLite 并发**：扩展 auto-save 不得在持有 DB 连接时 `await` 长时间 `save_url`；见 `services/extension.py` WAL 模式。

12. **事件批量写入**：循环 `log_event_deduped()` 已废弃，改用 `log_events_batch([(type, data, key), ...])` 单次连接批量写入。新代码勿恢复 N+1 模式。

13. **搜索取消清理**：`collect_all` 的 `while pending` 循环用 `try/finally` 包裹，确保 `JobCancelled` 时取消所有子任务。

14. **同步状态原子更新**：`_persist_bilibili`/`_persist_zhihu` 用 `sync_state.atomic_update_state(fn)` 做 load→update→save 原子操作；勿恢复裸 `load` + `save` 序列。

### 数据与存储

15. **AI 输出存前验证**：AI 摘要、评论归纳等 AI 输出在存入 `item.layers` 或 `item.summary` 前必须验证非空白且有实际内容长度（如 `> 10` 字符）。空白或过短内容不写入，避免前端渲染空的区块。

16. **扩展队列**：`extension/lib/queue.js` 分批 POST（默认 25 条/批），勿恢复单次 500 条上传。

### 文档与提交

17. **文档同步**：用户可见能力变更（新 prompt 约束、短路逻辑、配置项）必须同步更新 `docs/CAPABILITIES.md` 和 `docs/AI_CONTROL.md`，否则用户不知道功能变了。

18. **AGENTS.md 是活文档**：每次踩到新坑就在本小节加一条，描述具体现象、根因、修复位置。不要只写在 commit message 里，其他人（包括未来的你）看不到。

19. **大改动分多次会话**：不要在一个 session 里改 collector + prompt + API + UI。一次改一个模块，跑完对应层测试再继续。跨越多文件的改动使用 `task` 工具拆分给子 agent。

20. **测试是安全网**：代码改动必须跑对应层测试（见上方的三层测试结构），不能只跑 `ruff check`。改了采集/解析/过滤不跑第二层，线上数据质量会回退且无声。

## 关键配置段（`config.example.yaml`）

| 段 | 用途 |
|----|------|
| `ai` | DeepSeek provider、model、`auto_persona_rebuild` |
| `cookie_sync` | 搜罗前自动 sync、`auto_sync_before_search` |
| `sync` | 完整同步、Playwright、AICU、`browser_sync_after_api` |
| `search` | `comment_mine_top`、知乎 aggressive、SERP、别名发现、`foreign_expand` |
| `http` | `proxy`（国际信源代理；设置页「外文信源」可调） |
| `bilibili` | SDK 开关、字幕/弹幕/评论、WBI 搜索回退 |
| `zhihu` | OpenAPI `access_secret`、热榜、搜索链 |
| `profiles` | default / research / zhihu_deep 信源包 |

用户配置覆盖：`~/.osint/config.yaml`（Web **设置 → 运行参数** 图形化写入，含搜罗并发、知乎 OpenAPI、外文信源、AI 行为等；API `GET/PATCH /api/config/tunables`）。

## 延伸阅读

- [docs/ROADMAP.md](docs/ROADMAP.md) — 维护与改进方向（优先级、路线图、不做什么）
- [docs/CAPABILITIES.md](docs/CAPABILITIES.md) — 功能能力矩阵与限制
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — 数据流与模块图
- [docs/AI_CONTROL.md](docs/AI_CONTROL.md) — AI 导向与 prompt 覆盖
- [docs/PRIVACY.md](docs/PRIVACY.md) — 隐私与本地数据
- [extension/README.md](extension/README.md) — 扩展安装与同步
- [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) — 贡献流程
