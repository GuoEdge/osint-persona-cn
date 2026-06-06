# 任务调度器 - 异步调用各工具并推送进度

from __future__ import annotations

import asyncio
import glob
import json
import os
import re
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from fastapi import WebSocket

from api import database as db

# 输出根目录
OUTPUT_ROOT = "/workspace/osint_output"

# 各工具路径
MEDIACRAWLER_DIR = "/workspace/MediaCrawler"
BILIBILI_DANMAKU_FETCH = "/workspace/bilibili-danmaku/scripts/fetch_danmaku.py"
BILIBILI_DANMAKU_ANALYZE = "/workspace/bilibili-danmaku/scripts/analyze_danmaku.py"
BILI2TEXT_DIR = "/workspace/bili2text"
TRENDRADAR_DIR = "/workspace/TrendRadar"

# MediaCrawler 平台映射（前端传入的平台名 -> MediaCrawler 内部平台名）
PLATFORM_MAP = {
    "xhs": "xhs",
    "xiaohongshu": "xhs",
    "dy": "dy",
    "douyin": "dy",
    "ks": "ks",
    "kuaishou": "ks",
    "bili": "bili",
    "bilibili": "bili",
    "wb": "wb",
    "weibo": "wb",
    "tieba": "tieba",
    "zhihu": "zhihu",
}

# 全局 WebSocket 连接池
_ws_connections: Dict[str, WebSocket] = {}


def register_ws(query_id: str, websocket: WebSocket) -> None:
    """注册 WebSocket 连接"""
    _ws_connections[query_id] = websocket


def unregister_ws(query_id: str) -> None:
    """移除 WebSocket 连接"""
    _ws_connections.pop(query_id, None)


async def push_progress(
    query_id: str,
    platform: str,
    status: str,
    progress: int,
    message: str,
) -> None:
    """通过 WebSocket 推送进度消息"""
    ws = _ws_connections.get(query_id)
    if ws is None:
        return
    payload = {
        "type": "progress",
        "platform": platform,
        "status": status,
        "progress": progress,
        "message": message,
    }
    try:
        await ws.send_json(payload)
    except Exception:
        # 连接已断开，移除
        unregister_ws(query_id)


async def run_subprocess(
    cmd: str,
    cwd: Optional[str] = None,
    timeout: int = 600,
) -> tuple[int, str, str]:
    """异步执行子进程命令

    返回: (return_code, stdout, stderr)
    """
    proc = await asyncio.create_subprocess_shell(
        cmd,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )
    except asyncio.TimeoutError:
        proc.kill()
        return -1, "", "命令执行超时"
    stdout = stdout_bytes.decode("utf-8", errors="replace")
    stderr = stderr_bytes.decode("utf-8", errors="replace")
    return proc.returncode or -1, stdout, stderr


# ========== 搜索任务 ==========

async def run_search_task(
    query_id: str,
    keyword: str,
    days: int,
    platforms: List[str],
) -> None:
    """执行完整的搜索任务流程"""
    try:
        db.update_search_status(query_id, "running")

        # 1) 调用 MediaCrawler 进行多平台搜索
        await _run_mediacrawler_search(query_id, keyword, platforms)

        # 2) 调用 TrendRadar 获取全网热点
        await _run_trendradar(query_id, keyword)

        # 3) 对搜索到的B站视频进行弹幕分析
        await _run_danmaku_for_bili_results(query_id)

        # 4) 对搜索到的视频进行转文字
        await _run_transcribe_for_video_results(query_id)

        db.update_search_status(query_id, "completed")
        await push_progress(query_id, "all", "completed", 100, "搜索任务全部完成")

    except Exception as e:
        db.update_search_status(query_id, "failed")
        await push_progress(query_id, "all", "failed", 0, f"搜索任务失败: {e}")


async def _run_mediacrawler_search(
    query_id: str,
    keyword: str,
    platforms: List[str],
) -> None:
    """调用 MediaCrawler 搜索各平台"""
    total = len(platforms)
    if total == 0:
        return

    for idx, platform in enumerate(platforms):
        mc_platform = PLATFORM_MAP.get(platform, platform)
        await push_progress(
            query_id, platform, "running",
            int(idx / total * 60),
            f"正在搜索 {platform}...",
        )

        # 构建输出目录
        output_dir = os.path.join(OUTPUT_ROOT, query_id, "search")
        os.makedirs(output_dir, exist_ok=True)

        cmd = (
            f"cd {MEDIACRAWLER_DIR} && "
            f"uv run main.py --platform {mc_platform} --lt qrcode --type search "
            f"--keywords '{keyword}' --save_data_option json "
            f"--save_data_path {output_dir} --headless true"
        )
        returncode, stdout, stderr = await run_subprocess(cmd, timeout=600)

        if returncode == 0:
            await push_progress(
                query_id, platform, "completed",
                int((idx + 1) / total * 60),
                f"{platform} 搜索完成",
            )
            # 解析搜索结果并入库
            _parse_and_save_search_results(query_id, platform, output_dir)
        else:
            await push_progress(
                query_id, platform, "failed",
                int((idx + 1) / total * 60),
                f"{platform} 搜索失败: {stderr[:200]}",
            )


