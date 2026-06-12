# Web 控制台

本机网页界面，与 CLI 功能 1:1 对等。

## 安装与启动

### 一键启动（推荐，Windows）

双击项目根目录：

- **`start-osint-web.bat`**（或中文名 `启动情报台.bat`）— 启动服务并自动打开浏览器
- **`stop-osint-web.bat`**（或 `停止情报台.bat`）— 释放 8787 端口

固定到桌面（运行一次即可）：

```powershell
cd D:\gochj\gochj-web
powershell -ExecutionPolicy Bypass -File .\scripts\create-desktop-shortcut.ps1
```

会在桌面生成 **OSINT Web.lnk** 和 **Stop OSINT Web.lnk**。

脚本会自动使用 `.venv\Scripts\python.exe`（若存在），否则用系统 `python`，并设置 `PYTHONPATH=src`（无需每次手敲）。

### 命令行启动

```powershell
pip install -e ".[dev,web]"
osint web
```

浏览器打开：http://127.0.0.1:8787

可选参数：

```bash
osint web --port 8787 --host 127.0.0.1
```

## 导航说明

| 页面 | 用途 |
|------|------|
| 搜罗 | 多源搜索、AI 报告、追问、反馈 |
| 收录 | 粘贴 URL 收录到知识库 |
| 知识库 | 检索已收录内容 |
| 简报 | 今日简报与历史报告 |
| 画像 | 构建/查看/回滚心智画像 |
| 导入 | 浏览器/B站/知乎行为数据 |
| 运行记录 | Pipeline 步骤与 artifact |
| AI 控制 | directives 与 prompt 编辑 |
| 设置 | API/Cookie 状态与同步 |

## 验收清单

参见 [MANUAL_TEST.md](MANUAL_TEST.md) 中的 Web 验收部分。

## 安全说明

- 默认仅绑定 `127.0.0.1`
- API Key 不会通过 Web 返回
- 个人数据仍在 `%USERPROFILE%\.osint\`
