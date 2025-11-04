#!/usr/bin/env python3
"""
测试脚本：获取账户资产和加密货币价格信息
"""

import os
from dotenv import load_dotenv
from Money_Agent.tools.exchange_data_tool import (
    get_exchange,
    get_account_balance,
    get_positions,
    validate_api_credentials
)
from Money_Agent.config import ALL_SUPPORTED_COINS
from common.log_handler import logger

# 加载环境变量
load_dotenv()

# 支持的加密货币列表（从配置模块导入）
SUPPORTED_COINS = ALL_SUPPORTED_COINS

def print_separator(title="", char="=", width=70):
    """打印分隔线"""
    if title:
        print(f"\n{char * width}")
        print(f"{title:^{width}}")
        print(f"{char * width}")
    else:
        print(f"{char * width}")

def get_coin_price_info(exchange, coin: str):
    """获取单个币种的价格信息"""
    try:
        symbol = f"{coin}/USDT:USDT"
        
        # 获取ticker数据
        ticker = exchange.fetch_ticker(symbol)
        
        # 获取资金费率
        try:
            funding_rate = exchange.fetch_funding_rate(symbol)
            funding_rate_value = funding_rate.get('fundingRate')
            # 确保返回有效值或 'N/A'
            if funding_rate_value is None:
                funding_rate_value = 'N/A'
        except:
            funding_rate_value = 'N/A'
        
        # 获取持仓量
        try:
            open_interest = exchange.fetch_open_interest(symbol)
            oi_value = open_interest.get('openInterestValue')
            # 确保返回有效值或 'N/A'
            if oi_value is None:
                oi_value = 'N/A'
        except:
            oi_value = 'N/A'
        
        return {
            'symbol': symbol,
            'last_price': ticker.get('last', 0),
            'bid': ticker.get('bid', 0),
            'ask': ticker.get('ask', 0),
            'high_24h': ticker.get('high', 0),
            'low_24h': ticker.get('low', 0),
            'volume_24h': ticker.get('quoteVolume', 0),
            'change_24h': ticker.get('percentage', 0),
            'funding_rate': funding_rate_value,
            'open_interest': oi_value
        }
    except Exception as e:
        logger.error(f"获取 {coin} 价格信息失败: {e}")
        return None