def _parse_and_save_search_results(
    query_id: str, platform: str, output_dir: str
) -> None:
    """解析 MediaCrawler 输出的 JSON 文件并入库"""
    # MediaCrawler json 输出在 save_data_path 下
    json_pattern = os.path.join(output_dir, "**", "*.json")
    json_files = glob.glob(json_pattern, recursive=True)

    rows = []
    for jf in json_files:
        try:
            with open(jf, "r", encoding="utf-8") as f:
                data = json.load(f)

            # MediaCrawler 的 JSON 可能是列表或单条
            items = data if isinstance(data, list) else [data]
            for item in items:
                if not isinstance(item, dict):
                    continue
                result_id = item.get("note_id") or item.get("video_id") or str(uuid.uuid4())
                title = item.get("title") or item.get("note_id") or ""
                content = item.get("desc") or item.get("content") or ""
                url = item.get("url") or item.get("note_url") or ""
                author = item.get("nickname") or item.get("user") or ""
                publish_time = item.get("create_time") or item.get("published_time") or ""
                comment_count = item.get("comment_count", 0) or 0
                rows.append((
                    str(uuid.uuid4()), query_id, platform,
                    title, content, url, author,
                    str(publish_time), comment_count,
                    json.dumps(item, ensure_ascii=False),
                ))
        except Exception:
            continue

    if rows:
        db.insert_platform_results_batch(rows)


async def _run_trendradar(query_id: str, keyword: str) -> None:
    """调用 TrendRadar 获取全网热点"""
    await push_progress(query_id, "trendradar", "running", 65, "正在获取全网热点...")

    output_dir = os.path.join(OUTPUT_ROOT, query_id, "trendradar")
    os.makedirs(output_dir, exist_ok=True)

    cmd = f"cd {TRENDRADAR_DIR} && uv run python -m trendradar"
    returncode, stdout, stderr = await run_subprocess(cmd, timeout=300)

    if returncode == 0:
        await push_progress(query_id, "trendradar", "completed", 70, "全网热点获取完成")
    else:
        await push_progress(query_id, "trendradar", "failed", 70, f"全网热点获取失败: {stderr[:200]}")


async def _run_danmaku_for_bili_results(query_id: str) -> None:
    """对搜索到的B站视频进行弹幕分析"""
    results = db.get_platform_results(query_id)
    bili_results = [r for r in results if r.get("platform") in ("bili", "bilibili")]

    if not bili_results:
        return

    total = len(bili_results)
    for idx, result in enumerate(bili_results):
        url = result.get("url") or ""
        raw_data_str = result.get("raw_data") or "{}"
        try:
            raw_data = json.loads(raw_data_str) if raw_data_str else {}
        except json.JSONDecodeError:
            raw_data = {}

        # 从 URL 或 raw_data 中提取 BV 号
        bvid = _extract_bvid(url) or raw_data.get("bvid") or raw_data.get("video_id")
        if not bvid:
            continue

        analysis_id = str(uuid.uuid4())
        db.insert_danmaku_analysis(
            analysis_id=analysis_id,
            query_id=query_id,
            video_url=url,
        )

        progress_base = 70 + int(idx / total * 20)
        await push_progress(
            query_id, f"danmaku_{bvid}", "running",
            progress_base, f"正在分析弹幕 {bvid}...",
        )

        # 抓取弹幕
        danmaku_dir = os.path.join(OUTPUT_ROOT, query_id, "danmaku")
        os.makedirs(danmaku_dir, exist_ok=True)

        fetch_cmd = (
            f"python3 {BILIBILI_DANMAKU_FETCH} "
            f"--bvid {bvid} --outdir {danmaku_dir}"
        )
        returncode, stdout, stderr = await run_subprocess(fetch_cmd, timeout=120)

        if returncode != 0:
            await push_progress(
                query_id, f"danmaku_{bvid}", "failed",
                progress_base, f"弹幕抓取失败: {stderr[:200]}",
            )
            continue

        # 查找输出的 CSV 和 meta 文件
        csv_path, meta_path = _find_danmaku_output(danmaku_dir, bvid)
        if not csv_path:
            await push_progress(
                query_id, f"danmaku_{bvid}", "failed",
                progress_base, f"未找到弹幕 CSV 文件",
            )
            continue

        # 分析弹幕
        analyze_dir = os.path.join(OUTPUT_ROOT, query_id, "danmaku_analysis")
        os.makedirs(analyze_dir, exist_ok=True)
        safe_name = re.sub(r"[^0-9A-Za-z_\-\u4e00-\u9fff]", "_", bvid)

        analyze_cmd = (
            f"python3 {BILIBILI_DANMAKU_ANALYZE} "
            f"--csv {csv_path} "
            + (f"--meta {meta_path} " if meta_path else "")
            + f"--outdir {analyze_dir} --name {safe_name}"
        )
        returncode, stdout, stderr = await run_subprocess(analyze_cmd, timeout=120)

        if returncode == 0:
            # 读取分析结果
            _update_danmaku_analysis_from_output(analysis_id, analyze_dir, safe_name)
            await push_progress(
                query_id, f"danmaku_{bvid}", "completed",
                progress_base + int(1 / total * 20),
                f"弹幕分析完成 {bvid}",
            )
        else:
            await push_progress(
                query_id, f"danmaku_{bvid}", "failed",
                progress_base, f"弹幕分析失败: {stderr[:200]}",
            )


