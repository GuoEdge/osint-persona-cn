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

以下路径经实测对当前知乎账号 **404 或长期空数据**，同步流程 **不再请求**，以免浪费时间与 Playwright 资源：

| 原能力 | 原因 |
|--------|------|
| `voteanswers` / `vote_answers` / `answers/voted` | HTTP **404**，接口已废弃 |
| `browsing_histories` / `footprints` 等浏览 API | HTTP **404** |
| `members/{token}/activities` 动态流 | 常返回 **空列表**，不作为主数据源 |
| 自动 Playwright 打开知乎主页/赞同 Tab 补洞 | Cookie 无头模式下 **实测 0 条**捕获，已关闭 |
| `recent-viewed` HTML 引导解析 | 实测无稳定数据，已关闭 |

## 赞同 / 日常浏览 — 请用扩展

| 数据 | 推荐来源 |
|------|----------|
| **赞同**（点赞回答） | Chrome 扩展拦截 XHR / 用户点赞时的 API；**非**账号同步 |
| **日常浏览**（未进 Edge 历史的页面） | 扩展 `ext_page_visit` / `ext_page_dwell` |

安装扩展后日常上网即可增量写入 `events` 表，参与画像与「行为认可」。

## 用户可见提示

- 行为同步结果中的 **「画像三要素」**：赞同/浏览/动态若显示 `skip` 或 `extension`，表示该项 **不承诺** 由 Cookie 同步拉全。
- 收藏、关注在「行为认可」中为 **库存快照**；近期赞同依赖扩展。

## 维护者

- 实现：`ingest/zhihu_account.py`、`services/ingest.py`
- 扩展拦截：`ingest/capture_patterns.py`、`extension/content/inject.js`（保留，供用户主动浏览时采集）
- 勿恢复已停用 API 循环，除非重新实测端点可用并在 `tests/` 中验证
