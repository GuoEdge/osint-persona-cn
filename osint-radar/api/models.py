# Pydantic 数据模型定义

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ========== 请求模型 ==========

class SearchRequest(BaseModel):
    """搜索请求"""
    keyword: str = Field(..., description="搜索关键词")
    days: int = Field(7, description="搜索时间范围（天）")
    platforms: List[str] = Field(
        default_factory=lambda: ["xhs", "bili", "wb", "zhihu", "dy", "ks", "tieba"],
        description="搜索平台列表",
    )


class DanmakuRequest(BaseModel):
    """快捷弹幕分析请求"""
    video_url: str = Field(..., description="B站视频URL或BV号")
    bvid: Optional[str] = Field(None, description="BV号（可选，与video_url二选一）")


class TranscribeRequest(BaseModel):
    """快捷视频转文字请求"""
    video_url: str = Field(..., description="B站视频URL")


# ========== 响应模型 ==========

class SearchResponse(BaseModel):
    """搜索响应"""
    query_id: str = Field(..., description="查询ID")
    keyword: str = Field(..., description="搜索关键词")
    status: str = Field("pending", description="搜索状态")
    message: str = Field("搜索已提交", description="状态消息")


class SearchStatusResponse(BaseModel):
    """搜索状态响应"""
    query_id: str
    keyword: str
    platforms: str
    status: str
    created_at: Optional[str] = None
    progress: Dict[str, Any] = Field(
        default_factory=dict, description="各平台进度详情"
    )


class PlatformResultItem(BaseModel):
    """单条平台搜索结果"""
    id: str
    query_id: str
    platform: str
    title: Optional[str] = None
    content: Optional[str] = None
    url: Optional[str] = None
    author: Optional[str] = None
    publish_time: Optional[str] = None
    comment_count: int = 0
    raw_data: Optional[str] = None


class SearchResultsResponse(BaseModel):
    """搜索结果响应"""
    query_id: str
    keyword: str
    status: str
    results: List[PlatformResultItem] = Field(default_factory=list)
    danmaku_analyses: List[Dict[str, Any]] = Field(default_factory=list)
    video_transcripts: List[Dict[str, Any]] = Field(default_factory=list)


class DanmakuAnalysisResponse(BaseModel):
    """弹幕分析结果响应"""
    task_id: str
    video_url: Optional[str] = None
    video_title: Optional[str] = None
    total_danmaku: int = 0
    positive: int = 0
    neutral: int = 0
    negative: int = 0
    avg_score: float = 0.0
    wordcloud_path: Optional[str] = None
    report_path: Optional[str] = None
    top_words: Optional[str] = None
    status: str = "pending"


class TranscribeResponse(BaseModel):
    """视频转文字响应"""
    task_id: str
    video_url: str
    video_title: Optional[str] = None
    transcript_path: Optional[str] = None
    status: str = "pending"


class QuickTaskResponse(BaseModel):
    """快捷任务提交响应"""
    task_id: str = Field(..., description="任务ID")
    status: str = Field("pending", description="任务状态")
    message: str = Field("任务已提交", description="状态消息")


class HistoryItem(BaseModel):
    """搜索历史条目"""
    query_id: str
    keyword: str
    platforms: str
    status: str
    created_at: Optional[str] = None


class HistoryResponse(BaseModel):
    """搜索历史响应"""
    total: int
    items: List[HistoryItem]


# ========== WebSocket 消息模型 ==========

class WSProgressMessage(BaseModel):
    """WebSocket 进度推送消息"""
    type: str = "progress"
    platform: str = Field(..., description="平台名称")
    status: str = Field(..., description="状态: running/completed/failed")
    progress: int = Field(0, description="进度百分比 0-100")
    message: str = Field("", description="状态描述")
