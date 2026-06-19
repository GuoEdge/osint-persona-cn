# Windows 本机验收清单

## CLI 冒烟

1. 设置 `DEEPSEEK_API_KEY` 用户环境变量
2. `pip install -e ".[dev,web]"`
3. `osint doctor` — 知乎/B站/DeepSeek 等关键项
4. `pytest -q` — 全绿（当前 **454+** 项，含 `test_search_task_queue`、`test_tunable_config`）
5. `osint auth sync-cookies --browser edge`
6. `osint auth test --target all`
7. `osint search "测试话题" --trace`
8. `osint search "测试话题" --digest --no-ai`（无 API 时）
9. `osint save <知乎或B站URL> --with-comments`
10. `osint recall "测试"`
11. `osint ingest browser --since 30`
12. `osint persona build --review`
13. `osint run list` / `osint run show <run_id>`

## Web 控制台验收

1. `osint web` → 打开 http://127.0.0.1:8787
2. **设置**：API + Cookie 状态正常，`同步 Cookie` 成功
3. **搜罗**：多源搜索 → 步骤条 → 结果卡片 → 勾选「本轮情报报告」→ 报告与追问
4. **搜罗**：对结果提交 feedback（有用/噪音等）
5. **证据链**：报告正文含 `[cN]`，点击可滚动到对应结果卡片
6. **评论与社区层挖掘**：勾选后 B 站弱简介视频见字幕/热评/弹幕区块；知乎问答见「社区观点归纳」
7. **批量收录**：搜罗完成后点「收录本轮精选」→ **知识库** recall 可找到
8. **跨 run 新情报**：同一话题二次搜罗 → 筛选「本轮新增」
9. **收录**：粘贴 URL 收录（含评论选项）
10. **知识库**：recall 到刚收录内容
11. **简报**：今日简报 + 历史报告列表（与搜罗「本轮情报报告」不同）
12. **行为同步**：browser / bilibili / zhihu（原「导入」页）。知乎 Cookie 同步抓取：**赞同回答**（voteanswers）、**收藏**、**关注**、**浏览记录**、**主页动态流**（赞/藏/关注/发布等，非独立「发动态」时间线）；扩展被动采集可补洞。
13. **画像**：build → show → rollback
14. **研究树**：创建主题 → 挂载搜罗轮次 → 刷新页面 parent 挂载点不丢
15. **运行记录**：list → 详情（含采集 warnings/errors）→ artifact 链接；**批量清理**需确认对话框
16. **话题监视**：`~/.osint/config.yaml` 配置 `watches` → 工作区面板「立即运行」两次，第二次 `new_count` 应较小；点「刷新列表」可重载配置
17. **推荐搜罗**：完成画像后工作区顶部出现推荐话题芯片，点击可发起搜罗
18. **长跑搜罗 SSE**：默认 `collect_timeout_sec` 900s 时，事件流应能等到完成（`done` 后客户端拉取完整结果）
19. **AI 控制**：directives / prompts 编辑保存；Tab 键可切换分区
20. **大结果分批**：搜罗结果超过 30 条时出现「加载更多」
21. **简报存档**：点击历史日期在页内展开全文
22. **扩展**：manifest 更新后在浏览器扩展页 **重新加载**；微信公众号文章访问应出现在行为事件
23. **B 站字幕**：`config.yaml` 设 `bilibili.subtitle_prefer: cc_first` 后重试弱简介视频

### 二期稳定性验收（多任务 / 可调参数）

24. **多任务队列**：同时发起 2 个搜罗 → 第 3 个进入排队；任务列表可见位置
25. **加入队列不打断 SSE**：聚焦任务 A 时「加入队列」B → A 的进度/SSE 应持续
26. **任务切换**：从任务列表切换 run → 结果、报告、追问应与该 run 一致（无旧报告残留）
27. **排队取消**：排队中任务可取消；取消后不再启动
28. **运行参数**：设置页修改「同时运行搜罗数」→ 排队任务开始消化
29. **搜罗加速**：设置页关闭「联网发现关联词」后，下一轮搜罗应跳过 alias 阶段（耗时缩短）
30. **队列满**：排队已达上限时提交新任务 → HTTP 429 或前端 toast 提示
31. **报告分屏阅读**：宽屏分屏时报告正文不应出现单字竖排；Focus 模式可全宽阅读

## 可选自动化验收

服务已启动时：

```bash
osint doctor
python scripts/web_acceptance.py
```

报告写入 `~/.osint/acceptance/latest.json`。
