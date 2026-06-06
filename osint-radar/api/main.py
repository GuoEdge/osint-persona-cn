# FastAPI 主入口

from __future__ import annotations

import os

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api import database as db
from api.models import WSProgressMessage
from api.routes import router
from api.scheduler import register_ws, unregister_ws

# 输出目录
OUTPUT_DIR = "/workspace/osint_output"

# 创建 FastAPI 应用
app = FastAPI(
    title="OSINT Radar API",
    description="开源情报聚合分析平台后端服务",
    version="0.1.0",
)

# CORS 允许所有来源
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册 API 路由
app.include_router(router)


@app.on_event("startup")
async def on_startup() -> None:
    """应用启动时初始化数据库"""
    db.init_db()
    # 确保输出目录存在
    os.makedirs(OUTPUT_DIR, exist_ok=True)


# ========== WebSocket 端点 ==========

@app.websocket("/ws/search/{query_id}")
async def websocket_search_progress(websocket: WebSocket, query_id: str) -> None:
    """WebSocket 端点，用于实时推送采集进度"""
    await websocket.accept()
    register_ws(query_id, websocket)
    try:
        # 保持连接，等待客户端断开
        while True:
            # 接收客户端消息（心跳等）
            data = await websocket.receive_text()
            # 客户端发送 "ping" 则回复 "pong"
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        pass
    finally:
        unregister_ws(query_id)


# ========== 静态文件服务 ==========

# 确保输出目录存在后挂载静态文件
os.makedirs(OUTPUT_DIR, exist_ok=True)
app.mount(
    "/output",
    StaticFiles(directory=OUTPUT_DIR, html=True),
    name="output",
)


# ========== 健康检查 ==========

@app.get("/health")
async def health_check() -> dict:
    """健康检查端点"""
    return {"status": "ok", "service": "osint-radar-api"}
