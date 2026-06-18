# OSINT Toolkit / 个人情报工具

中文互联网的个人情报操作系统：多源搜罗、分层理解、AI 归纳、流程透明、反馈可纠正。

## 功能

- **多源搜索**: 知乎、B站、微信（搜狗）、Web、V2EX、RSS
- **AI 情报报告**: DeepSeek V4 Flash，`--digest`
- **流程透明**: `--trace`，`osint run show <run_id>`
- **AI 可控**: `ai_directives`、用户 prompt 覆盖、`--ai-instruct`
- **收录与知识库**: `save` / `recall`
- **行为导入**: 浏览器历史、B站观看、知乎赞同
- **Persona**: 心智画像构建与回滚
- **Web 控制台**: `osint web` 本机网页，与 CLI 功能对等

## 安装

推荐 **Python 3.12**（3.10–3.13 均可；3.14 暂不支持 `rookiepy` 浏览器历史导入）。

```bash
git clone https://github.com/GuoEdge/gochj.git
cd gochj
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -e ".[dev]"
# Web 控制台（可选）
pip install -e ".[dev,web]"
```

## Web 控制台

**Windows 一键启动**：双击 [`启动情报台.bat`](启动情报台.bat)（详见 [docs/WEB_UI.md](docs/WEB_UI.md)）。

```bash
osint web
# 浏览器打开 http://127.0.0.1:8787
```

详见 [docs/WEB_UI.md](docs/WEB_UI.md)。

## 配置 API Key

PowerShell:

```powershell
[System.Environment]::SetEnvironmentVariable("DEEPSEEK_API_KEY", "你的Key", "User")
```

或在 Web 控制台 **设置 → API 密钥** 填写（推荐，写入本机配置）。

知乎开放平台（可选，免 Cookie 站内搜索）：

```powershell
[System.Environment]::SetEnvironmentVariable("ZHIHU_ACCESS_SECRET", "你的AccessSecret", "User")
```

或在 `%USERPROFILE%\.osint\config.yaml` 中设置 `zhihu.openapi.access_secret: ${ZHIHU_ACCESS_SECRET}`。Key **不要**提交到 Git。

也可以在 Web 控制台 **设置 → API 密钥** 中直接粘贴保存（写入本机 `~/.osint/config.yaml`）。

## 快速开始

**推荐流程**（与 Web 入门向导一致）：

```bash
osint web                      # 1. 启动情报台
osint auth sync-cookies        # 2. 同步 Cookie（或扩展弹窗）
osint sync                     # 3. 完整同步行为数据
osint search "MCP协议" --digest # 4. 搜罗
osint persona build --review   # 5. 构建画像
osint doctor                   # 诊断 Cookie / Playwright / 数据
```

常用命令：

```bash
osint auth test --target all
osint search "MCP协议" --sources zhihu,bilibili,web,weixin
osint save "https://www.zhihu.com/question/..." --with-comments
osint recall "MCP"
osint run list
```

## 文档

- [docs/MANUAL_TEST.md](docs/MANUAL_TEST.md) — Windows 验收
- [docs/AI_CONTROL.md](docs/AI_CONTROL.md) — AI 导向控制
- [docs/PRIVACY.md](docs/PRIVACY.md) — 隐私说明

## 本地数据

`%USERPROFILE%\.osint\` — Cookie、知识库、runs、persona（不进 Git）
