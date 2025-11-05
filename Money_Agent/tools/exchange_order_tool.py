"""
交易所订单和历史工具

此模块的核心功能是获取历史仓位数据。
"""

from common.log_handler import logger
from typing import List, Dict, Any
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

def get_positions_history(exchange, day_offset: int = 1, limit: int = 100) -> List[Dict[str, Any]]:
    """获取历史仓位记录

    通过一次API调用获取所有币种的仓位历史，然后返回。

    Args:
        exchange: 交易所实例
        day_offset: 获取N天前的数据 (1 表示昨天, 0 表示今天)
        limit: 最多获取的记录数量
    
    Returns:
        历史仓位列表
    """
    try:
        if not (hasattr(exchange, 'apiKey') and exchange.apiKey):
            logger.warning("⚠️ 未配置API密钥，无法获取历史仓位")
            return []

        if not exchange.has.get('fetchPositionsHistory'):
            logger.error(f"❌ 交易所 {exchange.id} 不支持 fetchPositionsHistory 方法。")
            return []

        # --- 时间范围计算 (北京时间) ---
        tz_beijing = ZoneInfo("Asia/Shanghai")
        now_bjt = datetime.now(tz_beijing)
        
        # 从当前时间往前推 N*24 小时
        start_dt_bjt = now_bjt - timedelta(days=day_offset)
        
        since_ms = int(start_dt_bjt.timestamp() * 1000)
        params = {'endTime': int(now_bjt.timestamp() * 1000)}

        logger.info(f"📥 正在获取所有交易对的历史仓位 {since_ms} --- {params['endTime']}...")

        # 不提供 symbol 参数，一次性获取所有币种的历史仓位
        all_positions = exchange.fetch_positions_history(since=since_ms, limit=limit, params=params)
        
        # 按时间倒序排列 (使用平仓时间戳)
        all_positions.sort(key=lambda p: p.get('timestamp', 0), reverse=True)
        
        logger.info(f"✅ 共获取 {len(all_positions)} 条历史仓位记录")
        return all_positions
    
    except Exception as e:
        logger.error(f"❌ 获取历史仓位失败: {e}", exc_info=True)
        return []
