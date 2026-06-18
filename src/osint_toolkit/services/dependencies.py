"""新设备环境依赖检查与安装 / Environment dependencies for fresh installs."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any, Callable

from osint_toolkit.services import auth

_PROJECT_ROOT = Path(__file__).resolve().parents[3]


def project_root() -> Path:
    return _PROJECT_ROOT


def playwright_available() -> bool:
    try:
        import playwright  # noqa: F401

        return True
    except ImportError:
        return False


def rookiepy_available() -> bool:
    try:
        import rookiepy  # noqa: F401

        return True
    except ImportError:
        return False


def _venv_ok() -> tuple[bool, str]:
    in_venv = getattr(sys, "prefix", "") != getattr(sys, "base_prefix", sys.prefix)
    if in_venv:
        return True, f"venv: {sys.prefix}"
    return False, "未检测到虚拟环境，建议用项目 .venv 启动 Web"


def _auth_map() -> dict[str, dict[str, Any]]:
    return {x["key"]: x for x in auth.get_auth_status("all")}


def get_dependencies_status() -> dict[str, Any]:
    auth_map = _auth_map()
    deepseek = auth_map.get("deepseek", {})
    bilibili = auth_map.get("bilibili", {})
    zhihu = auth_map.get("zhihu", {})
    zhihu_openapi = auth_map.get("zhihu_openapi", {})
    venv_ok, venv_detail = _venv_ok()
    pw_ok = playwright_available()
    rookie_ok = rookiepy_available()

    items: list[dict[str, Any]] = [
        {
            "id": "venv",
            "label": "Python 虚拟环境",
            "ok": venv_ok and rookie_ok,
            "required": True,
            "detail": venv_detail if venv_ok else venv_detail,
            "hint": "在项目目录运行: py -3.12 -m venv .venv && pip install -e \".[dev,web]\"",
            "action": None,
        },
        {
            "id": "deepseek",
            "label": "DeepSeek API Key",
            "ok": bool(deepseek.get("ok")),
            "required": False,
            "detail": str(deepseek.get("detail") or ""),
            "hint": "在设置页「API 密钥」填写，或设置 DEEPSEEK_API_KEY 环境变量",
            "action": None,
        },
        {
            "id": "playwright",
            "label": "Playwright（知乎/微信搜罗回退 + 浏览器补洞）",
            "ok": pw_ok,
            "required": False,
            "required_for": ["zhihu 搜罗回退", "搜狗微信搜罗", "浏览器会话补洞"],
            "detail": "已安装" if pw_ok else "未安装 pip 包 playwright",
            "hint": "点击下方「一键安装 Playwright」；约 1–3 分钟，需联网",
            "action": "install_playwright",
        },
        {
            "id": "bilibili_cookie",
            "label": "B站 Cookie",
            "ok": bool(bilibili.get("ok")),
            "required": False,
            "required_for": ["B站搜罗", "B站导入"],
            "detail": str(bilibili.get("detail") or ""),
            "hint": "完全关闭 Edge 后点「同步 Cookie」，或扩展弹窗一键同步（推荐）",
            "action": "sync_cookies",
        },
        {
            "id": "zhihu_cookie",
            "label": "知乎 Cookie",
            "ok": bool(zhihu.get("ok")),
            "required": False,
            "required_for": ["知乎导入", "知乎评论深采"],
            "detail": str(zhihu.get("detail") or ""),
            "hint": "Cookie 失效时搜罗会尝试 Playwright；配置开放平台 Key 可免 Cookie 搜索",
            "action": "sync_cookies",
        },
        {
            "id": "zhihu_openapi",
            "label": "知乎开放平台 Access Secret",
            "ok": bool(zhihu_openapi.get("ok")),
            "required": False,
            "required_for": ["知乎官方站内搜索", "热榜"],
            "detail": str(zhihu_openapi.get("detail") or ""),
            "hint": "在设置页「API 密钥」填写 ZHIHU_ACCESS_SECRET，或设环境变量",
            "action": None,
        },
    ]

    blockers: list[str] = []
    if not rookie_ok:
        blockers.append("当前 Python 未安装 rookiepy，Cookie 磁盘同步不可用")
    if not deepseek.get("ok"):
        blockers.append("DeepSeek API 未配置：AI 摘要 / digest / 追问不可用")
    if not pw_ok:
        blockers.append("Playwright 未安装：知乎 API 被风控时无法回退，微信搜罗可能失败")
    if not bilibili.get("ok") and not zhihu.get("ok") and not zhihu_openapi.get("ok"):
        blockers.append("B站 Cookie、知乎 Cookie 与开放平台 Key 均未就绪")

    search_ready = rookie_ok and (
        pw_ok or bilibili.get("ok") or zhihu.get("ok") or zhihu_openapi.get("ok") or deepseek.get("ok")
    )

    return {
        "items": items,
        "playwright_installed": pw_ok,
        "rookiepy_installed": rookie_ok,
        "blockers": blockers,
        "search_ready": search_ready,
        "project_root": str(_PROJECT_ROOT),
        "python": sys.executable,
    }


async def install_playwright(
    *,
    log_lines: list[str] | None = None,
    on_log: Callable[[str], None] | None = None,
    on_progress: Callable[[str, str, int, int], None] | None = None,
) -> dict[str, Any]:
    """pip install -e \".[browser]\" + playwright install msedge."""
    lines = log_lines if log_lines is not None else []

    def _log(msg: str) -> None:
        text = msg.strip()
        if not text:
            return
        lines.append(text)
        if on_log:
            on_log(text)

    if playwright_available():
        _log("playwright 包已存在，跳过 pip install")
        if on_progress:
            on_progress("pip", "playwright 包已存在", 1, 40)
    else:
        _log("安装 osint-toolkit[browser] …")
        if on_progress:
            on_progress("pip", "pip install osint-toolkit[browser]…", 0, 10)
        code = await _run_subprocess_stream(
            sys.executable,
            "-m",
            "pip",
            "install",
            "-e",
            ".[browser]",
            cwd=_PROJECT_ROOT,
            on_line=_log,
        )
        if code != 0:
            raise RuntimeError(f"pip install 失败 (exit {code})")
        if on_progress:
            on_progress("pip", "pip 安装完成", 1, 45)

    _log("安装 Playwright Edge 浏览器驱动 …")
    if on_progress:
        on_progress("playwright", "下载 Edge 驱动…", 1, 55)
    code = await _run_subprocess_stream(
        sys.executable,
        "-m",
        "playwright",
        "install",
        "msedge",
        cwd=_PROJECT_ROOT,
        on_line=_log,
    )
    if code != 0:
        raise RuntimeError(f"playwright install 失败 (exit {code})")

    if not playwright_available():
        raise RuntimeError("安装完成但仍无法 import playwright，请重启 Web 服务后重试")

    _log("Playwright 安装完成")
    if on_progress:
        on_progress("done", "Playwright 安装完成", 2, 100)
    return {"ok": True, "playwright_installed": True, "log": lines}


async def _run_subprocess_stream(*cmd: str, cwd: Path, on_line: Callable[[str], None] | None = None) -> int:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    assert proc.stdout is not None
    while True:
        chunk = await proc.stdout.readline()
        if not chunk:
            break
        line = chunk.decode("utf-8", errors="replace").rstrip()
        if line and on_line:
            on_line(line)
    await proc.wait()
    return proc.returncode or 0


async def _run_subprocess(*cmd: str, cwd: Path) -> tuple[int, str]:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    stdout, _ = await proc.communicate()
    text = (stdout or b"").decode("utf-8", errors="replace")
    return proc.returncode or 0, text
