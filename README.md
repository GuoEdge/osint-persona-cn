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

## 安装

```bash
git clone https://github.com/GuoEdge/gochj.git
cd gochj
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -e ".[dev]"
```

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
