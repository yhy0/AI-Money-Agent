import pandas as pd
from typing import Dict, Any, List
from common.log_handler import logger


def extract_market_indicators(structured_market_data: Dict[str, Any], coin: str) -> Dict[str, Any]:
    """从结构化的市场数据中提取单个币种的技术指标
    
    Args:
        structured_market_data: 包含所有币种结构化数据的字典
        coin: 币种名称（如 "BTC", "DOGE"）
    
    Returns:
        包含技术指标的字典，如果提取失败则返回 None
    """
    try:
        coin_data = structured_market_data.get(coin)
        if not coin_data or not coin_data.get('success'):
            logger.warning(f"在 structured_market_data 中未找到 {coin} 的有效数据")
            return None

        df_3m = coin_data.get('df_3m')
        df_4h = coin_data.get('df_4h')

        if df_3m is None or df_4h is None or df_3m.empty or df_4h.empty:
            logger.warning(f"{coin} 的 DataFrame 为空或不存在")
            return None

        indicators = {
            'current_price': coin_data.get('current_price'),
            'ema20_3m': safe_get_latest(df_3m, 'EMA_20'),
            'macd_3m': safe_get_latest(df_3m, 'MACD_12_26_9'),
            'rsi_7_3m': safe_get_latest(df_3m, 'RSI_7'),
            'ema20_4h': safe_get_latest(df_4h, 'EMA_20_4h'),
            'ema50_4h': safe_get_latest(df_4h, 'EMA_50_4h'),
            'macd_4h': safe_get_latest(df_4h, 'MACD_4h'),
            'rsi_14_4h': safe_get_latest(df_4h, 'RSI_14_4h'),
        }

        # 过滤掉值为 None 的指标
        valid_indicators = {k: v for k, v in indicators.items() if v is not None}
        return valid_indicators

    except Exception as e:
        logger.error(f"从 structured_market_data 提取 {coin} 指标失败: {e}")
        return None


def validate_trend_consistency(decision: dict, structured_market_data: Dict[str, Any], trade_history: list) -> dict:
    """验证决策是否符合趋势一致性规则
    
    Args:
        decision: LLM 的交易决策
        structured_market_data: 包含所有币种结构化数据的字典
        trade_history: 交易历史记录
    
    Returns:
        验证结果字典，包含 'valid' (bool) 和 'warnings' (list) 字段
    """
    result = {
        'valid': True,
        'warnings': [],
        'trend_info': {}
    }
    
    # 只验证开仓信号
    if decision['signal'] not in ['buy_to_enter', 'sell_to_enter']:
        return result
    
    coin = decision.get('coin', '')
    if not coin:
        return result
    
    # 提取市场指标
    indicators = extract_market_indicators(structured_market_data, coin)
    
    if not indicators:
        result['warnings'].append(f"无法提取 {coin} 的市场指标，跳过趋势验证")
        return result
    
    # 检查必要的指标是否存在
    required_keys = ['ema20_4h', 'ema50_4h', 'macd_4h']
    missing_keys = [k for k in required_keys if k not in indicators]
    
    if missing_keys:
        result['warnings'].append(f"缺少关键指标: {', '.join(missing_keys)}，跳过趋势验证")
        return result
    
    # === 1. 趋势一致性检查 ===
    ema20_4h = indicators['ema20_4h']
    ema50_4h = indicators['ema50_4h']
    macd_4h = indicators['macd_4h']
    
    # 判断 4h 主趋势
    trend_4h = "up" if (ema20_4h > ema50_4h and macd_4h > 0) else \
               "down" if (ema20_4h < ema50_4h and macd_4h < 0) else \
               "neutral"
    
    result['trend_info'] = {
        '4h_trend': trend_4h,
        'ema20_4h': ema20_4h,
        'ema50_4h': ema50_4h,
        'macd_4h': macd_4h,
        'signal': decision['signal'],
        'confidence': decision.get('confidence', 0)
    }
    
    # 规则 1: 4h 下行趋势禁止做多（除非高信念度）
    if trend_4h == "down" and decision['signal'] == 'buy_to_enter':
        confidence = decision.get('confidence', 0)
        if confidence < 0.7:
            result['valid'] = False
            result['warnings'].append(
                f"⚠️ 规则违反：4h下行趋势中做多但信念度不足 "
                f"(confidence={confidence:.2f} < 0.7)"
            )
        else:
            result['warnings'].append(
                f"⚠️ 注意：4h下行趋势中做多，但信念度足够 (confidence={confidence:.2f} ≥ 0.7)"
            )
    
    # 规则 2: 4h 上行趋势禁止做空（除非高信念度）
    if trend_4h == "up" and decision['signal'] == 'sell_to_enter':
        confidence = decision.get('confidence', 0)
        if confidence < 0.7:
            result['valid'] = False
            result['warnings'].append(
                f"⚠️ 规则违反：4h上行趋势中做空但信念度不足 "
                f"(confidence={confidence:.2f} < 0.7)"
            )
        else:
            result['warnings'].append(
                f"⚠️ 注意：4h上行趋势中做空，但信念度足够 (confidence={confidence:.2f} ≥ 0.7)"
            )
    
    # === 2. RSI 限制规则检查 ===
    rsi_7_3m = indicators.get('rsi_7_3m')
    if rsi_7_3m is not None:
        # 下降趋势中 RSI < 30 不能做多
        if trend_4h == "down" and rsi_7_3m < 30 and decision['signal'] == 'buy_to_enter':
            result['warnings'].append(
                f"⚠️ RSI警告：下降趋势中RSI超卖 (RSI={rsi_7_3m:.1f} < 30)，"
                f"应等待MACD翻正或价格重回EMA20上方"
            )
    
    # === 3. 防过度交易规则检查 ===
    if len(trade_history) >= 3:
        # 检查最近3次交易是否均亏损
        recent_trades = trade_history[-3:]
        all_losses = all(
            t.get('result', {}).get('pnl', 0) < 0 
            for t in recent_trades 
            if 'result' in t and 'pnl' in t.get('result', {})
        )
        
        if all_losses:
            result['valid'] = False
            result['warnings'].append(
                "⚠️ 规则违反：过去3次交易均亏损，应进入观察状态（仅hold）"
            )
    
    return result


def safe_get_latest(df: pd.DataFrame, col: str):
    """安全地获取 DataFrame 的最后一行的指定列值"""
    if col in df.columns and not df[col].empty:
        return df[col].iloc[-1]
    return None
