# OSINT Toolkit / 个人情报工具

中文互联网的个人情报操作系统：多源搜罗、分层理解、AI 归纳、流程透明、反馈可纠正。

## 功能

- **多源搜索**: 知乎、B站、Web、V2EX、RSS
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

## 快速开始

```bash
osint auth sync-cookies --browser edge
osint auth test --target all
osint search "MCP协议" --sources zhihu,bilibili,web --trace
osint search "MCP协议" --digest --profile research
osint save "https://www.zhihu.com/question/..." --with-comments
osint recall "MCP"
osint persona build --review
osint run list
```

## 文档

- [docs/MANUAL_TEST.md](docs/MANUAL_TEST.md) — Windows 验收
- [docs/AI_CONTROL.md](docs/AI_CONTROL.md) — AI 导向控制
- [docs/PRIVACY.md](docs/PRIVACY.md) — 隐私说明

## 本地数据

`%USERPROFILE%\.osint\` — Cookie、知识库、runs、persona（不进 Git）
