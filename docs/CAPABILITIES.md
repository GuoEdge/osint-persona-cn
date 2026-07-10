# 功能与能力说明（个人情报台）

本文档面向 **使用者** 与 **维护者**，说明系统能做什么、依赖什么、以及已知限制。开源协作时请与 `AGENTS.md` 对照阅读。

---

## 1. 产品定位

个人情报台帮助你在 **本机** 完成：

1. **搜罗**：按话题从中文互联网多源采集、去重、AI 摘要，可选生成情报报告  
2. **理解**：用浏览/点赞/收藏等行为构建心智画像，模拟「我会不会点这条」  
3. **沉淀**：收录 URL 进知识库、写研究树笔记、分叉深挖、每日简报，并可同步为 Obsidian 兼容 Markdown vault
4. **审计**：每次搜罗落盘 `~/.osint/runs/{run_id}/`，可回溯每一步 JSON/报告  

默认绑定 `127.0.0.1:8787`，**单用户本地**使用，无账号体系。

---

## 2. 信源与搜罗能力

| 信源 | 搜罗内容 | 典型依赖 |
|------|----------|----------|
| **知乎** | 问答/文章/视频搜索；可选热榜；深度模式展开高赞回答 | Cookie 和/或 [知乎开放平台](https://developer.zhihu.com/) AccessSecret |
| **B站** | 视频/专栏等搜索；热评/字幕/弹幕挖掘（top N） | Cookie；部分接口需 WBI |
| **微信** | 搜狗微信搜索（公众号文章） | 无登录；受搜狗限流影响；**默认拉取阅读量并过滤低质**（`min_read_count`） |
| **Web** | Bing / SerpAPI / SearXNG 等 SERP | 对应 API Key 或自建 SearXNG |
| **V2EX** | 节点帖子搜索（Search API，失败回退 HTML） | 一般无需登录 |
| **GitHub** | 仓库 Search API（不足时回退 `site:github.com`） | 无需 Token（有速率限制） |
| **RSS** | `config.yaml` 中 `rss_feeds` |  feed URL |

**采集深度标注**（搜罗页信源目录与 API `depth` 字段）：

| depth | 含义 |
|-------|------|
| `hybrid` | 原生搜索 + 展开/评论挖掘（知乎、B站） |
| `native` | 独立采集器（如 GitHub API、V2EX API） |
| `serp` | 仅 `site:domain` SERP 摘要；可选 Top-N 正文抓取（`site_fetch_content_top`） |

论坛类 SERP 命中在 `thread_expand_top` 配置下可加深正文；信源规划面板支持 **本次必采 / 本次排除**（`source_overrides`）覆盖 AI 路由。

**扩展信源（SERP `site:domain`）**：在 Web 工作台勾选即可启用，无需单独采集器实现。

| 分类 | 信源 |
|------|------|
| 社交舆情 | 微博、即刻、小红书、脉脉 |
| 社区 | 贴吧、简书、Reddit、NGA |
| 游戏 | 机核 |
| 科技数码 | IT之家、少数派、掘金、Solidot、GitHub、Hacker News、Chiphell、什么值得买 |
| 商业观察 | 36氪、虎嗅、财新、澎湃、凤凰网 |
| 音乐 | 网易云、QQ音乐、酷狗、咪咕 |
| 文化文娱 | 豆瓣、小宇宙、喜马拉雅 |

领域关键词会自动推荐对应信源（如音乐、游戏、社交舆情），见 `source_routing.py`。完整目录：`GET /api/search/source-catalog`。

**查询扩展**：搜罗前可联网发现别名（如角色名、黑称），合并进 `queries_used` 并行采集。预览：`POST /api/search/expand` 或 Web 搜索框下方「关联词」。

**评论/字幕/社区层挖掘**（默认对 **相关度最高的 top 12** 条按源分配配额；信源见 `comment_mine_registry`）：

| 信源 | 挖掘内容 |
|------|----------|
| **B站** | 热评 + AI 归纳；弱简介视频补 **CC/AI 字幕轨**（官方 API）；弹幕 Top 词 + 可选 AI 归纳 |
| **知乎** | 回答/文章热评；深度搜罗可展开高赞回答并独立评论配额 |
| **V2EX** | 帖子回复（show.json API） |

Web 搜罗页勾选「评论与社区层挖掘」；`comment_mine_top` 可在高级选项调整。AI 归纳均标注为社区观点，非事实陈述。

未进入 top N 的长简介 B 站视频可能 **不拉弹幕/热评**；弱简介条目在搜索阶段仍可能补字幕。可对该条点「收录」单独 enrichment。

### 微信质量过滤（`search.weixin`）

搜罗时默认对排名前 **10** 篇尝试打开 `mp.weixin.qq.com` 解析 **阅读量**，并：

- 剔除摘要过短（默认 `< 40` 字）的搜狗结果  
- 剔除阅读量低于 **`min_read_count`（默认 500）** 的文章  
- 对保留条目按阅读量做对数加权，参与去重后排序（高阅读优先进入 AI 摘要预算）  

可在 `~/.osint/config.yaml` 调整：

```yaml
search:
  weixin:
    min_read_count: 500          # 设为 0 则只加权、不硬剔除
    fetch_read_count_top: 10
    drop_unknown_read_count: false  # true 时连无法解析阅读量的也剔除
```

---

## 3. 行为导入与画像

### 3.1 数据来源

| 来源 | 内容 | 入口 |
|------|------|------|
| Edge 浏览历史 | 多站访问记录 | `osint ingest browser` / 完整同步 |
| B站 Cookie API | 观看历史、收藏、点赞、关注 | accounts-sync |
| 知乎 Cookie API | 收藏、关注、我发布的回答/文章/想法；**点赞/活动历史**（`/api/v3/moments/{token}/activities` 反向发现）；**浏览历史**（`/api/v4/unify-consumption/read_history` 反向发现，Edge 历史作为补充） | accounts-sync |
| 浏览器扩展 | 页面访问、停留、API 拦截（含知乎赞同/收藏/关注 POST 拦截）、右键收录、高停留自动入库 | `POST /api/extension/events` |
| Playwright 补洞 | **仅 B 站**空间点赞页等 | browser-sync（知乎自动补洞已停用，见 [ZHIHU_PERSONA.md](ZHIHU_PERSONA.md)） |
| AICU（可选） | 本账号 B站 **发过** 的评论历史 | 需 probe 通过且显式开启 |

### 3.2 推荐流程

```
启动情报台 → 同步 Cookie → 完整同步 → 构建画像 → 搜罗（可勾选画像模拟）
```

- **Cookie**：`osint auth sync-cookies`（需关闭 Edge 后读磁盘）或扩展弹窗同步  
- **完整同步**：Web「行为同步」页一键 / `osint sync`  
- **画像**：`osint persona build` 或 Web「心智画像」；新行为后可半自动重建（`ai.auto_persona_rebuild`）
- 心智画像页现在同时提供“画像证据台”：可查看近期信源分布、行为类型、近 7 日高价值行为、账号清单快照与高兴趣样本，帮助判断画像建立在什么数据上，以及是否存在重复、偏差或遗漏。

### 3.3 心智画像用途

- 搜罗时对条目做 **画像模拟**（是否会点击、简要理由）；模拟失败时在结果卡片显示错误提示
- 注入 AI 报告、追问与研究树 **洞察/建议查询**（`research_ai` + `persona/context.py`）
- `mental_model.yaml` 现在同时保存结构化 persona：`interest_domains`、`active_projects`、`source_preferences`、`knowledge_goals`、`entity_affinities`、`reading_style`、`avoid_patterns`。AI 可增强结构化字段；无 API Key 时用规则版 fallback。
- 版本历史自动只保留最近 10 个版本，避免 persona 目录无限堆积；旧版本仍可在页面中回滚到最近保留范围内。
- 搜罗前的 `local_context.json` 会携带结构化 persona，供查询分析、信源规划、知识库问答和研究建议读取，不再只依赖 Markdown brief。
- `local_context.json` 还会额外携带相关概念、研究项目与知识缺口问题，供 AI 在“继续搜什么”“补哪块盲区”时参考，但不会直接替你删结果或改排序。
- 已有画像用户进入搜罗页时 **默认开启** 画像模拟（可手动勾选「跳过画像模拟」）
- **不**用于对外推荐流；仅供个人情报分析

---

## 4. Web 界面一览

| 页面 | 路径 | 作用 |
|------|------|------|
| 搜罗 | `/` | 多源搜索、情报报告（本轮）、研究树、话题监视、过程时间线 |
| 知识库 | `/knowledge` | 混合检索已收录条目，查看概念/实体/项目图谱、知识缺口、关联扩展、命中解释、知识库追问与 Markdown vault 状态/冲突 |
| 简报 | `/digest` | **每日简报**（与搜罗页「本轮情报报告」不同） |
| 行为同步 | `/ingest` | 预检、完整同步、扩展状态 |
| 行为时间线 | `/behavior` | 近期 events 浏览 |
| 心智画像 | `/persona` | 查看/构建/回滚画像 |
| 运行记录 | `/runs` | 历次搜罗产物与 trace |
| AI 控制 | `/ai` | `ai_directives`、prompt 覆盖 |
| 设置 | `/settings` | API Key、Cookie 同步、依赖检查 |

### 搜罗模式（`profiles`）

搜罗页 **「搜罗模式」** 下拉框决定默认启用的信源组合（切换时会同步勾选上方来源）。各模式 **共用同一套 pipeline**（别名发现、去重、AI 摘要、报告、评论与社区层挖掘等），差异主要在 **信源范围** 与 **画像模拟默认值**：

| 模式 | 信源 | 适用场景 | 与其他模式的差异 |
|------|------|----------|------------------|
| **默认** | 知乎、B站、网页、微信 | 日常话题、人物/事件速览 | 含微信（带阅读量过滤）；画像模拟由「更多选项」决定 |
| **全量** | 上述 + V2EX + RSS | 需要社区帖与订阅源 | 请求更多、耗时更长；RSS 来自 `rss_feeds` 配置 |
| **深度研究** | 知乎、B站、V2EX、网页（无微信） | 技术/社区课题 | 减少公众号干扰；**默认开启画像模拟** |
| **知乎深挖** | 仅知乎 | 问答、观点型话题 | 单源更快；走全局知乎深度配置；**默认关闭画像模拟** |

可在 `~/.osint/config.yaml` 的 `profiles:` 下自定义模式（`sources`、`label`、`summary`、`simulate_persona`）。CLI：`osint search "话题" --profile research`。

### 证据链与引用（搜罗报告）

- 每条去重结果分配稳定 **`citation_id`**（如 `c1`、`c2`），写入 `personal.citation_id` 与 `citation_map`
- 情报报告 prompt 要求正文使用 **`[cN]`** 引用；无 AI 时的 fallback 报告同样带引用
- Web 报告区点击 `[cN]` 可滚动定位到对应结果卡片
- 运行记录详情页展示采集 **警告**（`source_warnings`）与 **错误**（`source_errors`）分块

### 搜罗 → 知识库闭环

- 单条收录：结果卡片「收录」或 `POST /api/save`
- **批量收录**：`POST /api/search/{run_id}/save-items`，body 可选 `item_ids`、`min_relevance`、`tags`；工作区工具栏「收录本轮精选」
- 批量收录优先读取 `items_final.json`（含评论/字幕/摘要等后处理层），若不存在才回退 `items_dedup.json` / `items_raw.json`
- 收录条目写入 `personal.run_id` / `citation_id` 便于溯源

### Markdown vault 与云端文件夹

- 可在设置页或 `osint cloud init` 配置 `knowledge.cloud.vault_path`，推荐指向 OneDrive、Dropbox、iCloud、Syncthing 等同步文件夹。
- 收录、高停留自动收录、批量收录始终先写入 SQLite 索引；若 `sync_mode=passive` 会即时生成 Obsidian 兼容 Markdown 笔记，若为 `manual/scheduled` 则先进入待同步队列，等 `osint cloud sync` 再统一写入 vault。
- Vault 目录包含 `Inbox/`、`Sources/`、`Topics/`、`Entities/`、`Concepts/`、`Projects/`、`Daily/`、`Runs/`、`Attachments/` 与 `_osint/index.json`、`graph.json`、`sync-state.json`。
- Markdown frontmatter 会保留 `concepts`、`claims`、`questions`、`relations`、`project`、`confidence`、`evidence_refs`；正文使用 Obsidian wiki link 连接 `Topics/`、`Entities/`、`Concepts/`、`Projects/`。
- SQLite、Cookie、API Key、原始行为事件默认仍留在 `~/.osint/`，不直接放进云同步目录；新设备可用 `osint cloud reindex` 从 vault 重建本地索引。
- 若用户手改 Markdown，系统检测到 `content_hash` 变化后会保留冲突副本，不覆盖用户内容；Web 知识库页和 `osint cloud conflicts` 可查看冲突。
- 知识库页和 `osint cloud status` 会额外显示 vault 健康信息：是否位于 OneDrive 目录、目录结构是否完整、是否存在长路径/冲突风险、`sync-state.json` 是否存在。
- `osint cloud init` / Web 初始化现在支持多 OneDrive 根目录选择、vault 名称选择和同步模式选择，避免默认写入错误的同步盘位置。
- `osint cloud reindex` 现在会清理 vault 中已不存在、但本地仍残留的旧同步条目，让“云端 vault 是长期资产、本地 SQLite 是可重建索引”的语义更完整。
- `rclone`、`webdav`、`syncthing`、`git` 目前作为配置枚举保留；v1 实际同步依赖这些工具各自的本地同步文件夹或挂载目录。

### 知识库检索与利用

- 统一检索默认走 `hybrid`：综合 FTS、关键词字段、主题/实体/标签命中、时间衰减、停留时长、收录方式与历史反馈，返回可解释分数与命中原因。
- 中文自然句提问会拆成可检索片段，避免整句无法命中；知识库问答和本地上下文注入都复用同一检索层。
- 知识库“检索”本身不调用 AI；“问知识库”则是先本地召回，再由 AI 基于命中内容生成回答。若未配置 API Key 或 AI 失败，会自动回退为本地证据式回答。
- 所有通过 `DeepSeekClient` 发起的 AI 调用现在会落本地台账：记录任务类型、模型、成功/失败、耗时、输入输出规模，便于后续优化 AI 成本与效果。
- 收录后会进入 `knowledge_enrich`：规则抽取主题、实体、概念、观点、问题和项目，写入 `knowledge_concepts`、`knowledge_item_concepts`、`knowledge_relations`。规则高置信关系为 `confirmed`；AI 候选关系后续以 `suggested` 接入，必须带 `evidence`。
- 知识图谱支持 `mentions_entity`、`explains`、`extends`、`source_of`、`belongs_to_project`，并保留旧 `knowledge_links` 的 `same_topic` / `same_entity` 一跳扩展。
- 知识库页可按来源、主题、实体、标签与冲突状态过滤，图谱页可查看概念/实体/项目节点、关系证据和“后续研究问题”。
- 搜罗完成后会额外生成 `knowledge_audit.json`：标记每条结果是“库中已有”“补充旧知识”还是“可挂到研究项目”，并给出概念命中与后续问题，方便马上进入研究循环。
- API / CLI：`GET /api/knowledge/search`、`GET /api/knowledge/graph`、`GET /api/knowledge/items/{item_id}/graph`、`POST /api/knowledge/items/{item_id}/enrich`、`GET /api/knowledge/concepts`、`POST /api/knowledge/research-questions`、`POST /api/knowledge/ask`、`osint knowledge search|links|graph|enrich|concepts|gaps|ask`。

### 跨 run 新情报

- 结果列表筛选：**全部 | 本轮新增 | 已见过**（基于画像/KB 已见 URL）
- 搜罗完成 meta 显示「新增 N / 已见过 M」
- Run 对比：`GET /api/runs/{run_id}/diff?since_run=` 返回 URL diff（读磁盘，不重新搜罗）

### 话题监视（Watch）

在 `config.yaml` 配置 `watches` 列表（见 `config/config.example.yaml`）。Web 启动后后台每 30 分钟检查到期任务；工作区「话题监视」面板可 **立即运行**。状态落盘 `~/.osint/watches/{id}/last_run.json`，第二次运行仅摘要相对上次的新增 URL。

### 多任务搜罗与运行参数

- **任务队列**：`search.max_concurrent_searches`（默认 2）控制同时运行数；超出进入 FIFO 队列，`max_queued_searches`（默认 20）为排队上限
- Web：**开始搜罗** 聚焦当前任务；**加入队列** 后台提交且不打断正在观看的 SSE
- **任务列表** API：`GET /api/search/tasks`；取消：`POST /api/search/{run_id}/cancel`
- **运行参数**：设置页可调并发、搜罗加速（关联词/知乎深度/提前结束/AI 摘要条数）、知乎 OpenAPI 限流等；保存后写入 `config.yaml` 并立即生效
- **SSE**：`sse_max_lifetime_sec`（默认 3600s）覆盖 AI 阶段；搜罗页加载时 `GET /api/health` 预热 Web Token Cookie（供 EventSource 鉴权）

### 采集可信度

- **`source_warnings`** 与 **`source_errors`** 分离：超时、早停、Cookie 同步失败等进 warnings；采集失败进 errors
- 某信源零结果时仍保留该信源的 `consume_warnings()` 提示
- GitHub / RSS 等采集器对齐 warnings 模式；RSS 解析使用 `asyncio.to_thread` 避免阻塞事件循环

---

## 5. 研究树

将多轮搜罗组织成 **主题研究**：

- 节点类型：主题、搜罗轮次、笔记、AI 归纳要点、追问、知识条目、概念、实体、问题
- **分叉深挖**：继承上轮报告与有用/噪音反馈，修改关键词再搜  
- **归纳要点 / 建议查询**：需选中研究树中的搜罗节点 + DeepSeek API；建议查询显示在研究树面板下方  
- **从知识继续研究**：`POST /api/research/from-knowledge` / `osint research from-knowledge --item-id ID` 可把知识条目挂入研究树，并生成后续问题。

导图：研究树面板切换「导图」视图（Markmap）。

---

## 6. 浏览器扩展（v0.3.x）

| 能力 | 说明 |
|------|------|
| 被动浏览记录 | 12+ 平台内容页访问与停留 |
| API 拦截 | B站/知乎等 XHR 解析为行为事件 |
| Cookie 同步 | 写入本机 `~/.osint/cookies/` |
| 定时 accounts-sync | 默认每 4 小时 |
| 右键收录 | 进知识库 + 行为事件 |
| 高停留自动收录 | 默认 ≥90s（可配置 `extension.dwell_save_ms`） |

安装：Chrome `chrome://extensions` → 开发者模式 → 加载 `extension/` 目录。  
服务端须先 `osint web`；队列满时分批上传（避免单次过大请求失败）。

---

## 7. AI 能力

| 能力 | 配置/开关 | 说明 |
|------|-----------|------|
| 条目摘要 | 默认开；`--no-ai` 关闭 | DeepSeek V4 Flash；**防幻觉**：prompt 约束仅基于提供内容，不得引入原文未提及信息 |
| 评论归纳 | 需勾选评论挖掘 | 归纳社区评论为观点摘要；**防幻觉**：同样约束不引入评论外信息；AI 返回空时自动回退原始评论列表 |
| 情报报告 | `--digest` / Web 勾选「本轮情报报告」 | 基于去重条目 + 评论挖掘；正文含 `[cN]` 可点击溯源 |
| 画像模拟 | `--no-simulate` 关闭 | 需已有 persona |
| 别名发现 | `search.discover_aliases` | 联网 + AI，可禁 `--no-ai-step alias_discover` |
| 外文拓展 | `search.foreign_expand` | 国际信源英文检索词；`http.proxy` 可扩大探针范围。**设置 → 运行参数 → 外文信源** 可图形化配置；支持「检测国际网络」自检 |
| 本地上下文注入 | 默认开启 | 聚合 persona、混合检索后的知识库命中、概念/项目/知识缺口、近期高价值行为与反馈概况，作为 AI 查询/信源规划参考；每次搜罗落盘 `local_context.json` 供审计，当前不直接改排序 |
| 结构化 Persona | `osint persona build --structured` | 同时生成 brief 与可程序调用的长期兴趣、当前项目、信源偏好、反感模式等字段；AI 失败时规则 fallback |
| 知识增强 | 收录 / 批量收录 / reindex | 规则抽取概念、实体、观点、问题与关系；AI 仅作为候选增强，不直接覆盖用户笔记 |
| 研究树归纳/建议 | 研究树按钮 | 需报告或条目标题作上下文 |
| 追问报告 | 搜罗完成后 | `POST /api/ask` |
| 问知识库 | 知识库页 / CLI | `POST /api/knowledge/ask` / `osint knowledge ask` |
| 每日简报 | 简报页 | 基于近期行为与收录 |

### 反馈闭环

搜罗结果中的「有用 / 噪音」反馈会在后续搜罗中参与轻量相关度融合：同 URL、同信源/站点、标题关键词相似的条目会被小幅加权或降权。系统不会因反馈静默删除结果；所有调整会写入条目的 `personal.local_context_adjustments`，并在 run 目录落盘 `feedback_adjust.json` 供审计。

API Key：`DEEPSEEK_API_KEY` 环境变量或 Web **设置 → API 密钥**（写入 `~/.osint/config.yaml`）。

**AI 导向**：`~/.osint/ai_directives.yaml` 硬/软规则；`~/.osint/prompts/*.md` 覆盖内置 prompt。见 [AI_CONTROL.md](AI_CONTROL.md)。

---

## 8. CLI 常用命令

```bash
osint web                          # 启动 Web
osint auth sync-cookies            # 同步 Cookie
osint auth test --target all       # 诊断 Key + Cookie
osint sync                         # 完整行为同步
osint search "话题" --digest --trace
osint save "https://..." --with-comments
osint recall "关键词"
osint cloud init --provider onedrive_folder --sync
osint cloud status
osint cloud sync
osint cloud reindex
osint persona build --review
osint run list
osint run show <run_id>
osint doctor
```

Windows 可双击 `启动情报台.bat`、`sync-cookies.bat`。

---

## 9. 已知限制（开源使用者须知）

| 限制 | 说明 |
|------|------|
| Pre-Alpha | API 与配置可能随版本变更 |
| 中文站为主 | 采集器针对知乎/B站/国内 Web 优化 |
| Cookie 时效 | B站/知乎接口依赖登录态，需定期重新同步；**B站过期（code=-101 或含"权限"关键词）首次检出后立即设 `_auth_failed` 短路标记，后续所有评论/弹幕请求自动跳过，避免大量无用 API 调用和重复警告日志** |
| 反爬/WAF | 频繁请求可能空结果；系统含 WBI 重试与扩展补洞 |
| Python 3.14 | 暂不支持（`rookiepy`） |
| 微信 | 仅搜狗搜索搜罗；公众号文行为依赖 **Edge 浏览历史**（`ingest browser`）或手动收录，扩展 **不** 被动跟踪 `mp.weixin.qq.com` |
| 字幕 | 仅当视频存在 CC/AI 字幕轨；分 P 视频需正确 URL |
| AICU 发评 | 默认关；服务端直连常被 WAF 拦截 |
| 单用户 | Web 无认证，勿暴露到公网 |
| AI 成本 | DeepSeek 按 token 计费；可用 `--no-ai` 降级 |

### 9.1 稳健性与性能改进

以下问题已修复（2025-06）：

| 维度 | 改进 |
|------|------|
| **搜索取消** | `collect_all` 的 `try/finally` 确保取消时杀掉所有采集子任务，不再泄漏连接 |
| **AI 容错** | `DeepSeekClient()` 构造移入 try 块；API Key 缺失或超时时降级为规则摘要/空结果，不崩溃整条搜索 |
| **AI 防幻觉** | 摘要 prompt 与系统硬约束明确要求 AI 仅基于提供的标题/正文/社区观点生成摘要，**不得引入原文未提及的事件、人物、产品**；评论归纳同样受约束，且 AI 返回空内容时自动回退为原始评论列表 |
| **评论摘要保护** | 存储前检查评论归纳长度 > 10 字符，空白/过短内容不写入，前端不会渲染空的"社区观点归纳"区块 |
| **别名发现超时** | `probe_network` 加 60s 总超时 + 30s 单源超时，单个采集器卡住不阻塞整条搜索 |
| **分页防死循环** | 知乎收藏/关注、B站收藏/关注等所有分页循环加 50-100 页上限 |
| **同步状态锁** | `account_sync_state` 加 `threading.Lock` + `atomic_update_state()`，防止并发同步丢失更新 |
| **事件去重** | `log_events_batch()` 单次连接批量写入，替代循环 N+1；`ingest_history`/`ingest_likes` 改用去重写入 |
| **B站 Cookie 过期检测** | 所有 fetch 函数检测 `code=-101` 或含"权限"关键词的响应，首次命中设 `_auth_failed` 短路标记，后续请求直接跳过（不再发 WBI/legacy API），同时抑制重复警告日志 |
| **部分结果持久化** | 知乎浏览历史翻页失败时保存已获取数据，不丢弃 |
| **数据库索引** | 新增 6 个索引（`events.event_type/created_at`、`intel_items.source/url/created_at`、`endorsements.endorsed_at`），消除全表扫描 |
| **async 端点** | 30+ 个 `async def` 端点用 `asyncio.to_thread()` 包裹同步调用，不再阻塞事件循环 |
| **搜索清理健壮性** | `_execute_search` finally 块每步独立 try/except，磁盘满等异常不跳过后续清理 |
| **进度状态保留** | `finish_progress` 保留 "done" 状态到磁盘，完成后轮询可区分"完成"vs"未找到" |
| **知乎 URL 覆盖** | `_ZHIHU_CONTENT_URL` 正则补全 `zhuanlan./pin//zvideo//people//column/` |
| **相对 URL 处理** | `_parse_read_history_item` 支持 `/question/...` 相对路径，自动补全 |
| **dedup key 区分** | 知乎踩反对/取消赞同的 dedup key 加入 `vote_type` 和 HTTP method，不再碰撞 |
| **SSE 步骤变更追踪** | 按 `filename + mtime_ns` 而非仅文件名去重，running 占位→最终状态可被再次推送 |
| **Pipeline 产物隔离** | `run_step(artifact_name=...)` 步骤元数据与 artifact payload 分路径写入，不再互相覆盖 |
| **画像模拟覆盖持久化** | 覆盖后保留 `overridden` 标记和 `ai_original` 原始快照，支持还原；优先读写 `simulations.json` |
| **知乎评论分页** | 从 `paging.next` 中解析真实 `offset` 参数，而非直接拼接完整 URL；支持 `/answer/{aid}` 独立 URL |
| **B站 SDK 子回复修复** | `fetch_comments_lazy()` 保留 `_raw` 字段以供子回复富化，采集器返回前删除 |
| **B站 auth 短路持久化** | `_auth_failed` 不再在 `__init__` 重置，改由显式 `reset_auth_state()` 控制；子回复端点也检查短路标记 |
| **批量收录保留评论** | `save_run_items()` 优先读取 `items_final.json`，确保评论/评论摘要/字幕等后处理层不被遗漏 |
| **画像模拟 → 相关度融合** | 模拟判为"感兴趣"的条目自动提升 relevance 至 ≥0.6 并清除折叠；"无价值"降为 ≤0.15 并标记折叠 |
| **覆盖即学习** | 用户覆盖模拟判定后，自动写入 `sim_override` 行为事件（高分值），下次构建画像时纳入兴趣 hint，无需等待重新采集行为 |

---

## 10. 与 OpenBiliClaw 等项目的差异（简述）

| 维度 | 个人情报台 | 典型推荐型项目 |
|------|------------|----------------|
| 目标 | 话题驱动 OSINT、报告、研究树 | 个性化推荐、主动推送 |
| 数据 | 用户指定查询 + 本地行为 | 账号全量信号 + 候选池 |
| 产出 | `runs/` 审计、markdown 报告 | 推荐列表、画像 JSON |
| 扩展 | 被动传感器 + 同步 | 常为交互主界面 |

可借鉴：账户同步游标、Cookie 分级重试；本项目的 **点赞列表 API 拉取**、**研究树** 等为独有能力。

---

## 11. 获取帮助

- 诊断：`osint doctor`、Web 设置页环境检查  
- 验收：[MANUAL_TEST.md](MANUAL_TEST.md)  
- 架构：[ARCHITECTURE.md](ARCHITECTURE.md)  
- 贡献：[CONTRIBUTING.md](CONTRIBUTING.md)  
- AI 维护：[AGENTS.md](../AGENTS.md)  

Issue 请附带：`osint doctor` 输出、相关 `run_id`、是否使用扩展、Python 版本（**勿贴 API Key / Cookie**）。
