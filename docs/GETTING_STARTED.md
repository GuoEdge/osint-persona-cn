# 入门指南（个人情报台）

面向 **第一次使用** 的开源用户。5–15 分钟可完成基础环境。

---

## 1. 前置条件

- Windows 10/11 或 macOS / Linux
- Python **3.10–3.13**（推荐 3.12）
- 可选：Microsoft Edge（Cookie 磁盘同步）、Chrome（加载扩展）
- 可选：DeepSeek API Key（AI 功能）

---

## 2. 安装

```bash
git clone https://github.com/GuoEdge/osint-persona-cn.git
cd osint-persona-cn
python -m venv .venv
```

**Windows PowerShell：**

```powershell
.venv\Scripts\Activate.ps1
pip install -e ".[dev,web,bilibili]"
```

验证：

```bash
osint --help
osint doctor
```

---

## 3. 启动 Web 控制台

```bash
osint web
```

浏览器打开：**http://127.0.0.1:8787**

Windows 也可双击项目根目录 `启动情报台.bat`。

**部署详情**（配置、环境变量、Docker、扩展）：见 **[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)**。

---

## 4. 配置密钥（可选但推荐）

### DeepSeek（AI 摘要、报告、研究树）

Web：**设置 → API 密钥 → DeepSeek**

或环境变量 `DEEPSEEK_API_KEY`。

### 知乎 OpenAPI（可选）

在 [知乎开放平台](https://developer.zhihu.com/) 申请后，设置 `ZHIHU_ACCESS_SECRET` 或 Web 设置页。

---

## 5. 同步行为数据

情报质量依赖 **本机行为** 与 **登录态**。

### 方式 A：CLI

```bash
# 关闭 Edge 后从磁盘读 Cookie
osint auth sync-cookies
osint auth test --target bilibili,zhihu

# 拉取历史/收藏/点赞等
osint sync
```

### 方式 B：浏览器扩展（推荐日常使用）

1. Chrome 打开 `chrome://extensions`，开启开发者模式  
2. 「加载已解压的扩展程序」→ 选择仓库内 `extension/`  
3. 确保 `osint web` 已运行  
4. 扩展弹窗：**同步 Cookie**、查看队列状态  

详见 [extension/README.md](../extension/README.md)。

### 方式 C：Web「行为同步」页

一键 **完整同步**，含预检与进度展示。

---

## 6. 第一次搜罗

### Web

1. 打开 **搜罗** 页  
2. 输入话题，选择信源（或默认）  
3. 勾选 **生成情报报告**（需 DeepSeek）  
4. 开始搜罗 → 查看 **搜索结果 / 情报报告 / 研究树**  

### CLI

```bash
osint search "你想调研的话题" --digest --trace
osint run list
osint run show <run_id>
```

产物在 `~/.osint/runs/<run_id>/`。

---

## 7. 心智画像（可选）

```bash
osint persona build --review
```

或在 Web **心智画像** 页构建。构建后搜罗可勾选 **画像模拟**。

---

## 8. 研究树（可选）

1. 搜罗时勾选 **创建研究树** 或选择已有树  
2. 多轮搜索后，在研究树面板选中节点  
3. 使用 **归纳要点**、**建议查询**（需 API Key）  
4. **分叉深挖** 继承上下文继续搜  

---

## 9. 收录与检索

- 搜罗结果中 **收录** 单条  
- 扩展：右键「收录到情报台」、高停留自动入库  
- CLI：`osint save "URL" --with-comments`  
- 检索：`osint recall "关键词"` 或 Web **知识库**

---

## 10. 故障排查

| 现象 | 建议 |
|------|------|
| Cookie 无效 | 重新 `sync-cookies` 或扩展同步；`osint auth test` |
| 搜罗无结果 | 检查网络、Cookie、是否被限流；换信源组合 |
| AI 报错 | 检查 DeepSeek Key 与余额 |
| 扩展上传失败 | 确认 `osint web` 运行；查看扩展队列；勿一次积压过多 |
| 字幕拉取失败 | 视频须 UP 开启字幕；见 CAPABILITIES 限制说明 |

```bash
osint doctor
```

完整验收：[MANUAL_TEST.md](MANUAL_TEST.md)

---

## 11. 下一步

- [CAPABILITIES.md](CAPABILITIES.md) — 能做什么、不能做什么  
- [WEB_UI.md](WEB_UI.md) — 各页面说明  
- [AI_CONTROL.md](AI_CONTROL.md) — 定制 AI 行为  
- 参与开发：[CONTRIBUTING.md](CONTRIBUTING.md)、[AGENTS.md](../AGENTS.md)
