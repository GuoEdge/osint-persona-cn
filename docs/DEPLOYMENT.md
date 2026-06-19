# 部署指南

面向在 **本机** 或 **容器** 中运行 OSINT 个人情报台 Web 控制台（默认 `http://127.0.0.1:8787`）。

---

## 1. 本机部署（推荐）

### 安装

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

**Linux / macOS：**

```bash
source .venv/bin/activate
pip install -e ".[dev,web,bilibili]"
```

可选 Playwright 补洞同步：`pip install -e ".[browser]"` 后运行 `scripts/install-browser-sync.ps1`（Windows）或 `playwright install chromium`。

### 配置

```bash
# 复制示例配置到用户数据目录（Windows 为 %USERPROFILE%\.osint\）
mkdir -p ~/.osint
cp config/config.example.yaml ~/.osint/config.yaml
```

按需编辑 `~/.osint/config.yaml` 或设置环境变量：

| 变量 | 用途 |
|------|------|
| `DEEPSEEK_API_KEY` | AI 摘要与报告 |
| `ZHIHU_ACCESS_SECRET` | 知乎开放平台（可选） |
| `BING_SEARCH_API_KEY` / `SERPAPI_KEY` / `SEARXNG_BASE_URL` | Web/SERP 搜索 |
| `OSINT_DATA_DIR` | 数据目录（默认 `~/.osint`） |

### 启动

```bash
osint web
# 或指定端口
osint web --host 127.0.0.1 --port 8787
```

**快捷脚本：**

| 平台 | 命令 |
|------|------|
| Windows | 双击 `启动情报台.bat` 或 `powershell -File scripts/start.ps1` |
| Linux / macOS | `chmod +x scripts/start.sh && ./scripts/start.sh` |

停止 Windows 后台服务：运行项目中的 `停止情报台.bat` 或 `scripts/stop-web.ps1`。

### 浏览器扩展

1. Chrome / Edge → `chrome://extensions` → 开发者模式
2. 加载本仓库 [`extension/`](../extension/) 目录
3. 扩展选项中将 API 地址设为 `http://127.0.0.1:8787`

详见 [extension/README.md](../extension/README.md)。

---

## 2. Docker 部署（Web 仅）

适合无 Edge Cookie 同步、仅用 SERP + 扩展上报的场景。

```bash
# 构建并启动
docker compose up -d --build

# 首次：将示例配置写入卷（可选）
docker compose exec osint-web sh -c 'test -f /data/config.yaml || cp /app/config/config.example.yaml /data/config.yaml'
```

访问：**http://127.0.0.1:8787**

环境变量可通过项目根目录 `.env` 文件传入（勿提交密钥）。

**限制：**

- 容器内无法使用 `rookiepy` 读取宿主机 Edge Cookie
- Playwright 补洞同步需额外配置，一般在本机运行更合适
- 扩展仍指向宿主机 `127.0.0.1:8787`（端口已映射即可）

---

## 3. 验证

```bash
osint doctor
curl -s http://127.0.0.1:8787/api/extension/status
```

Web 工作台 **搜罗** 页应显示完整信源目录（核心 + 社区/社交/游戏/科技/商业/音乐/文化扩展源）。

---

## 4. 扩展信源说明

除知乎、B站、微信、V2EX、RSS 等原生采集器外，以下站点通过 **SERP `site:domain`** 模式接入（在 UI 勾选对应来源即可）：

即刻、贴吧、简书、微博、小红书、脉脉、Reddit、IT之家、少数派、掘金、Solidot、GitHub、Hacker News、Chiphell、什么值得买、机核、NGA、36氪、虎嗅、财新、澎湃、凤凰网、网易云/QQ/酷狗/咪咕音乐、豆瓣、小宇宙、喜马拉雅等。

完整列表见工作台信源面板或 `GET /api/search/source-catalog`。
