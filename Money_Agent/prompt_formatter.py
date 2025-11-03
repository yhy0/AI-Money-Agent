"""
Prompt 格式化工具
根据 nof1-prompt.md 的最佳实践，将原始市场数据格式化为高结构化、低歧义的提示词
"""

import pandas as pd
import json
from typing import Dict, Any, List


def format_coin_data(
    coin: str,
    ticker: Dict[str, Any],
    df_3m: pd.DataFrame,
    df_4h: pd.DataFrame,
    funding_rate: Dict[str, Any],
    open_interest: Dict[str, Any]
) -> str:
    """
    为单个代币生成完整的、结构化的市场数据描述
    
    Args:
        coin: 代币符号 (如 "BTC")
        ticker: 当前行情数据
        df_3m: 3分钟K线数据（已计算指标）
        df_4h: 4小时K线数据（已计算指标）
        funding_rate: 资金费率数据
        open_interest: 未平仓合约数据
    
    Returns:
        格式化的市场数据字符串
    """
    import math

    ticker = ticker or {}
    funding_rate = funding_rate or {}
    open_interest = open_interest or {}

    def sanitize_number(value):
        """将任意值安全转换为浮点数"""
        if value is None:
            return None
        if isinstance(value, str):
            stripped_value = value.replace(",", "").strip()
            if stripped_value == "":
                return None
            try:
                value = float(stripped_value)
            except ValueError:
                return None
        if isinstance(value, (int, float)):
            if isinstance(value, float) and math.isnan(value):
                return None
            return float(value)
        return None
    
    def format_price(price):
        """智能格式化价格：根据价格大小自动调整精度"""
        if price is None:
            return "N/A"
        if price >= 1000:
            return f"${price:.6f}"  # 高价币：2位小数 (如 BTC $67000.0000)
        elif price >= 1:
            return f"${price:.6f}"  # 中价币：4位小数 (如 ETH $3456.789000)
        else:
            return f"${price:.8f}"  # 低价币：6位小数 (如 DOGE $0.18630000)

    output = f"### 所有 {coin} 数据\n\n"
    
    # === 当前快照 ===
    output += "**当前快照:**\n"
    last_price = sanitize_number(ticker.get('last'))
    if last_price is not None:
        output += f"- 当前价格: {format_price(last_price)}\n"
    else:
        output += "- 当前价格: N/A\n"
    
    # 安全获取指标值（处理 NaN 和缺失列）
    def safe_get_value(df, col_name, default=None):
        """安全获取 DataFrame 中的值"""
        if col_name not in df.columns:
            return default
        val = sanitize_number(df[col_name].iloc[-1])
        if val is None:
            return default
        return val
    
    ema_20 = safe_get_value(df_3m, 'EMA_20')
    macd = safe_get_value(df_3m, 'MACD_12_26_9')
    rsi_7 = safe_get_value(df_3m, 'RSI_7')
    
    output += f"- 当前 EMA(20): ${ema_20:.6f}\n" if ema_20 is not None else "- 当前 EMA(20): N/A\n"
    output += f"- 当前 MACD: {macd:.6f}\n" if macd is not None else "- 当前 MACD: N/A\n"
    output += f"- 当前 RSI (7周期): {rsi_7:.6f}\n\n" if rsi_7 is not None else "- 当前 RSI (7周期): N/A\n\n"
    
    # === 永续合约指标 ===
    output += "**永续合约指标:**\n"
    oi_value = sanitize_number(open_interest.get('openInterestValue'))
    if oi_value is not None:
        output += f"- 未平仓合约 (最新): ${oi_value:,.0f}\n"
    else:
        output += "- 未平仓合约 (最新): N/A\n"

    funding_rate_value = sanitize_number(funding_rate.get('fundingRate'))
    if funding_rate_value is not None:
        output += f"- 资金费率: {funding_rate_value:.6f}"

        # 资金费率解读
        if funding_rate_value > 0.0001:
            output += " (多头支付空头，市场看涨)\n\n"
        elif funding_rate_value < -0.0001:
            output += " (空头支付多头，市场看跌)\n\n"
        else:
            output += " (中性)\n\n"
    else:
        output += "- 资金费率: N/A\n\n"
    
    # === 日内序列 (3分钟间隔) ===
    output += "**日内序列 (3分钟间隔, 从旧到新):**\n\n"
    
    # 取最近10个数据点
    recent_count = min(10, len(df_3m))
    
    # 安全获取序列数据
    def safe_get_series(df, col_name, count):
        """安全获取序列数据"""
        if col_name not in df.columns:
            return pd.Series([None] * count)
        series = df[col_name].tail(count)
        return series.apply(sanitize_number)
    
    output += f"中间价: {_format_list(safe_get_series(df_3m, 'close', recent_count))}\n\n"
    output += f"EMA 指标 (20周期): {_format_list(safe_get_series(df_3m, 'EMA_20', recent_count))}\n\n"
    output += f"MACD 指标: {_format_list(safe_get_series(df_3m, 'MACD_12_26_9', recent_count))}\n\n"
    output += f"RSI 指标 (7周期): {_format_list(safe_get_series(df_3m, 'RSI_7', recent_count))}\n\n"
    output += f"RSI 指标 (14周期): {_format_list(safe_get_series(df_3m, 'RSI_14', recent_count))}\n\n"
    
    # === 长周期背景 (4小时时间框架) ===
    output += "**长周期背景 (4小时时间框架):**\n\n"
    
    ema20_4h = safe_get_value(df_4h, 'EMA_20_4h')
    ema50_4h = safe_get_value(df_4h, 'EMA_50_4h')
    
    # 安全处理 EMA 值
    if ema20_4h is not None and ema50_4h is not None:
        output += f"20周期 EMA: ${ema20_4h:.6f} vs. 50周期 EMA: ${ema50_4h:.6f}"
        
        # EMA趋势解读
        if ema20_4h > ema50_4h:
            output += " (金叉，上升趋势)\n\n"
        elif ema20_4h < ema50_4h:
            output += " (死叉，下降趋势)\n\n"
        else:
            output += " (中性)\n\n"
    else:
        output += "20周期 EMA: N/A vs. 50周期 EMA: N/A (数据不足)\n\n"
    
    atr3_4h = safe_get_value(df_4h, 'ATR_3_4h')
    atr14_4h = safe_get_value(df_4h, 'ATR_14_4h')
    
    # 安全处理 ATR 值
    if atr3_4h is not None and atr14_4h is not None:
        output += f"3周期 ATR: ${atr3_4h:.6f} vs. 14周期 ATR: ${atr14_4h:.6f}"
        
        # ATR波动性解读
        if atr3_4h > atr14_4h * 1.2:
            output += " (波动性上升)\n\n"
        elif atr3_4h < atr14_4h * 0.8:
            output += " (波动性下降)\n\n"
        else:
            output += " (波动性正常)\n\n"
    else:
        output += "3周期 ATR: N/A vs. 14周期 ATR: N/A (数据不足)\n\n"
    
    vol_current = safe_get_value(df_4h, 'volume', 0)
    vol_avg = df_4h['volume'].mean() if 'volume' in df_4h.columns else 0
    
    if vol_current is not None and vol_avg and vol_avg > 0:
        output += f"当前成交量: {vol_current:,.0f} vs. 平均成交量: {vol_avg:,.0f}"
        
        # 成交量解读
        if vol_current > vol_avg * 1.5:
            output += " (成交量放大)\n\n"
        elif vol_current < vol_avg * 0.5:
            output += " (成交量萎缩)\n\n"
        else:
            output += " (成交量正常)\n\n"
    else:
        output += "当前成交量: N/A\n\n"
    
    output += f"MACD 指标 (4h): {_format_list(safe_get_series(df_4h, 'MACD_4h', recent_count))}\n\n"
    output += f"RSI 指标 (14周期, 4h): {_format_list(safe_get_series(df_4h, 'RSI_14_4h', recent_count))}\n\n"
    
    # === 市场状态分析 (新增) ===
    output += "**市场状态分析:**\n\n"
    
    # 1. 趋势状态分析
    if last_price is not None and ema20_4h is not None and ema50_4h is not None:
        if last_price > ema20_4h > ema50_4h:
            trend_strength = ((ema20_4h - ema50_4h) / ema50_4h) * 100
            output += f"- 趋势：强势上升趋势（价格 {format_price(last_price)} > 均线20 {format_price(ema20_4h)} > 均线50 {format_price(ema50_4h)}，均线差距 {trend_strength:.6f}%）\n"
        elif last_price < ema20_4h < ema50_4h:
            trend_strength = ((ema50_4h - ema20_4h) / ema50_4h) * 100
            output += f"- 趋势：强势下降趋势（价格 {format_price(last_price)} < 均线20 {format_price(ema20_4h)} < 均线50 {format_price(ema50_4h)}，均线差距 {trend_strength:.6f}%）\n"
        elif last_price > ema20_4h and ema20_4h < ema50_4h:
            output += f"- 趋势：反弹中（价格 {format_price(last_price)} > 均线20 {format_price(ema20_4h)}，但均线20 < 均线50 {format_price(ema50_4h)}，趋势可能转折）\n"
        elif last_price < ema20_4h and ema20_4h > ema50_4h:
            output += f"- 趋势：回调中（价格 {format_price(last_price)} < 均线20 {format_price(ema20_4h)}，但均线20 > 均线50 {format_price(ema50_4h)}，趋势可能转折）\n"
        else:
            output += f"- 趋势：震荡或转折中（价格 {format_price(last_price)}，均线20 {format_price(ema20_4h)}，均线50 {format_price(ema50_4h)}）\n"
    else:
        output += "- 趋势：数据不足，无法判断\n"
    
    # 2. 波动性状态分析
    if atr14_4h is not None and 'ATR_14_4h' in df_4h.columns:
        atr_series = df_4h['ATR_14_4h'].tail(20)
        atr_avg = atr_series.mean()
        
        if atr_avg and atr_avg > 0:
            volatility_ratio = atr14_4h / atr_avg
            
            if volatility_ratio > 1.5:
                output += f"- 波动性：高波动环境（当前真实波幅 ${atr14_4h:.6f} = {volatility_ratio:.6f}倍平均值 ${atr_avg:.6f}）- 建议降低仓位或使用更宽的止损\n"
            elif volatility_ratio < 0.7:
                output += f"- 波动性：低波动环境（当前真实波幅 ${atr14_4h:.6f} = {volatility_ratio:.6f}倍平均值 ${atr_avg:.6f}）- 可能即将突破，注意仓位管理\n"
            else:
                output += f"- 波动性：正常波动（当前真实波幅 ${atr14_4h:.6f} = {volatility_ratio:.6f}倍平均值 ${atr_avg:.6f}）\n"
        else:
            output += f"- 波动性：当前真实波幅 ${atr14_4h:.6f}（历史数据不足）\n"
    else:
        output += "- 波动性：数据不足，无法判断\n"
    
    # 3. RSI 极值警告（可选，仅在极端情况下显示）
    rsi_14 = safe_get_value(df_3m, 'RSI_14')
    if rsi_14 is not None:
        if rsi_14 > 80:
            output += f"- ⚠️ 相对强弱指数警告：严重超买（RSI = {rsi_14:.6f} > 80）- 警惕回调风险\n"
        elif rsi_14 > 70:
            output += f"- ⚠️ 相对强弱指数警告：超买区域（RSI = {rsi_14:.6f} > 70）- 注意获利了结\n"
        elif rsi_14 < 20:
            output += f"- ⚠️ 相对强弱指数警告：严重超卖（RSI = {rsi_14:.6f} < 20）- 可能反弹\n"
        elif rsi_14 < 30:
            output += f"- ⚠️ 相对强弱指数警告：超卖区域（RSI = {rsi_14:.6f} < 30）- 关注反弹机会\n"
    
    output += "\n"
    output += "---\n\n"
    
    return output


