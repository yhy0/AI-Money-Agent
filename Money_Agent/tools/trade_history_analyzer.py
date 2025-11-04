"""
交易历史分析工具 (最终版)

提供两个独立的、目标明确的函数：
1. generate_user_report: 生成给用户看的 Markdown 报告。
2. generate_llm_data: 生成给 LLM 使用的 JSON 结构化数据。
"""

import asyncio
from typing import List, Dict, Any, Tuple
from common.log_handler import logger
from datetime import datetime, timezone, timedelta
from .exchange_order_tool import get_positions_history

# --- 私有辅助函数 ---

def _process_positions_data(positions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """将原始仓位数据转换为干净的内部格式"""
    processed_trades = []
    for pos in positions:
        info = pos.get('info', {})
        net_profit = float(info.get('netProfit', 0))
        if net_profit == 0:
            continue

        position_side = info.get('holdSide', '')
        position_type = 'buy_to_enter(开多)' if position_side == 'long' else 'sell_to_enter(开空)'

        entry_price = float(info.get('openAvgPrice', 0))
        total_size = float(info.get('openTotalPos', 0))
        cost = entry_price * total_size
        profit_pct = (net_profit / cost * 100) if cost > 0 else 0

        close_timestamp_ms = int(info.get('utime', 0))
        utc_dt = datetime.fromtimestamp(close_timestamp_ms / 1000, tz=timezone.utc)
        bjt_dt = utc_dt.astimezone(timezone(timedelta(hours=8)))
        formatted_bjt_time = bjt_dt.strftime('%Y-%m-%d %H:%M:%S')

        processed_trades.append({
            'symbol': info.get('symbol', '').replace('USDT', ''),
            'position_type': position_type,
            'amount': total_size,
            'entry_price': entry_price,
            'exit_price': float(info.get('closeAvgPrice', 0)),
            'net_profit_usd': round(net_profit, 4),
            'profit_pct': round(profit_pct, 2),
            'datetime': formatted_bjt_time,
            'timestamp': close_timestamp_ms
        })
    
    processed_trades.sort(key=lambda x: x['timestamp'], reverse=True)
    return processed_trades

def _calculate_statistics(trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    """基于干净数据计算统计信息"""
    if not trades:
        return {}
    total_trades = len(trades)
    profits = [t['net_profit_usd'] for t in trades]
    profitable_trades = [t for t in trades if t['net_profit_usd'] > 0]
    losing_trades = [t for t in trades if t['net_profit_usd'] < 0]
    long_trades = [t for t in trades if t['position_type'] == '开多']
    short_trades = [t for t in trades if t['position_type'] == '开空']
    return {
        'total': {'count': total_trades, 'profit': round(sum(profits), 2), 'win_rate': (len(profitable_trades) / total_trades * 100) if total_trades > 0 else 0},
        'profitable': {'count': len(profitable_trades), 'avg_profit': round(sum(p['net_profit_usd'] for p in profitable_trades) / len(profitable_trades), 2) if profitable_trades else 0},
        'losing': {'count': len(losing_trades), 'avg_loss': round(sum(l['net_profit_usd'] for l in losing_trades) / len(losing_trades), 2) if losing_trades else 0},
        'long': {'count': len(long_trades), 'profit': round(sum(t['net_profit_usd'] for t in long_trades), 2), 'win_rate': (len([t for t in long_trades if t['net_profit_usd'] > 0]) / len(long_trades) * 100) if long_trades else 0},
        'short': {'count': len(short_trades), 'profit': round(sum(t['net_profit_usd'] for t in short_trades), 2), 'win_rate': (len([t for t in short_trades if t['net_profit_usd'] > 0]) / len(short_trades) * 100) if short_trades else 0}
    }

def _format_to_markdown(clean_trades: List[Dict[str, Any]], statistics: Dict[str, Any]) -> str:
    """将所有信息格式化为 Markdown 报告"""
    if not clean_trades or not statistics:
        return "### 交易历史分析\n\n没有找到符合条件的交易记录。\n"
    md = "### 交易历史分析\n\n"
    md += "#### 总体表现\n"
    md += f"- **总仓位数**: {statistics['total']['count']}\n"
    md += f"- **总净盈亏**: ${statistics['total']['profit']:+.2f}\n"
    md += f"- **胜率**: {statistics['total']['win_rate']:.1f}%\n"
    md += f"- **盈利仓位**: {statistics['profitable']['count']}笔, 平均盈利: ${statistics['profitable']['avg_profit']:+.2f}\n"
    md += f"- **亏损仓位**: {statistics['losing']['count']}笔, 平均亏损: ${statistics['losing']['avg_loss']:+.2f}\n\n"
    md += "#### 分类表现\n"
    md += f"- **开多**: {statistics['long']['count']}笔, 盈亏: ${statistics['long']['profit']:+.2f}, 胜率: {statistics['long']['win_rate']:.1f}%\n"
    md += f"- **开空**: {statistics['short']['count']}笔, 盈亏: ${statistics['short']['profit']:+.2f}, 胜率: {statistics['short']['win_rate']:.1f}%\n\n"
    md += "#### 最近仓位记录\n"
    md += "| 币种 | 类型 | 开仓均价 | 平仓均价 | 净盈亏 (USD) | 盈亏率 | 平仓时间 |\n"
    md += "|:---|:---|---:|---:|---:|---:|:---|"
    for trade in clean_trades[:15]:
        emoji = "📈" if trade['net_profit_usd'] > 0 else "📉"
        md += f"| {emoji} **{trade['symbol']}** | {trade['position_type']} | " \
               f"${trade['entry_price']:.4f} | ${trade['exit_price']:.4f} | " \
               f"**${trade['net_profit_usd']:+.2f}** | " \
               f"{trade['profit_pct']:+.2f}% | " \
               f"{trade['datetime']} |\n"
    return md

async def _get_and_process_data(exchange) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """获取并处理数据的核心逻辑"""
    loop = asyncio.get_event_loop()
    raw_positions = await loop.run_in_executor(None, get_positions_history, exchange, 1)
    clean_trades = _process_positions_data(raw_positions)
    statistics = _calculate_statistics(clean_trades)
    logger.info(f"✅ 已获取并处理 {len(clean_trades)} 条历史仓位数据")
    return clean_trades, statistics

# --- 公开接口 ---

async def generate_user_report(exchange) -> str:
    """生成给用户看的完整 Markdown 报告。"""
    try:
        clean_trades, statistics = await _get_and_process_data(exchange)
        return _format_to_markdown(clean_trades, statistics)
    except Exception as e:
        logger.error(f"❌ 生成用户报告失败: {e}", exc_info=True)
        return "生成报告时发生错误。"

async def generate_llm_data(exchange) -> Dict[str, Any]:
    """生成给 LLM 使用的、包含统计摘要和仓位列表的 JSON 结构。"""
    try:
        clean_trades, statistics = await _get_and_process_data(exchange)
        return {
            "statistics": statistics,
            "positions": clean_trades
        }
    except Exception as e:
        logger.error(f"❌ 生成LLM数据失败: {e}", exc_info=True)
        return {}