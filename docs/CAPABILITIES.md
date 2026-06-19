# 功能与能力说明（个人情报台）

本文档面向 **使用者** 与 **维护者**，说明系统能做什么、依赖什么、以及已知限制。开源协作时请与 `AGENTS.md` 对照阅读。

---

## 1. 产品定位

个人情报台帮助你在 **本机** 完成：

1. **搜罗**：按话题从中文互联网多源采集、去重、AI 摘要，可选生成情报报告  
2. **理解**：用浏览/点赞/收藏等行为构建心智画像，模拟「我会不会点这条」  
3. **沉淀**：收录 URL 进知识库、写研究树笔记、分叉深挖、每日简报  
4. **审计**：每次搜罗落盘 `~/.osint/runs/{run_id}/`，可回溯每一步 JSON/报告  

默认绑定 `127.0.0.1:8787`，**单用户本地**使用，无账号体系。

---

## 2. 信源与搜罗能力

| 信源 | 搜罗内容 | 典型依赖 |
|------|----------|----------|
| **知乎** | 问答/文章/视频搜索；可选热榜；深度模式展开高赞回答 | Cookie 和/或 [知乎开放平台](https://developer.zhihu.com/) AccessSecret |
| **B站** | 视频/专栏等搜索；热评/字幕/弹幕挖掘（top N） | Cookie；部分接口需 WBI |
| **微信** | 搜狗微信搜索（公众号文章） | 无登录；受搜狗限流影响 |
| **Web** | Bing / SerpAPI / SearXNG 等 SERP | 对应 API Key 或自建 SearXNG |
| **V2EX** | 节点帖子搜索 | 一般无需登录 |
| **RSS** | `config.yaml` 中 `rss_feeds` |  feed URL |

**查询扩展**：搜罗前可联网发现别名（如角色名、黑称），合并进 `queries_used` 并行采集。预览：`POST /api/search/expand` 或 Web 搜索框下方「关联词」。

**评论/字幕挖掘**（B站视频，默认对 **相关度最高的 top 12** 条）：

- 热评 + AI 归纳
- **CC / AI 字幕**（视频须 UP 开启字幕轨）
- 弹幕 Top 词 + 可选 AI 归纳  

未进入 top N 且简介较长的视频，搜罗列表阶段可能 **不拉字幕**；可对该条点「收录」单独 enrichment。

---

## 3. 行为导入与画像

### 3.1 数据来源

| 来源 | 内容 | 入口 |
|------|------|------|
| Edge 浏览历史 | 多站访问记录 | `osint ingest browser` / 完整同步 |
| B站 Cookie API | 观看历史、收藏、点赞、关注 | accounts-sync |
| 知乎 Cookie API | 收藏、动态、赞同、关注、浏览 | accounts-sync |
| 浏览器扩展 | 页面访问、停留、API 拦截、右键收录、高停留自动入库 | `POST /api/extension/events` |
| Playwright 补洞 | B站空间点赞页、知乎动态/最近浏览等 | browser-sync |
| AICU（可选） | 本账号 B站 **发过** 的评论历史 | 需 probe 通过且显式开启 |

### 3.2 推荐流程

```
启动情报台 → 同步 Cookie → 完整同步 → 构建画像 → 搜罗（可勾选画像模拟）
```

- **Cookie**：`osint auth sync-cookies`（需关闭 Edge 后读磁盘）或扩展弹窗同步  
- **完整同步**：Web「行为同步」页一键 / `osint sync`  
- **画像**：`osint persona build` 或 Web「心智画像」；新行为后可半自动重建（`ai.auto_persona_rebuild`）

### 3.3 心智画像用途

- 搜罗时对条目做 **画像模拟**（是否会点击、简要理由）
- 注入 AI 报告与追问上下文（`persona/context.py`）
- **不**用于对外推荐流；仅供个人情报分析

---

## 4. Web 界面一览

| 页面 | 路径 | 作用 |
|------|------|------|
| 搜罗 | `/` | 多源搜索、情报报告、研究树（分区 Tab / 可选分屏） |
| 知识库 | `/knowledge` | FTS 检索已收录条目 |
| 简报 | `/digest` | 按日 AI 简报 |
| 行为同步 | `/ingest` | 预检、完整同步、扩展状态 |
| 行为时间线 | `/behavior` | 近期 events 浏览 |
| 心智画像 | `/persona` | 查看/构建/回滚画像 |
| 运行记录 | `/runs` | 历次搜罗产物与 trace |
| AI 控制 | `/ai` | `ai_directives`、prompt 覆盖 |
| 设置 | `/settings` | API Key、Cookie 同步、依赖检查 |

---

## 5. 研究树

将多轮搜罗组织成 **主题研究**：

- 节点类型：主题、搜罗轮次、笔记、AI 归纳要点、追问  
- **分叉深挖**：继承上轮报告与有用/噪音反馈，修改关键词再搜  
- **归纳要点 / 建议查询**：需选中研究树中的搜罗节点 + DeepSeek API；建议查询显示在研究树面板下方  

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
| 条目摘要 | 默认开；`--no-ai` 关闭 | DeepSeek V4 Flash |
| 情报报告 | `--digest` / Web 勾选 | 基于去重条目 + 评论挖掘结果 |
| 画像模拟 | `--no-simulate` 关闭 | 需已有 persona |
| 别名发现 | `search.discover_aliases` | 联网 + AI，可禁 `--no-ai-step alias_discover` |
| 研究树归纳/建议 | 研究树按钮 | 需报告或条目标题作上下文 |
| 追问报告 | 搜罗完成后 | `POST /api/ask` |
| 每日简报 | 简报页 | 基于近期行为与收录 |

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
| Cookie 时效 | B站/知乎接口依赖登录态，需定期重新同步 |
| 反爬/WAF | 频繁请求可能空结果；系统含 WBI 重试与扩展补洞 |
| Python 3.14 | 暂不支持（`rookiepy`） |
| 微信 | 仅搜狗搜索 + 扩展记录已打开公众号文；无行为全量导入 |
| 字幕 | 仅当视频存在 CC/AI 字幕轨；分 P 视频需正确 URL |
| AICU 发评 | 默认关；服务端直连常被 WAF 拦截 |
| 单用户 | Web 无认证，勿暴露到公网 |
| AI 成本 | DeepSeek 按 token 计费；可用 `--no-ai` 降级 |

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