def format_positions(positions: List[Dict[str, Any]], trade_history: List[Dict[str, Any]] = None) -> str:
    """
    格式化持仓信息为清晰的结构化文本（符合 nof1-prompt.md 规范）
    
    Args:
        positions: 持仓列表
        trade_history: 交易历史（用于恢复 exit_plan）
    
    Returns:
        格式化的持仓字符串
    """
    if not positions or len(positions) == 0:
        return "```python\n[]\n```\n\n(当前无持仓)"
    
    # 构建 exit_plan 映射表（从交易历史中恢复）
    exit_plans = {}
    if trade_history:
        for trade in reversed(trade_history):  # 从最新的交易开始查找
            decision = trade.get('decision', {})
            if decision.get('signal') in ['buy_to_enter', 'sell_to_enter']:
                coin = decision.get('coin')
                if coin and coin not in exit_plans:
                    exit_plans[coin] = {
                        'profit_target': decision.get('profit_target', 0),
                        'stop_loss': decision.get('stop_loss', 0),
                        'invalidation_condition': decision.get('invalidation_condition', 'N/A'),
                        'confidence': decision.get('confidence', 0),
                        'risk_usd': decision.get('risk_usd', 0)
                    }
    
    output = "```python\n[\n"
    
    for i, pos in enumerate(positions):
        symbol = pos.get('symbol', 'N/A')
        # 从 symbol 中提取币种（如 "BTC/USDT:USDT" -> "BTC"）
        coin = symbol.split('/')[0] if '/' in symbol else symbol
        
        output += "  {\n"
        # 获取价格用于智能格式化
        entry_price = pos.get('entry_price', 0)
        current_price = pos.get('mark_price', 0)
        liquidation_price = pos.get('liquidation_price', 0)
        
        output += f"    'symbol': '{symbol}',\n"
        output += f"    'side': '{pos.get('side', 'N/A')}',\n"
        output += f"    'quantity': {pos.get('size', 0)},\n"
        output += f"    'entry_price': {entry_price:.6f},\n"
        output += f"    'current_price': {current_price:.6f},\n"
        output += f"    'liquidation_price': {liquidation_price:.6f},\n"
        output += f"    'unrealized_pnl': {pos.get('unrealized_pnl', 0):.6f},\n"
        output += f"    'leverage': {pos.get('leverage', 1)},\n"
        
        # 添加 exit_plan（从交易历史恢复或使用默认值）
        exit_plan = exit_plans.get(coin, {
            'profit_target': 0,
            'stop_loss': 0,
            'invalidation_condition': '未设置',
            'confidence': 0,
            'risk_usd': 0
        })
        
        output += "    'exit_plan': {\n"
        output += f"      'profit_target': {exit_plan['profit_target']:.6f},\n"
        output += f"      'stop_loss': {exit_plan['stop_loss']:.6f},\n"
        output += f"      'invalidation_condition': '{exit_plan['invalidation_condition']}'\n"
        output += "    },\n"
        output += f"    'confidence': {exit_plan['confidence']:.6f},\n"
        output += f"    'risk_usd': {exit_plan['risk_usd']:.6f},\n"
        output += f"    'notional_usd': {pos.get('notional', 0):.6f}\n"
        
        output += "  }"
        if i < len(positions) - 1:
            output += ","
        output += "\n"
    
    output += "]\n```"
    
    return output


def _format_list(series: pd.Series, precision: int = 2) -> str:
    """
    将 pandas Series 格式化为易读的列表字符串
    
    Args:
        series: pandas Series
        precision: 小数精度
    
    Returns:
        格式化的列表字符串
    """
    import math
    values = series.tolist()
    formatted = []
    for v in values:
        if v is None or (isinstance(v, float) and math.isnan(v)):
            formatted.append("N/A")
        elif isinstance(v, (int, float)):
            formatted.append(f"{v:.{precision}f}")
        else:
            formatted.append(str(v))
    return "[" + ", ".join(formatted) + "]"


def validate_dataframe_indicators(df: pd.DataFrame, required_columns: List[str]) -> bool:
    """
    验证 DataFrame 是否包含所需的指标列
    
    Args:
        df: 数据框
        required_columns: 必需的列名列表
    
    Returns:
        是否包含所有必需列
    """
    missing = [col for col in required_columns if col not in df.columns]
    if missing:
        raise ValueError(f"DataFrame 缺少必需的指标列: {missing}")
    return True