async def _run_transcribe_for_video_results(query_id: str) -> None:
    """对搜索到的视频进行转文字"""
    results = db.get_platform_results(query_id)
    # 收集所有含 URL 的视频结果
    video_results = [r for r in results if r.get("url")]

    if not video_results:
        return

    total = len(video_results)
    for idx, result in enumerate(video_results):
        url = result.get("url") or ""
        if not url:
            continue

        transcript_id = str(uuid.uuid4())
        db.insert_video_transcript(
            transcript_id=transcript_id,
            query_id=query_id,
            video_url=url,
        )

        progress_base = 90 + int(idx / max(total, 1) * 10)
        await push_progress(
            query_id, f"transcribe_{idx}", "running",
            progress_base, f"正在转写视频...",
        )

        output_dir = os.path.join(OUTPUT_ROOT, query_id, "transcripts")
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f"{transcript_id}.txt")

        cmd = (
            f"cd {BILI2TEXT_DIR} && "
            f"uv run bili2text transcribe '{url}' --output {output_path}"
        )
        returncode, stdout, stderr = await run_subprocess(cmd, timeout=600)

        if returncode == 0:
            db.update_video_transcript(
                transcript_id=transcript_id,
                transcript_path=output_path,
                status="completed",
            )
            await push_progress(
                query_id, f"transcribe_{idx}", "completed",
                progress_base, "视频转写完成",
            )
        else:
            db.update_video_transcript(
                transcript_id=transcript_id,
                status="failed",
            )
            await push_progress(
                query_id, f"transcribe_{idx}", "failed",
                progress_base, f"视频转写失败: {stderr[:200]}",
            )


# ========== 快捷弹幕分析 ==========

async def run_quick_danmaku(
    task_id: str,
    video_url: str,
    bvid: Optional[str] = None,
) -> None:
    """快捷弹幕分析（不需要登录态）"""
    # 提取 BV 号
    if not bvid:
        bvid = _extract_bvid(video_url)
    if not bvid:
        db.update_danmaku_analysis(
            analysis_id=task_id,
            report_path="",
        )
        return

    db.insert_danmaku_analysis(
        analysis_id=task_id,
        query_id="quick",
        video_url=video_url,
    )

    output_dir = os.path.join(OUTPUT_ROOT, "quick_danmaku")
    os.makedirs(output_dir, exist_ok=True)

    # 1) 抓取弹幕
    fetch_cmd = (
        f"python3 {BILIBILI_DANMAKU_FETCH} "
        f"--bvid {bvid} --outdir {output_dir}"
    )
    returncode, stdout, stderr = await run_subprocess(fetch_cmd, timeout=120)

    if returncode != 0:
        db.update_danmaku_analysis(analysis_id=task_id, report_path="")
        return

    # 2) 查找输出文件
    csv_path, meta_path = _find_danmaku_output(output_dir, bvid)
    if not csv_path:
        db.update_danmaku_analysis(analysis_id=task_id, report_path="")
        return

    # 3) 分析弹幕
    analyze_dir = os.path.join(OUTPUT_ROOT, "quick_danmaku_analysis")
    os.makedirs(analyze_dir, exist_ok=True)
    safe_name = re.sub(r"[^0-9A-Za-z_\-\u4e00-\u9fff]", "_", bvid)

    analyze_cmd = (
        f"python3 {BILIBILI_DANMAKU_ANALYZE} "
        f"--csv {csv_path} "
        + (f"--meta {meta_path} " if meta_path else "")
        + f"--outdir {analyze_dir} --name {safe_name}"
    )
    returncode, stdout, stderr = await run_subprocess(analyze_cmd, timeout=120)

    if returncode == 0:
        _update_danmaku_analysis_from_output(task_id, analyze_dir, safe_name)
    else:
        db.update_danmaku_analysis(analysis_id=task_id, report_path="")