def test_account_info():
    """测试获取账户信息"""
    print_separator("🧪 账户信息测试脚本", "=")
    
    # 1. 初始化交易所
    print("\n1️⃣ 初始化交易所连接...")
    exchange = get_exchange()
    print("   ✅ 交易所初始化成功")
    
    # 2. 验证API凭据
    print("\n2️⃣ 验证API凭据...")
    is_valid = validate_api_credentials(exchange)
    
    if not is_valid:
        print("   ⚠️ API凭据验证失败，将使用模拟数据")
        print("   💡 提示：请在 .env 文件中配置正确的 API 密钥")
    else:
        print("   ✅ API凭据验证成功")
    
    # 3. 获取账户余额
    print_separator("💰 账户余额信息", "-")
    balance = get_account_balance(exchange)
    
    print(f"\n{'项目':<20} {'金额 (USDT)':<20}")
    print("-" * 40)
    print(f"{'总资产':<20} ${balance['total_balance']:>18,.2f}")
    print(f"{'可用余额':<20} ${balance['free_balance']:>18,.2f}")
    print(f"{'已用余额':<20} ${balance['used_balance']:>18,.2f}")
    
    # 4. 获取当前持仓
    print_separator("📍 当前持仓信息", "-")
    positions = get_positions(exchange)
    
    if positions:
        print(f"\n持仓数量: {len(positions)} 个\n")
        for i, pos in enumerate(positions, 1):
            print(f"持仓 #{i}:")
            print(f"  币种: {pos.get('symbol', 'N/A')}")
            print(f"  方向: {pos.get('side', 'N/A')}")
            print(f"  数量: {pos.get('contracts', 0)} 张")
            print(f"  杠杆: {pos.get('leverage', 1)}x")
            print(f"  开仓价: ${pos.get('entry_price', 0):.6f}")
            print(f"  当前价: ${pos.get('mark_price', 0):.6f}")
            print(f"  未实现盈亏: ${pos.get('unrealized_pnl', 0):+.2f}")
            print(f"  收益率: {pos.get('percentage', 0):+.2f}%")
            print()
    else:
        print("\n当前无持仓")
    
    # 5. 获取支持的加密货币价格
    print_separator("💹 支持的加密货币价格信息", "-")
    
    print(f"\n正在获取 {len(SUPPORTED_COINS)} 个币种的价格信息...\n")
    
    coin_prices = {}
    for coin in SUPPORTED_COINS:
        print(f"📊 获取 {coin} 价格信息...")
        price_info = get_coin_price_info(exchange, coin)
        if price_info:
            coin_prices[coin] = price_info
            print(f"   ✅ {coin}: ${price_info['last_price']:,.2f}")
        else:
            print(f"   ❌ {coin}: 获取失败")
    
    # 6. 详细价格信息表格
    print_separator("📈 详细价格信息", "-")
    
    if coin_prices:
        print(f"\n{'币种':<8} {'最新价':<12} {'24h涨跌':<12} {'24h最高':<12} {'24h最低':<12} {'24h成交量':<15}")
        print("-" * 85)
        
        for coin, info in coin_prices.items():
            change_str = f"{info['change_24h']:+.2f}%" if isinstance(info['change_24h'], (int, float)) else "N/A"
            volume_str = f"${info['volume_24h']:,.0f}" if isinstance(info['volume_24h'], (int, float)) else "N/A"
            
            print(f"{coin:<8} "
                  f"${info['last_price']:<11,.2f} "
                  f"{change_str:<12} "
                  f"${info['high_24h']:<11,.2f} "
                  f"${info['low_24h']:<11,.2f} "
                  f"{volume_str:<15}")
    
    # 7. 永续合约信息
    print_separator("🔄 永续合约信息", "-")
    
    if coin_prices:
        print(f"\n{'币种':<8} {'资金费率':<15} {'持仓量':<20}")
        print("-" * 50)
        
        for coin, info in coin_prices.items():
            # 处理资金费率
            funding_rate = info.get('funding_rate')
            if funding_rate and funding_rate != 'N/A':
                try:
                    funding_str = f"{float(funding_rate)*100:.6f}%"
                except (ValueError, TypeError):
                    funding_str = "N/A"
            else:
                funding_str = "N/A"
            
            # 处理持仓量
            open_interest = info.get('open_interest')
            if open_interest and open_interest != 'N/A':
                try:
                    oi_str = f"${float(open_interest):,.0f}"
                except (ValueError, TypeError):
                    oi_str = "N/A"
            else:
                oi_str = "N/A"
            
            print(f"{coin:<8} {funding_str:<15} {oi_str:<20}")
    
    # 8. 总结
    print_separator("📊 测试总结", "=")
    
    print(f"\n✅ 测试完成！")
    print(f"\n统计信息:")
    print(f"  • 账户总资产: ${balance['total_balance']:,.2f}")
    print(f"  • 可用余额: ${balance['free_balance']:,.2f}")
    print(f"  • 当前持仓: {len(positions)} 个")
    print(f"  • 成功获取价格: {len(coin_prices)}/{len(SUPPORTED_COINS)} 个币种")
    
    if is_valid:
        print(f"\n💡 提示: 这是您的真实账户数据")
    else:
        print(f"\n💡 提示: 部分数据为模拟数据（未配置API密钥）")
    
    print_separator("", "=")
    
    return {
        'balance': balance,
        'positions': positions,
        'coin_prices': coin_prices
    }

if __name__ == "__main__":
    try:
        result = test_account_info()
        
        # 可选：保存结果到文件
        import json
        from datetime import datetime
        
        output_file = f"account_info_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump({
                'timestamp': datetime.now().isoformat(),
                'balance': result['balance'],
                'positions': result['positions'],
                'coin_prices': {k: v for k, v in result['coin_prices'].items()}
            }, f, indent=2, ensure_ascii=False)
        
        print(f"\n💾 结果已保存到: {output_file}")
        
    except KeyboardInterrupt:
        print("\n\n⚠️ 用户中断测试")
    except Exception as e:
        logger.error(f"测试过程中出错: {e}")
        import traceback
        traceback.print_exc()
