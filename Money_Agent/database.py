#!/usr/bin/env python3
"""
SQLite 数据库模块
用于存储 Agent 运行数据，供 Web Dashboard 展示
"""

import sqlite3
import json
from datetime import datetime
from typing import Dict, Any, List, Optional
from pathlib import Path
from common.log_handler import logger

# 数据库文件路径
DB_PATH = Path(__file__).parent.parent / "data" / "agent_data.db"


class AgentDatabase:
    """Agent 数据库管理类"""
    
    def __init__(self, db_path: str = None):
        """初始化数据库连接"""
        self.db_path = db_path or str(DB_PATH)
        
        # 确保数据目录存在
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        
        # 初始化数据库表
        self._init_tables()
    
    def _get_connection(self):
        """获取数据库连接"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # 返回字典格式
        return conn
    
    def _init_tables(self):
        """初始化数据库表"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # 1. 账户价值历史表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS account_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                total_balance REAL NOT NULL,
                free_balance REAL NOT NULL,
                used_balance REAL NOT NULL,
                account_value REAL NOT NULL,
                return_pct REAL DEFAULT 0,
                sharpe_ratio REAL DEFAULT 0,
                max_drawdown REAL DEFAULT 0,
                win_rate REAL DEFAULT 0,
                total_trades INTEGER DEFAULT 0,
                minutes_elapsed INTEGER DEFAULT 0,
                btc_price REAL
            )
        """)
        
        # 如果表已存在，尝试添加 btc_price 字段
        try:
            cursor.execute("ALTER TABLE account_history ADD COLUMN btc_price REAL")
            logger.info("✅ 已添加 btc_price 字段到 account_history 表")
        except sqlite3.OperationalError:
            pass  # 字段已存在，忽略错误
        
        # 2. 持仓历史表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS position_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                contracts REAL NOT NULL,
                leverage INTEGER DEFAULT 1,
                entry_price REAL NOT NULL,
                mark_price REAL NOT NULL,
                liquidation_price REAL,
                unrealized_pnl REAL DEFAULT 0,
                percentage REAL DEFAULT 0,
                notional REAL DEFAULT 0,
                exit_plan TEXT,
                confidence REAL DEFAULT 0,
                risk_usd REAL DEFAULT 0
            )
        """)
        
        # 3. 交易历史表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trade_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                cycle INTEGER NOT NULL,
                coin TEXT NOT NULL,
                signal TEXT NOT NULL,
                side TEXT,
                quantity REAL,
                entry_price REAL,
                profit_target REAL,
                stop_loss REAL,
                leverage INTEGER DEFAULT 1,
                confidence REAL DEFAULT 0,
                risk_usd REAL DEFAULT 0,
                reasoning TEXT,
                invalidation_condition TEXT,
                execution_status TEXT,
                execution_message TEXT
            )
        """)
        
        # 4. AI 决策历史表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS decision_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                cycle INTEGER NOT NULL,
                decision_type TEXT NOT NULL,
                coin TEXT,
                signal TEXT,
                reasoning TEXT,
                confidence REAL DEFAULT 0,
                market_data TEXT,
                full_decision TEXT
            )
        """)
        
        # 5. 市场价格历史表（用于绘制价格曲线）
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS market_price_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                coin TEXT NOT NULL,
                price REAL NOT NULL,
                volume_24h REAL,
                change_24h REAL,
                funding_rate REAL,
                open_interest REAL
            )
        """)
        
        # 6. 系统日志表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS system_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                level TEXT NOT NULL,
                category TEXT,
                message TEXT NOT NULL,
                details TEXT
            )
        """)
        
        # 创建索引以提高查询性能
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_account_timestamp ON account_history(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_position_timestamp ON position_history(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_trade_timestamp ON trade_history(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_decision_timestamp ON decision_history(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_market_timestamp ON market_price_history(timestamp, coin)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON system_logs(timestamp)")
        
        conn.commit()
        conn.close()
    
    # ==================== 写入方法 ====================
    
    def save_account_snapshot(self, account_info: Dict[str, Any]):
        """保存账户快照"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # 获取当前 BTC 价格
        btc_price = None
        try:
            market_prices = self.get_latest_market_prices()
            if market_prices and 'BTC' in market_prices:
                btc_price = market_prices['BTC'].get('price')
        except:
            pass  # 如果获取失败，btc_price 保持为 None
        
        cursor.execute("""
            INSERT INTO account_history (
                total_balance, free_balance, used_balance, account_value,
                return_pct, sharpe_ratio, max_drawdown, win_rate,
                total_trades, minutes_elapsed, btc_price
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            account_info.get('total_balance', 0),
            account_info.get('free_balance', 0),
            account_info.get('used_balance', 0),
            account_info.get('account_value', 0),
            account_info.get('return_pct', 0),
            account_info.get('sharpe_ratio', 0),
            account_info.get('max_drawdown', 0),
            account_info.get('win_rate', 0),
            account_info.get('total_trades', 0),
            account_info.get('minutes_elapsed', 0),
            btc_price
        ))
        
        conn.commit()
        conn.close()
        logger.info(f"💾 账户快照已保存：${account_info.get('account_value', 0):.6f} (BTC: ${btc_price or 0:.6f})")
    
    def save_positions(self, positions: List[Dict[str, Any]]):
        """保存当前持仓（先清空旧数据）"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # 删除旧的持仓记录（保留历史快照）
        # 这里我们每次都插入新记录，以便追踪持仓变化
        
        for pos in positions:
            # 兼容蛇形和驼峰字段名
            contracts = pos.get('contracts')
            if contracts is None:
                contracts = pos.get('size', 0)
            
            entry_price = pos.get('entryPrice')
            if entry_price is None:
                entry_price = pos.get('entry_price', 0)
            
            mark_price = pos.get('markPrice')
            if mark_price is None:
                mark_price = pos.get('mark_price', 0)
            
            liquidation_price = pos.get('liquidationPrice')
            if liquidation_price is None:
                liquidation_price = pos.get('liquidation_price', 0)
            
            unrealized_pnl = pos.get('unrealizedPnl')
            if unrealized_pnl is None:
                unrealized_pnl = pos.get('unrealized_pnl', 0)
            
            cursor.execute("""
                INSERT INTO position_history (
                    symbol, side, contracts, leverage, entry_price, mark_price,
                    liquidation_price, unrealized_pnl, percentage, notional,
                    exit_plan, confidence, risk_usd
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                pos.get('symbol', ''),
                pos.get('side', ''),
                contracts,
                pos.get('leverage', 1),
                entry_price,
                mark_price,
                liquidation_price,
                unrealized_pnl,
                pos.get('percentage', 0),
                pos.get('notional', 0),
                json.dumps(pos.get('exit_plan', {})),
                pos.get('confidence', 0),
                pos.get('risk_usd', 0)
            ))
        
        conn.commit()
        conn.close()
        logger.info(f"💾 持仓已保存：{len(positions)} 个")
    
    def save_trade(self, cycle: int, decision: Dict[str, Any], execution_result: Dict[str, Any] = None):
        """保存交易记录"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # 🔥 字段名兼容：justification -> reasoning
        reasoning = decision.get('reasoning') or decision.get('justification', '')
        
        cursor.execute("""
            INSERT INTO trade_history (
                cycle, coin, signal, side, quantity, entry_price,
                profit_target, stop_loss, leverage, confidence, risk_usd,
                reasoning, invalidation_condition, execution_status, execution_message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            cycle,
            decision.get('coin', ''),
            decision.get('signal', ''),
            decision.get('side', ''),
            decision.get('quantity', 0),
            decision.get('entry_price', 0),
            decision.get('profit_target', 0),
            decision.get('stop_loss', 0),
            decision.get('leverage', 1),
            decision.get('confidence', 0),
            decision.get('risk_usd', 0),
            reasoning,
            decision.get('invalidation_condition', ''),
            execution_result.get('status', 'pending') if execution_result else 'pending',
            execution_result.get('message', '') if execution_result else ''
        ))
        
        conn.commit()
        conn.close()
        logger.info(f"💾 交易已保存：{decision.get('coin', '')} - {decision.get('signal', '')}")
    
    def save_decision(self, cycle: int, decision: Dict[str, Any], market_data: Dict[str, Any] = None):
        """保存 AI 决策"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # 字段名映射：justification -> reasoning (兼容前端)
        reasoning = decision.get('reasoning') or decision.get('justification', '')
        
        cursor.execute("""
            INSERT INTO decision_history (
                cycle, decision_type, coin, signal, reasoning, confidence,
                market_data, full_decision
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            cycle,
            decision.get('signal', 'hold'),
            decision.get('coin', ''),
            decision.get('signal', ''),
            reasoning,
            decision.get('confidence', 0),
            json.dumps(market_data) if market_data else None,
            json.dumps(decision)
        ))
        
        conn.commit()
        conn.close()
        logger.info(f"💾 决策已保存：周期 {cycle}")
    
    def save_market_prices(self, prices: Dict[str, Dict[str, Any]]):
        """保存市场价格"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        for coin, data in prices.items():
            cursor.execute("""
                INSERT INTO market_price_history (
                    coin, price, volume_24h, change_24h, funding_rate, open_interest
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (
                coin,
                data.get('price', 0),
                data.get('volume_24h', 0),
                data.get('change_24h', 0),
                data.get('funding_rate', 0),
                data.get('open_interest', 0)
            ))
        
        conn.commit()
        conn.close()
        logger.info(f"💾 市场价格已保存：{len(prices)} 个币种")
    
    def save_log(self, level: str, category: str, message: str, details: Dict[str, Any] = None):
        """保存系统日志"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO system_logs (level, category, message, details)
            VALUES (?, ?, ?, ?)
        """, (
            level,
            category,
            message,
            json.dumps(details) if details else None
        ))
        
        conn.commit()
        conn.close()
    
    # ==================== 读取方法（供 Web Server 使用）====================
    
    def get_latest_account(self) -> Optional[Dict[str, Any]]:
        """获取最新账户信息"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM account_history
            ORDER BY timestamp DESC
            LIMIT 1
        """)
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return dict(row)
        return None
    
    def get_account_history(self, hours: int = 24) -> List[Dict[str, Any]]:
        """获取账户历史（最近N小时）"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM account_history
            WHERE timestamp >= datetime('now', '-' || ? || ' hours')
            ORDER BY timestamp ASC
        """, (hours,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def get_current_positions(self) -> List[Dict[str, Any]]:
        """获取当前持仓（最新的一批）"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # 获取最新时间戳的所有持仓
        cursor.execute("""
            SELECT * FROM position_history
            WHERE timestamp = (SELECT MAX(timestamp) FROM position_history)
        """)
        
        rows = cursor.fetchall()
        conn.close()
        
        positions = []
        for row in rows:
            pos = dict(row)
            # 解析 JSON 字段
            if pos.get('exit_plan'):
                pos['exit_plan'] = json.loads(pos['exit_plan'])
            positions.append(pos)
        
        return positions
    
    def get_recent_trades(self, limit: int = 50) -> List[Dict[str, Any]]:
        """获取最近的交易记录"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM trade_history
            ORDER BY timestamp DESC
            LIMIT ?
        """, (limit,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def get_recent_decisions(self, limit: int = 50) -> List[Dict[str, Any]]:
        """获取最近的 AI 决策"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM decision_history
            ORDER BY timestamp DESC
            LIMIT ?
        """, (limit,))
        
        rows = cursor.fetchall()
        conn.close()
        
        decisions = []
        for row in rows:
            decision = dict(row)
            # 解析 JSON 字段
            if decision.get('market_data'):
                decision['market_data'] = json.loads(decision['market_data'])
            if decision.get('full_decision'):
                decision['full_decision'] = json.loads(decision['full_decision'])
            decisions.append(decision)
        
        return decisions
    
    def get_market_price_history(self, coin: str, hours: int = 24) -> List[Dict[str, Any]]:
        """获取市场价格历史"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM market_price_history
            WHERE coin = ? AND timestamp >= datetime('now', '-' || ? || ' hours')
            ORDER BY timestamp ASC
        """, (coin, hours))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def get_latest_market_prices(self) -> Dict[str, Dict[str, Any]]:
        """获取所有币种的最新价格"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT DISTINCT coin FROM market_price_history
        """)
        
        coins = [row[0] for row in cursor.fetchall()]
        
        prices = {}
        for coin in coins:
            cursor.execute("""
                SELECT * FROM market_price_history
                WHERE coin = ?
                ORDER BY timestamp DESC
                LIMIT 1
            """, (coin,))
            
            row = cursor.fetchone()
            if row:
                prices[coin] = dict(row)
        
        conn.close()
        return prices
    
    def get_recent_logs(self, limit: int = 100, level: str = None) -> List[Dict[str, Any]]:
        """获取最近的系统日志"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        if level:
            cursor.execute("""
                SELECT * FROM system_logs
                WHERE level = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (level, limit))
        else:
            cursor.execute("""
                SELECT * FROM system_logs
                ORDER BY timestamp DESC
                LIMIT ?
            """, (limit,))
        
        rows = cursor.fetchall()
        conn.close()
        
        logs = []
        for row in rows:
            log = dict(row)
            if log.get('details'):
                log['details'] = json.loads(log['details'])
            logs.append(log)
        
        return logs
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计数据"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # 获取最新账户信息
        latest_account = self.get_latest_account()
        
        # 获取交易统计
        cursor.execute("SELECT COUNT(*) as total FROM trade_history")
        total_trades = cursor.fetchone()[0]
        
        cursor.execute("""
            SELECT COUNT(*) as wins FROM trade_history
            WHERE execution_status = 'success'
        """)
        successful_trades = cursor.fetchone()[0]
        
        # 获取持仓统计
        cursor.execute("""
            SELECT COUNT(*) as count FROM position_history
            WHERE timestamp = (SELECT MAX(timestamp) FROM position_history)
        """)
        current_positions = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            'account': latest_account,
            'total_trades': total_trades,
            'successful_trades': successful_trades,
            'win_rate': (successful_trades / total_trades * 100) if total_trades > 0 else 0,
            'current_positions': current_positions
        }
    
    def cleanup_old_data(self, days: int = 30):
        """清理旧数据（保留最近N天）"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        tables = ['account_history', 'position_history', 'trade_history', 
                  'decision_history', 'market_price_history', 'system_logs']
        
        for table in tables:
            cursor.execute(f"""
                DELETE FROM {table}
                WHERE timestamp < datetime('now', '-' || ? || ' days')
            """, (days,))
        
        conn.commit()
        conn.close()
        
        logger.info(f"🧹 已清理 {days} 天前的旧数据")


# 全局数据库实例
_db_instance = None

def get_database() -> AgentDatabase:
    """获取数据库单例"""
    global _db_instance
    if _db_instance is None:
        _db_instance = AgentDatabase()
    return _db_instance


if __name__ == "__main__":
    # 测试数据库
    db = AgentDatabase()
    
    # 测试保存账户快照
    db.save_account_snapshot({
        'total_balance': 1000.0,
        'free_balance': 500.0,
        'used_balance': 500.0,
        'account_value': 1050.0,
        'return_pct': 5.0,
        'sharpe_ratio': 1.5,
        'max_drawdown': -2.0,
        'win_rate': 60.0,
        'total_trades': 10,
        'minutes_elapsed': 180
    })
    
    # 测试读取
    latest = db.get_latest_account()
    print(f"✅ 最新账户：{latest}")
    
    stats = db.get_statistics()
    print(f"✅ 统计数据：{stats}")