# ========== 快捷视频转文字 ==========

async def run_quick_transcribe(
    task_id: str,
    video_url: str,
) -> None:
    """快捷视频转文字"""
    db.insert_video_transcript(
        transcript_id=task_id,
        query_id="quick",
        video_url=video_url,
    )

    output_dir = os.path.join(OUTPUT_ROOT, "quick_transcripts")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"{task_id}.txt")

    cmd = (
        f"cd {BILI2TEXT_DIR} && "
        f"uv run bili2text transcribe '{video_url}' --output {output_path}"
    )
    returncode, stdout, stderr = await run_subprocess(cmd, timeout=600)

    if returncode == 0:
        db.update_video_transcript(
            transcript_id=task_id,
            transcript_path=output_path,
            status="completed",
        )
    else:
        db.update_video_transcript(
            transcript_id=task_id,
            status="failed",
        )


# ========== 辅助函数 ==========

def _extract_bvid(url: str) -> Optional[str]:
    """从 URL 中提取 BV 号"""
    if not url:
        return None
    m = re.search(r"/(BV[0-9A-Za-z]+)", url)
    return m.group(1) if m else None


def _find_danmaku_output(danmaku_dir: str, bvid: str) -> tuple[Optional[str], Optional[str]]:
    """查找弹幕抓取输出的 CSV 和 meta 文件"""
    csv_path = None
    meta_path = None

    # 查找包含 bvid 的文件
    for f in os.listdir(danmaku_dir):
        if bvid in f and f.endswith("_danmaku.csv"):
            csv_path = os.path.join(danmaku_dir, f)
        elif bvid in f and f.endswith("_meta.json"):
            meta_path = os.path.join(danmaku_dir, f)

    # 如果没找到精确匹配，取最新的文件
    if not csv_path:
        csv_files = sorted(
            glob.glob(os.path.join(danmaku_dir, "*_danmaku.csv")),
            key=os.path.getmtime,
            reverse=True,
        )
        if csv_files:
            csv_path = csv_files[0]

    if not meta_path:
        meta_files = sorted(
            glob.glob(os.path.join(danmaku_dir, "*_meta.json")),
            key=os.path.getmtime,
            reverse=True,
        )
        if meta_files:
            meta_path = meta_files[0]

    return csv_path, meta_path


def _update_danmaku_analysis_from_output(
    analysis_id: str,
    analyze_dir: str,
    name_prefix: str,
) -> None:
    """从分析输出文件中读取结果并更新数据库"""
    sentiment_path = os.path.join(analyze_dir, f"{name_prefix}_sentiment.json")
    top_words_path = os.path.join(analyze_dir, f"{name_prefix}_top_words.json")
    wordcloud_path = os.path.join(analyze_dir, f"{name_prefix}_wordcloud.png")
    report_path = os.path.join(analyze_dir, f"{name_prefix}_report.md")

    # 读取情感分析结果
    total_danmaku = 0
    positive = 0
    neutral = 0
    negative = 0
    avg_score = 0.0
    video_title = None
    top_words_str = None

    if os.path.exists(sentiment_path):
        try:
            with open(sentiment_path, "r", encoding="utf-8") as f:
                sentiment = json.load(f)
            total_danmaku = sentiment.get("total", 0)
            distribution = sentiment.get("distribution", {})
            positive = distribution.get("positive", 0)
            neutral = distribution.get("neutral", 0)
            negative = distribution.get("negative", 0)
            avg_score = sentiment.get("avg_score", 0.0)
        except Exception:
            pass

    # 读取 meta 获取视频标题
    meta_files = glob.glob(os.path.join(os.path.dirname(analyze_dir), "**", "*_meta.json"), recursive=True)
    if meta_files:
        try:
            with open(meta_files[0], "r", encoding="utf-8") as f:
                meta = json.load(f)
            video_title = (meta.get("video") or {}).get("title")
        except Exception:
            pass

    # 读取热词
    if os.path.exists(top_words_path):
        try:
            with open(top_words_path, "r", encoding="utf-8") as f:
                top_words_data = json.load(f)
            top_words_str = json.dumps(top_words_data[:30], ensure_ascii=False)
        except Exception:
            pass

    db.update_danmaku_analysis(
        analysis_id=analysis_id,
        video_title=video_title,
        total_danmaku=total_danmaku,
        positive=positive,
        neutral=neutral,
        negative=negative,
        avg_score=avg_score,
        wordcloud_path=wordcloud_path if os.path.exists(wordcloud_path) else None,
        report_path=report_path if os.path.exists(report_path) else None,
        top_words=top_words_str,
    )
