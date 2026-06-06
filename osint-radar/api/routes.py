# API 路由定义

from __future__ import annotations

import asyncio
import uuid
from typing import Any, Dict, List

from fastapi import APIRouter, BackgroundTasks, HTTPException

from api import database as db
from api.models import (
    DanmakuAnalysisResponse,
    DanmakuRequest,
    HistoryItem,
    HistoryResponse,
    PlatformResultItem,
    QuickTaskResponse,
    SearchRequest,
    SearchResponse,
    SearchResultsResponse,
    SearchStatusResponse,
    TranscribeRequest,
    TranscribeResponse,
)
from api.scheduler import (
    run_quick_danmaku,
    run_quick_transcribe,
    run_search_task,
)

router = APIRouter(prefix="/api")


# ========== 搜索相关端点 ==========

@router.post("/search", response_model=SearchResponse)
async def create_search(
    request: SearchRequest,
    background_tasks: BackgroundTasks,
) -> SearchResponse:
    """发起搜索，启动后台任务调用各工具"""
    query_id = str(uuid.uuid4())
    platforms_str = ",".join(request.platforms)

    # 写入数据库
    db.insert_search_query(
        query_id=query_id,
        keyword=request.keyword,
        days=request.days,
        platforms=platforms_str,
        status="pending",
    )

    # 异步执行搜索任务
    background_tasks.add_task(
        run_search_task,
        query_id=query_id,
        keyword=request.keyword,
        days=request.days,
        platforms=request.platforms,
    )

    return SearchResponse(
        query_id=query_id,
        keyword=request.keyword,
        status="pending",
        message="搜索已提交，请通过 WebSocket 或状态接口查看进度",
    )


@router.get("/search/{query_id}/status", response_model=SearchStatusResponse)
async def get_search_status(query_id: str) -> SearchStatusResponse:
    """获取搜索状态"""
    record = db.get_search_query(query_id)
    if not record:
        raise HTTPException(status_code=404, detail="查询不存在")

    # 获取各平台结果数量作为进度参考
    results = db.get_platform_results(query_id)
    progress: Dict[str, Any] = {}
    platform_list = record["platforms"].split(",") if record["platforms"] else []

    for p in platform_list:
        p_results = [r for r in results if r.get("platform") == p]
        progress[p] = {
            "result_count": len(p_results),
            "status": "completed" if p_results else ("running" if record["status"] == "running" else "pending"),
        }

    # 弹幕和转写进度
    danmaku_analyses = db.get_danmaku_analyses(query_id)
    video_transcripts = db.get_video_transcripts(query_id)
    progress["danmaku"] = {"count": len(danmaku_analyses)}
    progress["transcripts"] = {"count": len(video_transcripts)}

    return SearchStatusResponse(
        query_id=record["query_id"],
        keyword=record["keyword"],
        platforms=record["platforms"],
        status=record["status"],
        created_at=record.get("created_at"),
        progress=progress,
    )


@router.get("/search/{query_id}/results", response_model=SearchResultsResponse)
async def get_search_results(query_id: str) -> SearchResultsResponse:
    """获取搜索结果"""
    record = db.get_search_query(query_id)
    if not record:
        raise HTTPException(status_code=404, detail="查询不存在")

    # 平台搜索结果
    platform_results = db.get_platform_results(query_id)
    results = [
        PlatformResultItem(
            id=r["id"],
            query_id=r["query_id"],
            platform=r["platform"],
            title=r.get("title"),
            content=r.get("content"),
            url=r.get("url"),
            author=r.get("author"),
            publish_time=r.get("publish_time"),
            comment_count=r.get("comment_count", 0),
            raw_data=r.get("raw_data"),
        )
        for r in platform_results
    ]

    # 弹幕分析结果
    danmaku_analyses = db.get_danmaku_analyses(query_id)
    danmaku_list = [dict(a) for a in danmaku_analyses]

    # 视频转文字结果
    video_transcripts = db.get_video_transcripts(query_id)
    transcript_list = [dict(t) for t in video_transcripts]

    return SearchResultsResponse(
        query_id=record["query_id"],
        keyword=record["keyword"],
        status=record["status"],
        results=results,
        danmaku_analyses=danmaku_list,
        video_transcripts=transcript_list,
    )


# ========== 快捷弹幕分析 ==========

@router.post("/quick/danmaku", response_model=QuickTaskResponse)
async def quick_danmaku(
    request: DanmakuRequest,
    background_tasks: BackgroundTasks,
) -> QuickTaskResponse:
    """快捷弹幕分析，直接调用 bilibili-danmaku 脚本"""
    task_id = str(uuid.uuid4())

    # 异步执行弹幕分析
    background_tasks.add_task(
        run_quick_danmaku,
        task_id=task_id,
        video_url=request.video_url,
        bvid=request.bvid,
    )

    return QuickTaskResponse(
        task_id=task_id,
        status="pending",
        message="弹幕分析任务已提交",
    )


# ========== 快捷视频转文字 ==========

@router.post("/quick/transcribe", response_model=QuickTaskResponse)
async def quick_transcribe(
    request: TranscribeRequest,
    background_tasks: BackgroundTasks,
) -> QuickTaskResponse:
    """快捷视频转文字"""
    task_id = str(uuid.uuid4())

    # 异步执行转写
    background_tasks.add_task(
        run_quick_transcribe,
        task_id=task_id,
        video_url=request.video_url,
    )

    return QuickTaskResponse(
        task_id=task_id,
        status="pending",
        message="视频转写任务已提交",
    )


# ========== 快捷任务结果查询 ==========

@router.get("/quick/{task_id}")
async def get_quick_task_result(task_id: str) -> Dict[str, Any]:
    """获取快捷任务结果（弹幕分析或视频转文字）"""
    # 先查弹幕分析表
    danmaku = db.get_danmaku_analysis_by_id(task_id)
    if danmaku:
        return {
            "type": "danmaku",
            "data": DanmakuAnalysisResponse(
                task_id=danmaku["id"],
                video_url=danmaku.get("video_url"),
                video_title=danmaku.get("video_title"),
                total_danmaku=danmaku.get("total_danmaku", 0),
                positive=danmaku.get("positive", 0),
                neutral=danmaku.get("neutral", 0),
                negative=danmaku.get("negative", 0),
                avg_score=danmaku.get("avg_score", 0.0),
                wordcloud_path=danmaku.get("wordcloud_path"),
                report_path=danmaku.get("report_path"),
                top_words=danmaku.get("top_words"),
                status="completed" if danmaku.get("report_path") else "pending",
            ),
        }

    # 再查视频转文字表
    transcript = db.get_video_transcript_by_id(task_id)
    if transcript:
        return {
            "type": "transcribe",
            "data": TranscribeResponse(
                task_id=transcript["id"],
                video_url=transcript.get("video_url") or "",
                video_title=transcript.get("video_title"),
                transcript_path=transcript.get("transcript_path"),
                status=transcript.get("status", "pending"),
            ),
        }

    raise HTTPException(status_code=404, detail="任务不存在")


# ========== 搜索历史 ==========

@router.get("/history", response_model=HistoryResponse)
async def get_history(
    limit: int = 50,
    offset: int = 0,
) -> HistoryResponse:
    """获取搜索历史"""
    items = db.get_search_history(limit=limit, offset=offset)
    total = db.get_search_history_count()

    return HistoryResponse(
        total=total,
        items=[
            HistoryItem(
                query_id=item["query_id"],
                keyword=item["keyword"],
                platforms=item["platforms"],
                status=item["status"],
                created_at=item.get("created_at"),
            )
            for item in items
        ],
    )
