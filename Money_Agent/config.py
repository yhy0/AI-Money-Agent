"""
配置管理模块
统一管理所有配置项，包括币种列表
"""
import os
from typing import List, Literal
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 支持的所有币种（用于验证）
ALL_SUPPORTED_COINS = ["BTC", "ETH", "SOL", "BGB", "DOGE", "SUI", "LTC"]

# ==================== 资金限制配置 ====================
# 当账户权益低于此阈值时，只交易 DOGE
MIN_EQUITY_FOR_MULTI_ASSET = float(os.getenv('MIN_EQUITY_FOR_MULTI_ASSET', '30'))

# 低资金模式下允许交易的币种（默认只有 DOGE）
LOW_EQUITY_COINS = os.getenv('LOW_EQUITY_COINS', 'DOGE').split(',')
LOW_EQUITY_COINS = [coin.strip().upper() for coin in LOW_EQUITY_COINS if coin.strip()]

def get_trading_coins() -> List[str]:
    """
    从环境变量获取交易币种列表
    
    Returns:
        币种列表，例如 ["BTC", "ETH", "SOL"]
    """
    coins_str = os.getenv('TRADING_COINS', 'BTC,ETH,SOL')
    coins = [coin.strip().upper() for coin in coins_str.split(',') if coin.strip()]
    
    # 验证币种是否支持
    invalid_coins = [coin for coin in coins if coin not in ALL_SUPPORTED_COINS]
    if invalid_coins:
        raise ValueError(
            f"不支持的币种: {invalid_coins}. "
            f"支持的币种: {ALL_SUPPORTED_COINS}"
        )
    
    return coins

def get_coin_literal_type():
    """
    获取币种的 Literal 类型（用于 Pydantic 验证）
    
    Returns:
        所有支持币种的 Literal 类型
    """
    # 返回所有支持的币种，而不仅仅是当前交易的币种
    # 这样可以保证 Pydantic 验证的灵活性
    return Literal["BTC", "ETH", "SOL", "BGB", "DOGE", "SUI", "LTC"]

# 导出常量
TRADING_COINS = get_trading_coins()

if __name__ == "__main__":
    # 测试配置
    print(f"当前交易币种: {TRADING_COINS}")
    print(f"支持的所有币种: {ALL_SUPPORTED_COINS}")
