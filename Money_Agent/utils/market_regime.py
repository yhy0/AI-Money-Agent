"""
市场状态评估模块
根据市场数据计算当前市场环境（高波动趋势、低波动盘整等）
"""
from typing import Dict, Any
import numpy as np
from common.log_handler import logger


def calculate_market_regime(structured_market_data: Dict[str, Any]) -> str:
    """
    根据结构化市场数据计算市场状态
    
    Args:
        structured_market_data: 包含各币种市场数据的字典
        
    Returns:
        市场状态描述字符串，例如 "高波动趋势" 或 "低波动盘整"
    """
    try:
        if not structured_market_data:
            return "数据不足"
        
        # 收集所有成功获取数据的币种的波动率和趋势信息
        volatilities = []
        trend_strengths = []
        
        for coin, data in structured_market_data.items():
            if not data.get('success', False):
                continue
                
            df_4h = data.get('df_4h')
            if df_4h is None or df_4h.empty:
                continue
            
            try:
                # 计算波动率（使用ATR）
                atr_14 = df_4h['ATR_14_4h'].iloc[-1]
                current_price = data.get('current_price', df_4h['close'].iloc[-1])
                
                # 归一化波动率（ATR / 价格）
                normalized_volatility = (atr_14 / current_price) * 100 if current_price > 0 else 0
                volatilities.append(normalized_volatility)
                
                # 计算趋势强度（使用EMA和MACD）
                ema_20 = df_4h['EMA_20_4h'].iloc[-1]
                ema_50 = df_4h['EMA_50_4h'].iloc[-1]
                macd = df_4h['MACD_4h'].iloc[-1]
                
                # EMA差距作为趋势强度指标
                ema_diff = abs(ema_20 - ema_50) / ema_50 * 100 if ema_50 > 0 else 0
                
                # MACD绝对值作为趋势强度指标
                macd_strength = abs(macd) / current_price * 100 if current_price > 0 else 0
                
                # 综合趋势强度
                trend_strength = (ema_diff + macd_strength) / 2
                trend_strengths.append(trend_strength)
                
            except Exception as e:
                logger.debug(f"计算 {coin} 市场指标时出错: {e}")
                continue
        
        # 如果没有足够的数据
        if not volatilities or not trend_strengths:
            return "数据不足"
        
        # 计算平均波动率和趋势强度
        avg_volatility = np.mean(volatilities)
        avg_trend_strength = np.mean(trend_strengths)
        
        # 定义阈值
        HIGH_VOLATILITY_THRESHOLD = 2.0  # 2%
        LOW_VOLATILITY_THRESHOLD = 0.8   # 0.8%
        STRONG_TREND_THRESHOLD = 1.5     # 1.5%
        WEAK_TREND_THRESHOLD = 0.5       # 0.5%
        
        # 判断市场状态
        if avg_volatility > HIGH_VOLATILITY_THRESHOLD:
            if avg_trend_strength > STRONG_TREND_THRESHOLD:
                regime = "高波动趋势"
            else:
                regime = "高波动盘整"
        elif avg_volatility < LOW_VOLATILITY_THRESHOLD:
            if avg_trend_strength > STRONG_TREND_THRESHOLD:
                regime = "低波动趋势"
            else:
                regime = "低波动盘整"
        else:
            # 中等波动
            if avg_trend_strength > STRONG_TREND_THRESHOLD:
                regime = "中等波动趋势"
            elif avg_trend_strength < WEAK_TREND_THRESHOLD:
                regime = "中等波动盘整"
            else:
                regime = "中等波动震荡"
        
        logger.info(f"📊 市场状态评估: {regime} (波动率: {avg_volatility:.2f}%, 趋势强度: {avg_trend_strength:.2f}%)")
        
        return regime
        
    except Exception as e:
        logger.error(f"计算市场状态失败: {e}")
        return "计算失败"
