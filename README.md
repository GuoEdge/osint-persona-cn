# OSINT Toolkit / 个人情报台

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

**中文互联网的个人情报操作系统**：多源搜罗、行为理解、AI 归纳、流程可审计、研究树深挖。

> 仓库名：`osint-persona-cn` · 包名：`osint-toolkit` · 本地 Web：`http://127.0.0.1:8787`

适合 **个人情报分析**、话题调研、将浏览行为沉淀为可检索知识库，并用 AI 生成结构化报告——数据默认 **仅存本机**，不上传浏览记录。

---

## 你能用它做什么

| 能力 | 说明 |
|------|------|
| **多源搜罗** | 知乎、B站、微信、Web、V2EX、RSS；扩展信源含微博、即刻、贴吧、小红书、机核、Chiphell、财新、澎湃、Reddit 等（SERP）；可选别名发现与评论/字幕挖掘；**支持多任务排队** |
| **情报报告** | DeepSeek 生成 markdown 报告，支持追问与每日简报 |
| **行为导入** | Edge 历史、B站/知乎账号 API、Chrome 扩展被动采集 |
| **心智画像** | 从行为构建 persona，搜罗时模拟「我会不会点」 |
| **研究树** | 多轮搜罗、笔记、AI 归纳要点、分叉深挖、导图 |
| **知识库** | 收录 URL、FTS 检索、高停留自动入库（扩展） |
| **流程透明** | 每轮搜罗落盘 `~/.osint/runs/{run_id}/`，可 `osint run show` |
| **AI 可控** | `ai_directives`、自定义 prompt、`--ai-instruct` |

完整能力矩阵与限制见 **[docs/CAPABILITIES.md](docs/CAPABILITIES.md)**。

---

## 截图与界面

启动后访问 **搜罗**、**行为同步**、**心智画像**、**研究树** 等页面。Windows 可双击 [`启动情报台.bat`](启动情报台.bat)。

---

## 安装

**Python 3.10–3.13**（推荐 **3.12**；3.14 暂不支持 `rookiepy` 浏览器历史）。

```bash
git clone https://github.com/GuoEdge/osint-persona-cn.git
cd osint-persona-cn
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
pip install -e ".[dev,web,bilibili]"
```

可选扩展能力：

```bash
pip install -e ".[browser]"   # Playwright 补洞同步
```

浏览器扩展：Chrome `chrome://extensions` → 开发者模式 → 加载本仓库 [`extension/`](extension/) 目录。详见 [extension/README.md](extension/README.md)。

---

## 快速开始

```bash
osint web                      # 1. 启动情报台 → http://127.0.0.1:8787
osint auth sync-cookies        # 2. 同步 Cookie（关 Edge 后或扩展同步）
osint sync                     # 3. 完整行为同步
osint search "话题" --digest   # 4. 搜罗并生成报告
osint persona build --review   # 5. 构建心智画像
osint doctor                   # 环境诊断
```

常用命令：

```bash
osint auth test --target all
osint search "MCP协议" --sources zhihu,bilibili,web,weixin --trace
osint save "https://www.zhihu.com/question/..." --with-comments
osint recall "关键词"
osint run list
```

---

## 配置 API Key

**DeepSeek**（AI 摘要/报告/研究树）：

```powershell
[System.Environment]::SetEnvironmentVariable("DEEPSEEK_API_KEY", "你的Key", "User")
```

或在 Web **设置 → API 密钥** 填写（写入 `~/.osint/config.yaml`，推荐）。**运行参数**（搜罗并发、加速、知乎限流等）亦在设置页在线调整。

**知乎开放平台**（可选，免 Cookie 站内搜索）：

```powershell
[System.Environment]::SetEnvironmentVariable("ZHIHU_ACCESS_SECRET", "你的AccessSecret", "User")
```

复制 [`config/config.example.yaml`](config/config.example.yaml) 到 `~/.osint/config.yaml` 并按需修改。**切勿将 Key 提交到 Git。**

---

## 本地数据

所有个人数据在 **`%USERPROFILE%\.osint\`**（或 `OSINT_DATA_DIR`）：

| 目录/文件 | 内容 |
|-----------|------|
| `config.yaml` | 用户配置与 API Key |
| `cookies/` | 各站 Cookie |
| `knowledge.db` | 行为事件与知识库 |
| `runs/` | 搜罗产物与 trace |
| `persona/` | 心智画像 |
| `research/trees/` | 研究树 |

见 [docs/PRIVACY.md](docs/PRIVACY.md)。

---

## 文档索引

### 使用者

| 文档 | 内容 |
|------|------|
| [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md) | **入门指南**（安装、同步、第一次搜罗） |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | **部署指南**（本机/Docker、启动脚本、扩展） |
| [docs/CAPABILITIES.md](docs/CAPABILITIES.md) | **功能与能力说明**（信源、扩展、AI、限制） |
| [docs/WEB_UI.md](docs/WEB_UI.md) | Web 控制台与页面说明 |
| [docs/AI_CONTROL.md](docs/AI_CONTROL.md) | AI 导向与 prompt 覆盖 |
| [docs/MANUAL_TEST.md](docs/MANUAL_TEST.md) | Windows 验收清单 |
| [extension/README.md](extension/README.md) | 浏览器扩展安装与同步 |
| [docs/PRIVACY.md](docs/PRIVACY.md) | 隐私与本地存储 |

### 开发者与 AI 维护者

| 文档 | 内容 |
|------|------|
| [AGENTS.md](AGENTS.md) | **AI / 维护者入口**（仓库结构、pipeline、修改指南） |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 架构与数据流 |
| [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) | 贡献流程与 PR 规范 |

在 Cursor、Copilot 等工具中打开本仓库时，请优先加载 **AGENTS.md** 与 **CAPABILITIES.md**。

---

## 开源与许可

- **许可证**：[MIT](LICENSE)
- **贡献**：[docs/CONTRIBUTING.md](docs/CONTRIBUTING.md)
- **Issue**：请附 `osint doctor` 输出与复现步骤（勿贴 Key/Cookie）
- **状态**：Pre-Alpha，API 与配置可能随版本演进

---

## 致谢

Built for personal OSINT on the Chinese web. 各平台接口与反爬策略可能变化，欢迎通过 Issue/PR 共同维护采集器与文档。
