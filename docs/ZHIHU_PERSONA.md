# 知乎与个人画像 — 能力说明与限制

本文档说明 **知乎行为导入** 在画像中的真实能力，避免与 B 站同级能力混淆。

## 账号同步（Cookie API）稳定支持

| 数据 | 接口/来源 | 画像事件 |
|------|-----------|----------|
| 收藏夹 | `favlists` + `collections/.../items` | `zhihu_fav` |
| 关注的人 | `members/{token}/followees` | `zhihu_follow` |
| 我发布的回答 | `members/{token}/answers` | `zhihu_answer` |
| 我发布的文章 | `members/{token}/articles` | `zhihu_article` |
| 我的想法 | `members/{token}/pins` | `zhihu_pin` |
| Edge 浏览过的知乎问答/专栏 | 本机 Edge `History` SQLite | `zhihu_browse`（`via: edge_history`） |
| 行为摘要时间线 | 由收藏/关注/发布等 **合成**（非官方动态流） | 各对应 `event_type` |

## 已停用（不再自动调用）

以下路径经实测对当前知乎账号 **404 或长期空数据**：

| 原能力 | 原因 |
|--------|------|
| `voteanswers` / `vote_answers` / `answers/voted` | HTTP **404**，接口已废弃（2024-11 对 sankichu 重新实测确认仍 404）|
| `browsing_histories` / `footprints` 等浏览 API | HTTP **404**（重新实测确认）|
| `members/{token}/activities` 动态流（v4 端点）| 200 但 **返回空列表**（v4 端点已失效）|

## 动态流与点赞历史 — moments API（v3）

**2024-11 重大发现**：知乎真正的动态流端点是 `/api/v3/moments/{token}/activities`（v3 moments），
而非已废弃的 v4 `/api/v4/members/{token}/activities`（返回空）。

moments API 返回近期动态，每页 7 条，用 `offset`（毫秒时间戳）翻页，verb 包含：
- `MEMBER_VOTEUP_ANSWER`：点赞回答 → `zhihu_vote`
- `MEMBER_VOTE_PIN`：点赞想法 → `zhihu_vote`
- 其它：收藏/关注/发布等

**HttpClient 可直接调用**（无需 Playwright 签名），翻页可获取数周内的点赞/收藏/关注历史。
实现：`ingest/zhihu_account.py` `ingest_activities()` → 写入 events 表 + 增量游标去重。

## 点赞/收藏/关注 — 扩展 POST 拦截（实时记录）

知乎已关闭赞同历史端点，**完整点赞历史无法恢复**。但从现在起每次点赞/收藏/关注动作可被
扩展实时拦截并记录到 events 表：

| 动作 | 拦截端点 | event_type |
|------|----------|------------|
| 点赞回答/文章/想法 | `POST /api/v4/{type}/{id}/voters` | `zhihu_vote` |
| 取消点赞 | `DELETE /api/v4/{type}/{id}/voters` | `zhihu_unvote` |
| 收藏内容 | `POST /api/v4/favlists/items` | `zhihu_fav` |
| 取消收藏 | `DELETE /api/v4/favlists/items` | `zhihu_unfav` |
| 关注人/问题 | `POST /api/v4/{type}/{token}/followers` | `zhihu_follow` |
| 取消关注 | `DELETE /api/v4/{type}/{token}/followers` | `zhihu_unfollow` |

实现：`extension/content/inject.js` 拦截 POST → `ingest/extension_events.py` `_parse_zhihu_post` 解析。

## Playwright 补洞页（动态/收藏/回答）

`ZHIHU_PROBE_PAGES` 已填充知乎个人主页各 Tab 模板。`osint sync --mode browser` 或
`osint ingest browser-sync` 会打开这些页面，由浏览器自然签名后发出 XHR，
`capture_patterns` 拦截入库。推荐 Persistent 模式（需关闭 Edge）。

| 页面 | URL | 预期拦截 |
|------|-----|----------|
| 知乎动态 | `/people/{token}/activities` | activities XHR（含点赞/收藏/关注动态）|
| 知乎收藏 | `/people/{token}/collections` | favlists + collections/items XHR |
| 知乎回答 | `/people/{token}/answers` | members/{token}/answers XHR |
| 知乎文章 | `/people/{token}/posts` | members/{token}/articles XHR |

扩展定时同步（`probePageTemplates`）也包含知乎动态/收藏页，每 4h 自动打开拦截。

## 维护者

- 实现：`ingest/zhihu_account.py`、`services/ingest.py`
- 扩展拦截：`ingest/capture_patterns.py`、`extension/content/inject.js`（保留，供用户主动浏览时采集）
- 勿恢复已停用 API 循环，除非重新实测端点可用并在 `tests/` 中验证
