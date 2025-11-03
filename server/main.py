#!/usr/bin/env python3
"""
AI Money Agent - Web Dashboard Server
提供实时数据展示的 FastAPI 服务器
"""

import asyncio
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv()

from Money_Agent.database import get_database

app = FastAPI(title="AI Money Agent Dashboard")

# CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载静态文件
web_dir = project_root / "web"
if web_dir.exists():
    app.mount("/static", StaticFiles(directory=str(web_dir)), name="static")

# 全局数据库实例
db = None

# WebSocket 连接管理
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections[:]:
            try:
                await connection.send_json(message)
            except:
                self.disconnect(connection)

manager = ConnectionManager()


def get_db_data() -> Dict[str, Any]:
    """从数据库获取所有需要的数据"""
    # 获取最新账户信息
    account = db.get_latest_account()
    
    # 获取当前持仓
    positions = db.get_current_positions()
    
    # 获取最新市场价格
    market_prices = db.get_latest_market_prices()
    
    # 获取最近交易
    trades = db.get_recent_trades(limit=20)
    
    # 获取最近决策
    decisions = db.get_recent_decisions(limit=20)
    
    return {
        "account": account,
        "positions": positions,
        "market_prices": market_prices,
        "trades": trades,
        "decisions": decisions
    }


@app.on_event("startup")
async def startup_event():
    """启动时初始化"""
    global db
    db = get_database()
    print("✅ AI Money Agent Dashboard 已启动")
    print(f"📊 访问地址: http://localhost:8000")
    print(f"💾 数据库路径: {db.db_path}")


@app.on_event("shutdown")
async def shutdown_event():
    """关闭时清理"""
    print("\n🛑 正在关闭服务器...")
    for connection in manager.active_connections[:]:
        try:
            await connection.close()
        except:
            pass
    manager.active_connections.clear()
    print("✅ 服务器已关闭")


@app.get("/")
async def get_index():
    """返回主页"""
    index_file = web_dir / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"message": "Dashboard HTML not found"}


@app.get("/api/account/history")
async def get_account_history(hours: int = 24):
    """获取账户历史数据（用于绘制曲线）"""
    try:
        history = db.get_account_history(hours=hours)
        return {"success": True, "data": {"history": history}}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/api/trades")
async def get_trades(limit: int = 50):
    """获取最近的交易记录"""
    try:
        trades = db.get_recent_trades(limit=limit)
        return {"success": True, "data": {"recent_trades": trades}}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/api/decisions")
async def get_decisions(limit: int = 50):
    """获取最近的决策记录"""
    try:
        decisions = db.get_recent_decisions(limit=limit)
        return {"success": True, "data": {"recent_decisions": decisions}}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/api/logs")
async def get_logs(limit: int = 100):
    """获取系统日志"""
    try:
        logs = db.get_recent_logs(limit=limit)
        return {"success": True, "data": {"logs": logs}}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket 端点，用于实时数据推送"""
    await manager.connect(websocket)
    
    try:
        # 发送初始数据
        data = get_db_data()
        await websocket.send_json({
            "type": "initial_state",
            "data": {
                "balance": data["account"],
                "positions": data["positions"],
                "market_prices": data["market_prices"],
                "trades": data["trades"],
                "decisions": data["decisions"]
            }
        })
        
        # 记录上次数据用于变化检测
        last_account_value = data["account"]["account_value"] if data["account"] else None
        last_positions_count = len(data["positions"])
        
        # 持续推送更新
        while True:
            await asyncio.sleep(5)  # 每5秒检查一次
            
            # 获取最新数据
            data = get_db_data()
            account = data["account"]
            
            if not account:
                continue
            
            # 检测数据变化
            current_value = account["account_value"]
            current_positions_count = len(data["positions"])
            
            has_changed = (
                last_account_value is None or
                abs(current_value - last_account_value) > 0.01 or
                current_positions_count != last_positions_count
            )
            
            # 只在数据变化时推送
            if has_changed:
                await websocket.send_json({
                    "type": "update",
                    "data": {
                        "balance": account,
                        "positions": data["positions"],
                        "market_prices": data["market_prices"],
                        "trades": data["trades"],
                        "decisions": data["decisions"]
                    }
                })
                
                last_account_value = current_value
                last_positions_count = current_positions_count
            
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        print(f"WebSocket 错误: {e}")
        manager.disconnect(websocket)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")