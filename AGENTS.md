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

```bash
pytest                                    # 全量
pytest tests/test_search_session.py -q    # 会话相关
pytest tests/test_bilibili_sdk.py -q      # B站 SDK
pytest tests/test_extension_events.py -q  # 扩展解析
```

- 新增逻辑应有单元测试；API 用 `TestClient`（见 `tests/test_web_api.py`）
- 依赖真实 Edge/Playwright 的用 `@pytest.mark.integration`
- 改 `app.js` 后提醒用户 **Ctrl+F5**；改扩展需 **重新加载扩展**

## 提交与 PR 规范

- Conventional Commits：`feat:` / `fix:` / `docs:` / `test:` / `refactor:`
- 运行 `pytest` + `ruff check` 后再 PR
- **绝不提交**：`.env`、`~/.osint` 内容、真实 API Key、Cookie 文件
- 配置示例只改 `config/config.example.yaml`，用 `${ENV_VAR}` 占位

## AI 维护时的注意点

1. **最小改动**：搜罗参数泄漏曾导致 `tree_id` 传入 `run_search` 报错；改 API 时检查 `search_params.py` 边界。
2. **Cookie 与 WBI**：B站/知乎接口常变；失败时优先 WBI 回退、扩展补洞，而非硬爬页面。
3. **SQLite 并发**：扩展 auto-save 不得在持有 DB 连接时 `await` 长时间 `save_url`；见 `services/extension.py` WAL 模式。
4. **扩展队列**：`extension/lib/queue.js` 分批 POST（默认 25 条/批），勿恢复单次 500 条上传。
5. **工作台布局**：搜罗页为分区 Tab（结果/报告/研究树），宽屏可选分屏；勿恢复三列挤版。
6. **文档同步**：用户可见能力变更时更新 `docs/CAPABILITIES.md` 与 README 功能列表。

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

- [docs/CAPABILITIES.md](docs/CAPABILITIES.md) — 功能能力矩阵与限制
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — 数据流与模块图
- [docs/AI_CONTROL.md](docs/AI_CONTROL.md) — AI 导向与 prompt 覆盖
- [docs/PRIVACY.md](docs/PRIVACY.md) — 隐私与本地数据
- [extension/README.md](extension/README.md) — 扩展安装与同步
- [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) — 贡献流程
