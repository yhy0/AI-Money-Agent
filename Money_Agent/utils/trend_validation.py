import re
from common.log_handler import logger


def extract_market_indicators(market_data_str: str, coin: str) -> dict:
    """从格式化的市场数据字符串中提取技术指标
    
    Args:
        market_data_str: 格式化的市场数据字符串
        coin: 币种名称（如 "BTC", "DOGE"）
    
    Returns:
        包含技术指标的字典，如果提取失败则返回 None
    """
    try:
        # 查找该币种的数据块
        pattern = f"### 所有 {coin} 数据.*?(?=### 所有|$)"
        match = re.search(pattern, market_data_str, re.DOTALL)
        
        if not match:
            logger.warning(f"未找到 {coin} 的市场数据")
            return None
        
        coin_data = match.group(0)
        
        # 提取关键指标
        indicators = {}
        
        # 提取当前价格
        price_match = re.search(r'当前价格:\s*\$?([\d.]+)', coin_data)
        if price_match:
            indicators['current_price'] = float(price_match.group(1))
        
        # 提取 3min EMA20
        ema20_3m_match = re.search(r'当前 EMA\(20\):\s*\$?([\d.]+)', coin_data)
        if ema20_3m_match:
            indicators['ema20_3m'] = float(ema20_3m_match.group(1))
        
        # 提取 3min MACD
        macd_3m_match = re.search(r'当前 MACD:\s*(-?[\d.]+)', coin_data)
        if macd_3m_match:
            indicators['macd_3m'] = float(macd_3m_match.group(1))
        
        # 提取 3min RSI
        rsi_3m_match = re.search(r'当前 RSI \(7周期\):\s*([\d.]+)', coin_data)
        if rsi_3m_match:
            indicators['rsi_7_3m'] = float(rsi_3m_match.group(1))
        
        # 提取 4h EMA20 和 EMA50
        ema_4h_match = re.search(r'20周期 EMA:\s*\$?([\d.]+)\s*vs\.\s*50周期 EMA:\s*\$?([\d.]+)', coin_data)
        if ema_4h_match:
            indicators['ema20_4h'] = float(ema_4h_match.group(1))
            indicators['ema50_4h'] = float(ema_4h_match.group(2))
        
        # 提取 4h MACD（从序列中取最后一个值）
        macd_4h_match = re.search(r'MACD 指标 \(4h\):\s*\[(.*?)\]', coin_data)
        if macd_4h_match:
            macd_values = macd_4h_match.group(1).split(',')
            # 取最后一个非 N/A 的值
            for val in reversed(macd_values):
                val = val.strip()
                if val != 'N/A':
                    try:
                        indicators['macd_4h'] = float(val)
                        break
                    except ValueError:
                        continue
        
        # 提取 4h RSI（从序列中取最后一个值）
        rsi_4h_match = re.search(r'RSI 指标 \(14周期, 4h\):\s*\[(.*?)\]', coin_data)
        if rsi_4h_match:
            rsi_values = rsi_4h_match.group(1).split(',')
            # 取最后一个非 N/A 的值
            for val in reversed(rsi_values):
                val = val.strip()
                if val != 'N/A':
                    try:
                        indicators['rsi_14_4h'] = float(val)
                        break
                    except ValueError:
                        continue
        
        return indicators if indicators else None
        
    except Exception as e:
        logger.error(f"提取 {coin} 市场指标失败: {e}")
        return None


def validate_trend_consistency(decision: dict, market_data_str: str, trade_history: list) -> dict:
    """验证决策是否符合趋势一致性规则
    
    Args:
        decision: LLM 的交易决策
        market_data_str: 格式化的市场数据字符串
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
    indicators = extract_market_indicators(market_data_str, coin)
    
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
