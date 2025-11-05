
import ccxt
import pandas as pd
import vectorbt as vbt
import pandas_ta as ta
import os
import time
from typing import Dict, Any, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from common.log_handler import logger, log_tool_event, log_system_event
from Money_Agent.config import TRADING_COINS
from Money_Agent.utils.prompt_formatter import format_coin_data
    

# 全局缓存字典
_market_data_cache = {}

def clear_market_data_cache():
    """清理市场数据缓存"""
    global _market_data_cache
    _market_data_cache.clear()
    logger.info("🧹 已清理市场数据缓存")

def validate_api_credentials(exchange) -> bool:
    """验证API凭据有效性"""
    try:
        if not (hasattr(exchange, 'apiKey') and exchange.apiKey):
            logger.warning("⚠️ 未配置API密钥")
            return False
        
        # 测试API连接
        exchange.fetch_balance()
        logger.info("✅ API凭据验证成功")
        return True
    except ccxt.AuthenticationError as e:
        logger.error(f"❌ API凭据验证失败 (认证错误): {e}")
        return False
    except ccxt.NetworkError as e:
        logger.error(f"❌ API凭据验证失败 (网络错误): {e}")
        return False
    except Exception as e:
        logger.error(f"❌ API凭据验证失败: {e}")
        return False

def get_exchange():
    """初始化并返回 Bitget 交易所实例。"""
    
    # 从环境变量获取API密钥
    api_key = os.getenv('BITGET_API_KEY', '')
    secret = os.getenv('BITGET_SECRET', '')
    passphrase = os.getenv('BITGET_PASSPHRASE', '')
    
    # 判断是否使用沙盒环境
    use_sandbox = os.getenv('BITGET_SANDBOX', 'true').lower() == 'true'
    
    exchange = ccxt.bitget({
        'apiKey': api_key,
        'secret': secret,
        'password': passphrase,  # Bitget 需要 passphrase
        'sandbox': use_sandbox,  # 使用测试环境
        'rateLimit': 1000,  # 增加速率限制间隔
        'enableRateLimit': True,
        'timeout': 30000,  # 30秒超时
        'options': {
            'defaultType': 'swap',  # 使用永续合约
        },
    })
    
    log_system_event("初始化 Bitget 交易所", {
        "沙盒模式": use_sandbox,
        "API配置": "已配置" if api_key else "未配置"
    })
    return exchange

def _fetch_coin_data(exchange, coin: str) -> Dict[str, Any]:
    """获取单个币种的市场数据（用于并发调用）"""
    try:
        symbol = f"{coin}/USDT:USDT"
        
        # --- 获取数据（禁用缓存，实时获取） ---
        # 3分钟K线
        ohlcv_3m = exchange.fetch_ohlcv(symbol, timeframe='3m', limit=100)
        df_3m = pd.DataFrame(ohlcv_3m, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        # 4小时K线
        ohlcv_4h = exchange.fetch_ohlcv(symbol, timeframe='4h', limit=100)
        df_4h = pd.DataFrame(ohlcv_4h, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

        # 其他市场指标（实时获取）
        ticker = exchange.fetch_ticker(symbol)
        
        # 🔥 记录当前价格
        current_price = ticker['last']
        # 智能格式化价格：根据价格大小自动调整精度
        if current_price >= 1000:
            price_str = f"${current_price:.6f}"
        elif current_price >= 1:
            price_str = f"${current_price:.6f}"
        else:
            price_str = f"${current_price:.8f}"
        
        log_tool_event(f"获取 {coin} 行情", {
            "当前价格": price_str,
            "24h涨跌": f"{ticker.get('percentage', 0):.6f}%",
            "24h成交量": f"${ticker.get('quoteVolume', 0):,.0f}"
        })
        
        funding_rate = exchange.fetch_funding_rate(symbol)
        open_interest = exchange.fetch_open_interest(symbol)

        # --- 使用 vectorbt 计算指标 ---
        # 3分钟指标
        df_3m['EMA_20'] = vbt.MA.run(df_3m['close'], window=20, ewm=True).ma.values
        
        # MACD (12, 26, 9)
        macd_result = vbt.MACD.run(df_3m['close'], fast_window=12, slow_window=26, signal_window=9)
        df_3m['MACD_12_26_9'] = macd_result.macd.values
        df_3m['MACDh_12_26_9'] = macd_result.hist.values  # 使用 hist 而不是 histogram
        df_3m['MACDs_12_26_9'] = macd_result.signal.values
        
        # RSI (使用 pandas_ta，标准 Wilder's smoothing)
        df_3m['RSI_7'] = ta.rsi(df_3m['close'], length=7)
        df_3m['RSI_14'] = ta.rsi(df_3m['close'], length=14)
        
        # 4小时指标
        df_4h['EMA_20_4h'] = vbt.MA.run(df_4h['close'], window=20, ewm=True).ma.values
        df_4h['EMA_50_4h'] = vbt.MA.run(df_4h['close'], window=50, ewm=True).ma.values
        
        # ATR
        atr_3 = vbt.ATR.run(df_4h['high'], df_4h['low'], df_4h['close'], window=3)
        df_4h['ATR_3_4h'] = atr_3.atr.values
        
        atr_14 = vbt.ATR.run(df_4h['high'], df_4h['low'], df_4h['close'], window=14)
        df_4h['ATR_14_4h'] = atr_14.atr.values
        
        # MACD 4h
        macd_4h = vbt.MACD.run(df_4h['close'], fast_window=12, slow_window=26, signal_window=9)
        df_4h['MACD_4h'] = macd_4h.macd.values
        df_4h['MACDh_4h'] = macd_4h.hist.values  # 使用 hist 而不是 histogram
        df_4h['MACDs_4h'] = macd_4h.signal.values
        
        # RSI 4h (使用 pandas_ta，标准 Wilder's smoothing)
        df_4h['RSI_14_4h'] = ta.rsi(df_4h['close'], length=14)

        return {
            'success': True,
            'coin': coin,
            'ticker': ticker,
            'df_3m': df_3m,
            'df_4h': df_4h,
            'funding_rate': funding_rate,
            'open_interest': open_interest,
            'current_price': current_price
        }

    except Exception as e:
        logger.error(f"获取 {coin} 数据失败: {e}")
        return {
            'success': False,
            'coin': coin,
            'error': str(e)
        }


def get_market_data(exchange, coins=None, max_workers=8):
    """获取并格式化市场数据。
    
    Args:
        exchange: 交易所实例
        coins: 币种列表（默认从环境变量 TRADING_COINS 读取）
        max_workers: 最大并发线程数 8 
    
    Returns:
        格式化的市场数据字符串和结构化数据字典的元组
    """
    if coins is None:
        coins = TRADING_COINS

    market_data_str = ""
    prices_summary = {}
    coin_results = []
    structured_results = {}
    
    # 🔥 使用线程池并发获取数据
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # 提交所有任务
        future_to_coin = {
            executor.submit(_fetch_coin_data, exchange, coin): coin 
            for coin in coins
        }
        
        # 按完成顺序收集结果
        for future in as_completed(future_to_coin):
            result = future.result()
            coin_results.append(result)
    
    # 按原始顺序排序结果（保持输出一致性）
    coin_results.sort(key=lambda x: coins.index(x['coin']))
    
    # 格式化输出
    for result in coin_results:
        structured_results[result['coin']] = result
        if result['success']:
            # 记录价格
            prices_summary[result['coin']] = result['current_price']
            
            # 格式化数据
            market_data_str += format_coin_data(
                coin=result['coin'],
                ticker=result['ticker'],
                df_3m=result['df_3m'],
                df_4h=result['df_4h'],
                funding_rate=result['funding_rate'],
                open_interest=result['open_interest']
            )
        else:
            # 错误处理
            market_data_str += f"### 获取 {result['coin']} 数据时出错: {result['error']}\n\n---\n"
    
    # 🔥 汇总所有币种价格
    if prices_summary:
        log_tool_event("市场价格汇总", prices_summary)
            
    return market_data_str, structured_results

def get_account_balance(exchange) -> Dict[str, Any]:
    """获取账户余额信息"""
    try:
        # 如果有API密钥，尝试获取真实余额
        if hasattr(exchange, 'apiKey') and exchange.apiKey:
            balance = exchange.fetch_balance()
            result = {
                'total_balance': balance['total'].get('USDT', 10000),
                'free_balance': balance['free'].get('USDT', 10000),
                'used_balance': balance['used'].get('USDT', 0),
            }
            
            # 🔥 记录账户余额
            log_tool_event("获取账户余额", {
                "总余额": f"${result['total_balance']:.6f}",
                "可用余额": f"${result['free_balance']:.6f}",
                "占用余额": f"${result['used_balance']:.6f}"
            })
            
            return result
        else:
            # 没有API密钥时返回默认值
            log_tool_event("使用默认账户余额", "未配置API密钥")
            return {
                'total_balance': 10000,  # 默认值
                'free_balance': 10000,
                'used_balance': 0,
            }
    except Exception as e:
        logger.warning(f"获取账户余额失败，使用默认值: {e}")
        return {
            'total_balance': 10000,  # 默认值
            'free_balance': 10000,
            'used_balance': 0,
        }

def get_positions(exchange) -> List[Dict[str, Any]]:
    """获取当前持仓（包含杠杆、强平价、止盈止损）"""
    try:
        # 如果有API密钥，尝试获取真实持仓
        if hasattr(exchange, 'apiKey') and exchange.apiKey:
            positions = exchange.fetch_positions()
            active_positions = []

            # 🔥 获取所有未成交订单（用于查找止盈止损订单）
            open_orders = {}
            try:
                all_orders = exchange.fetch_open_orders()
                # 按 symbol 分组
                for order in all_orders:
                    symbol = order['symbol']
                    if symbol not in open_orders:
                        open_orders[symbol] = []
                    open_orders[symbol].append(order)
            except Exception as e:
                logger.warning(f"获取未成交订单失败: {e}")

            for position in positions:
          
                if position['contracts'] > 0:  # 有持仓
                    symbol = position['symbol']
                    
                    # 🔥 正确的获取方式：从 info 字段获取
                    # bitget 使用 cctx 这个库，映射时是在 info 中的
                    info = position.get('info', {})
                    stop_loss_price = float(info.get('stopLoss', 0) or 0)
                    take_profit_price = float(info.get('takeProfit', 0) or 0)

                    active_positions.append({
                        'symbol': position['symbol'],
                        'side': position['side'],
                        'size': position['contracts'],
                        'entry_price': position['entryPrice'],
                        'mark_price': position['markPrice'],
                        'unrealized_pnl': position['unrealizedPnl'],
                        'percentage': position['percentage'],
                        # 新增字段：杠杆和强平价
                        'leverage': position.get('leverage', 1),
                        'liquidation_price': position.get('liquidationPrice', 0),
                        'notional': position.get('notional', 0),  # 名义价值
                        # 🔥 新增：止盈止损价格
                        'stop_loss_price': stop_loss_price,
                        'take_profit_price': take_profit_price,
                    })
            
            # 🔥 记录持仓信息（包含止盈止损）
            if active_positions:
                positions_summary = []
                for pos in active_positions:
                    # 智能格式化价格
                    entry_p = pos['entry_price']
                    mark_p = pos['mark_price']
                    liq_p = pos['liquidation_price']
                    sl_p = pos['stop_loss_price']
                    tp_p = pos['take_profit_price']
                    
                    def fmt_p(p):
                        if p == 0:
                            return "未设置"
                        elif p >= 1000:
                            return f"${p:.6f}"
                        elif p >= 1:
                            return f"${p:.6f}"
                        else:
                            return f"${p:.8f}"
                    
                    summary = {
                        "币种": pos['symbol'],
                        "方向": pos['side'],
                        "数量": pos['size'],
                        "杠杆": f"{pos['leverage']}x",
                        "入场价": fmt_p(entry_p),
                        "当前价": fmt_p(mark_p),
                        "强平价": fmt_p(liq_p),
                        "未实现盈亏": f"${pos['unrealized_pnl']:.6f}",
                        "回报率": f"{pos['percentage']:+.2f}%",
                        "止损价": fmt_p(sl_p),
                        "止盈价": fmt_p(tp_p),
                    }
                    positions_summary.append(summary)
                
                log_tool_event("获取持仓信息", positions_summary)
            else:
                log_tool_event("获取持仓信息", "当前无持仓")
            
            return active_positions
        else:
            # 没有API密钥时返回空持仓
            log_tool_event("获取持仓信息", "未配置API密钥")
            return []
    except Exception as e:
        logger.warning(f"获取持仓失败: {e}")
        return []

def get_market_limits(exchange, symbol: str) -> Dict[str, Any]:
    """
    获取交易对的市场限制（最小/最大交易数量、价格精度等）
    
    Args:
        exchange: 交易所实例
        symbol: 交易对符号（如 "SOL/USDT:USDT"）
    
    Returns:
        包含限制信息的字典
    """
    # Bitget 的最小交易数量
    BITGET_MIN_AMOUNTS = {
        'BTC/USDT:USDT': 0.0001,
        'ETH/USDT:USDT': 0.001,
        'SOL/USDT:USDT': 0.1,     
        'LTC/USDT:USDT': 0.01,
        'SUI/USDT:USDT': 0.1,
        'BGB/USDT:USDT': 1,
        'DOGE/USDT:USDT': 1,
    }
    
    try:
        # 加载市场信息
        if not hasattr(exchange, 'markets') or not exchange.markets:
            exchange.load_markets()
        
        market = exchange.market(symbol)
        limits = market.get('limits', {})
        
        # 优先使用交易所返回的限制，如果没有则使用我们的后备值
        min_amount = limits.get('amount', {}).get('min')
        if min_amount is None or min_amount == 0:
            min_amount = BITGET_MIN_AMOUNTS.get(symbol, 0.1)
        
        return {
            'min_amount': min_amount,
            'max_amount': limits.get('amount', {}).get('max', float('inf')),
            'min_cost': limits.get('cost', {}).get('min', 5),
            'amount_precision': market.get('precision', {}).get('amount', 8),
            'price_precision': market.get('precision', {}).get('price', 8),
        }
    except Exception as e:
        logger.warning(f"获取市场限制失败 {symbol}: {e}，使用后备值")
        # 返回后备值
        min_amount = BITGET_MIN_AMOUNTS.get(symbol, 0.1)
        return {
            'min_amount': min_amount,
            'max_amount': float('inf'),
            'min_cost': 5,
            'amount_precision': 3,
            'price_precision': 2,
        }


def _resolve_order_fill(exchange, symbol: str, order: Dict[str, Any], side: str, max_attempts: int = 3, sleep_ms: int = 200) -> (float, float):
    """
    回查订单与成交，尽量获取准确的成交均价与成交数量。
    优先顺序：order.average -> order.price -> fetch_order -> fetch_my_trades(加权均价) -> ticker.last
    """
    order_id = order.get('id') or order.get('orderId')
    price = order.get('average') or order.get('price') or 0
    filled = order.get('filled') or order.get('amount') or 0

    attempt = 0
    while attempt < max_attempts and (price == 0 or not filled):
        try:
            # 1) 回查订单
            if order_id:
                fetched = exchange.fetch_order(order_id, symbol)
                price = fetched.get('average') or fetched.get('price') or price
                filled = fetched.get('filled') or filled
        except Exception:
            pass

        # 2) 如仍未获得，尝试从成交明细聚合
        if (price == 0 or not filled):
            try:
                trades = exchange.fetch_my_trades(symbol)
                if trades:
                    related = [t for t in trades if (t.get('order') == order_id) or (str(t.get('order')) == str(order_id))]
                    if related:
                        total_qty = sum(float(t.get('amount') or 0) for t in related)
                        if total_qty > 0:
                            vwap = sum(float(t.get('price') or 0) * float(t.get('amount') or 0) for t in related) / total_qty
                            price = price or vwap
                            filled = filled or total_qty
            except Exception:
                pass

        if price != 0 and filled:
            break

        time.sleep(sleep_ms / 1000)
        attempt += 1

    # 3) 最后兜底：使用市场价记录
    if price == 0:
        try:
            ticker = exchange.fetch_ticker(symbol)
            price = ticker.get('last', 0)
            logger.info(f"ℹ️ 订单未返回成交均价，使用市场价 ${price:.6f} 作为记录价")
        except Exception:
            price = 0

    return price, (filled or 0)

def execute_trade_order(exchange, decision: Dict[str, Any], dry_run: bool = False) -> Dict[str, Any]:
    """执行交易订单（增强错误处理，支持模拟模式）
    
    Args:
        exchange: 交易所实例
        decision: 交易决策字典
        dry_run: 是否为模拟运行模式（True=模拟，False=实盘）
    
    Returns:
        交易结果字典，包含 success, order_id, simulated 等字段
    """
    try:
        # 验证必需参数
        required_fields = ['signal', 'coin', 'quantity', 'leverage']
        for field in required_fields:
            if field not in decision:
                error_msg = f"缺少必需参数: {field}"
                logger.error(error_msg)
                return {
                    'success': False,
                    'order_id': None,
                    'side': None,
                    'quantity': 0,
                    'price': 0,
                    'error': error_msg,
                    'simulated': False
                }
        
        signal = decision['signal']
        coin = decision['coin']
        quantity = decision['quantity']
        leverage = decision['leverage']
        
        # 验证信号类型
        valid_signals = ['buy_to_enter', 'sell_to_enter', 'close', 'hold']
        if signal not in valid_signals:
            error_msg = f"无效的交易信号: {signal}"
            logger.error(error_msg)
            return {
                'success': False,
                'order_id': None,
                'side': None,
                'quantity': 0,
                'price': 0,
                'error': error_msg,
                'simulated': False
            }
        
        # 处理 hold 信号
        if signal == 'hold':
            logger.info(f"📊 持有信号: {coin}")
            return {
                'success': True,
                'order_id': None,
                'side': 'hold',
                'quantity': 0,
                'price': 0,
                'error': None,
                'simulated': dry_run
            }
        
        symbol = f"{coin}/USDT:USDT"
        is_swap_market = symbol.endswith(":USDT") or ":" in symbol
        order_type = "market"
        
        # 🔥 获取市场限制并验证交易数量
        market_limits = get_market_limits(exchange, symbol)
        min_amount = market_limits['min_amount']
        amount_precision = market_limits['amount_precision']
        
        # 检查数量是否满足最小要求
        if quantity < min_amount and signal in ['buy_to_enter', 'sell_to_enter']:
            error_msg = f"交易数量 {quantity} {coin} 低于最小要求 {min_amount} {coin}"
            logger.warning(f"⚠️ {error_msg}")
            
            # 尝试调整到最小数量（如果资金允许）
            try:
                ticker = exchange.fetch_ticker(symbol)
                current_price = ticker['last']
                required_capital = min_amount * current_price / leverage
                
                # 获取可用余额
                balance = get_account_balance(exchange)
                available = balance.get('free_balance', 0)
                
                if available >= required_capital:
                    # 资金足够，调整到最小数量
                    quantity = min_amount
                    logger.info(f"✅ 已调整交易数量到最小值: {quantity} {coin} (需要资金: ${required_capital:.6f})")
                else:
                    # 资金不足
                    error_msg = f"资金不足：需要 ${required_capital:.6f} 才能满足最小交易量 {min_amount} {coin}，当前可用 ${available:.6f}"
                    logger.error(f"❌ {error_msg}")
                    return {
                        'success': False,
                        'order_id': None,
                        'side': None,
                        'quantity': 0,
                        'price': 0,
                        'error': error_msg,
                        'simulated': False
                    }
            except Exception as e:
                logger.error(f"❌ 调整交易数量失败: {e}")
                return {
                    'success': False,
                    'order_id': None,
                    'side': None,
                    'quantity': 0,
                    'price': 0,
                    'error': error_msg,
                    'simulated': False
                }
        
        # 调整数量精度（确保 amount_precision 是整数）
        quantity = round(quantity, int(amount_precision))
        
        # 🔥 模拟运行模式：不执行实际交易，但获取当前价格用于模拟
        if dry_run:
            try:
                # 获取当前市场价格用于模拟
                ticker = exchange.fetch_ticker(symbol)
                current_price = ticker['last']
                # 智能格式化价格
                if current_price >= 1000:
                    price_str = f"${current_price:.6f}"
                elif current_price >= 1:
                    price_str = f"${current_price:.6f}"
                else:
                    price_str = f"${current_price:.8f}"
                logger.info(f"🎭 [模拟交易] {signal} {coin} 数量: {quantity} 模拟价格: {price_str}")
                return {
                    'success': True,
                    'order_id': f"dry_run_{int(time.time())}",
                    'side': signal,
                    'quantity': quantity,
                    'price': current_price,
                    'amount': quantity,
                    'error': None,
                    'simulated': True
                }
            except Exception as e:
                logger.warning(f"⚠️ 获取模拟价格失败，使用默认值: {e}")
                return {
                    'success': True,
                    'order_id': f"dry_run_{int(time.time())}",
                    'side': signal,
                    'quantity': quantity,
                    'price': 0,
                    'amount': quantity,
                    'error': None,
                    'simulated': True
                }
        
        # 检查是否有API密钥进行实际交易
        if not (hasattr(exchange, 'apiKey') and exchange.apiKey):
            logger.info(f"🎭 模拟交易: {signal} {coin} 数量: {quantity} (未配置API密钥)")
            return {
                'success': True,
                'order_id': f"mock_{int(time.time())}",
                'side': signal,
                'quantity': quantity,
                'price': 0,
                'error': None,
                'simulated': True
            }
        
        # 设置持仓模式和杠杆（只适用于合约）
        if is_swap_market:
            try:
                # 🔥 设置为单向持仓模式（one-way mode）
                # CCXT: False = 单向持仓, True = 双向持仓
                exchange.set_position_mode(False, symbol)
                logger.info(f"✅ 设置单向持仓模式 for {symbol}")
            except ccxt.BadRequest as e:
                logger.warning(f"⚠️ 设置持仓模式失败 (可能已设置): {e}")
            except Exception as e:
                logger.warning(f"⚠️ 设置持仓模式失败: {e}")
            
            # 设置杠杆
            if leverage > 1:
                try:
                    leverage_int = int(leverage)
                    exchange.set_leverage(leverage_int, symbol)
                    logger.info(f"✅ 设置杠杆 {leverage_int}x for {symbol}")
                except ccxt.BadRequest as e:
                    logger.warning(f"⚠️ 设置杠杆失败 (可能已设置): {e}")
                except Exception as e:
                    logger.error(f"❌ 设置杠杆失败: {e}")
                    return {
                        'success': False,
                        'order_id': None,
                        'side': None,
                        'quantity': 0,
                        'price': 0,
                        'error': f"设置杠杆失败: {str(e)}",
                        'simulated': False
                    }
        
        result = {'success': False, 'order_id': None, 'error': None, 'simulated': False}
        
        # 🔥 强制检查止损止盈（开仓必须设置止损止盈）
        stop_loss_price = decision.get('stop_loss_price', 0)
        take_profit_price = decision.get('take_profit_price', 0)
        
        # 只对开仓信号进行检查
        if signal in ['buy_to_enter', 'sell_to_enter']:
            if stop_loss_price <= 0 or take_profit_price <= 0:
                error_msg = f"❌ 开仓必须设置止损止盈！当前止损: ${stop_loss_price}, 止盈: ${take_profit_price}"
                logger.error(error_msg)
                logger.error(f"📋 决策详情: {decision}")
                return {
                    'success': False,
                    'order_id': None,
                    'side': None,
                    'quantity': 0,
                    'price': 0,
                    'error': error_msg,
                    'simulated': False
                }
        
        # 🔥 准备止损止盈参数（开仓时直接预设）
        # 参考：ccxt/bitget.py 第 5143-5148 行
        # Bitget 支持在开仓时预设止损止盈（presetStopLossPrice/presetStopSurplusPrice）
        extra_params = {}
        
        # 添加止损止盈到参数中（CCXT 会自动转换为 Bitget API 格式）
        if stop_loss_price > 0:
            extra_params['stopLoss'] = {
                'triggerPrice': stop_loss_price,
                'type': 'mark_price'  # 使用标记价格触发，避免插针
            }
            logger.info(f"📌 预设止损: ${stop_loss_price:.6f}")
        
        if take_profit_price > 0:
            extra_params['takeProfit'] = {
                'triggerPrice': take_profit_price,
                'type': 'mark_price'  # 使用标记价格触发
            }
            logger.info(f"📌 预设止盈: ${take_profit_price:.6f}")
        
        # 🔥 最终资金检查：确保有足够资金执行交易
        if signal in ['buy_to_enter', 'sell_to_enter']:
            try:
                ticker = exchange.fetch_ticker(symbol)
                current_price = ticker['last']
                # 计算所需保证金 = 名义价值 / 杠杆
                required_margin = (quantity * current_price) / leverage
                
                # 获取当前可用余额
                balance = get_account_balance(exchange)
                available = balance.get('free_balance', 0)
                
                # 预留5%作为缓冲（手续费等）
                required_with_buffer = required_margin * 1.05
                
                if available < required_with_buffer:
                    # 尝试调整数量以适应可用资金
                    max_affordable_quantity = (available * 0.95 * leverage) / current_price
                    
                    # 检查调整后的数量是否满足最小要求
                    if max_affordable_quantity >= min_amount:
                        old_quantity = quantity
                        quantity = round(max_affordable_quantity, int(amount_precision))
                        logger.warning(f"⚠️ 资金不足，已自动调整数量: {old_quantity} -> {quantity} {coin}")
                        logger.info(f"📊 调整后需要保证金: ${(quantity * current_price / leverage):.6f}, 可用: ${available:.6f}")
                    else:
                        error_msg = f"资金不足：需要保证金 ${required_margin:.6f} (含缓冲 ${required_with_buffer:.6f})，当前可用 ${available:.6f}。即使调整到最小数量 {min_amount} {coin} 也需要 ${(min_amount * current_price / leverage):.6f}"
                        logger.error(f"❌ {error_msg}")
                        logger.error(f"📊 详情: {coin} 数量={quantity}, 价格=${current_price:.6f}, 杠杆={leverage}x")
                        return {
                            'success': False,
                            'order_id': None,
                            'side': None,
                            'quantity': 0,
                            'price': 0,
                            'error': error_msg,
                            'simulated': False
                        }
                else:
                    logger.info(f"✅ 资金检查通过: 需要 ${required_with_buffer:.6f}, 可用 ${available:.6f}")
            except Exception as e:
                logger.warning(f"⚠️ 资金检查失败，继续执行: {e}")
        
        # 执行买入开多
        if signal == 'buy_to_enter':
            order = exchange.create_order(symbol, order_type, 'buy', quantity, None, extra_params)
            price, filled = _resolve_order_fill(exchange, symbol, order, 'long')
            
            result = {
                'success': True,
                'order_id': order.get('id'),
                'side': 'long',
                'quantity': quantity,
                'price': price,
                'amount': filled,
                'error': None,
                'simulated': False
            }
            price_str = f"${price:.6f}" if price else "未知"
            logger.info(f"✅ 开多仓成功: {coin} 数量: {quantity} 价格: {price_str} 成交: {filled}")
        
        # 执行卖出开空
        elif signal == 'sell_to_enter':
            order = exchange.create_order(symbol, order_type, 'sell', quantity, None, extra_params)
            price, filled = _resolve_order_fill(exchange, symbol, order, 'short')
            
            result = {
                'success': True,
                'order_id': order.get('id'),
                'side': 'short',
                'quantity': quantity,
                'price': price,
                'amount': filled,
                'error': None,
                'simulated': False
            }
            price_str = f"${price:.6f}" if price else "未知"
            logger.info(f"✅ 开空仓成功: {coin} 数量: {quantity} 价格: {price_str} 成交: {filled}")
        
        # 执行平仓
        elif signal == 'close':
            positions = get_positions(exchange)
            target_position = None
            
            for pos in positions:
                if coin in pos['symbol']:
                    target_position = pos
                    break
            
            if target_position:
                opposite_side = 'sell' if target_position['side'] == 'long' else 'buy'
                # 🔥 CCXT 单向持仓模式平仓：只需设置 reduceOnly=True
                # 参考：ccxt/bitget.py 第 5158-5162 行
                close_params = {
                    'reduceOnly': True  # 只减仓，不开新仓
                }
                order = exchange.create_order(symbol, order_type, opposite_side, target_position['size'], None, close_params)
                price, filled = _resolve_order_fill(exchange, symbol, order, target_position['side'])
                
                result = {
                    'success': True,
                    'order_id': order.get('id'),
                    'side': target_position['side'],  # ✅ 使用原持仓方向（long/short），而不是 'close'
                    'quantity': target_position['size'],
                    'price': price,
                    'amount': filled,
                    'error': None,
                    'simulated': False
                }
                logger.info(f"✅ 平仓成功: {coin} 方向: {target_position['side']} 数量: {result['quantity']} 价格: ${price:.6f} 成交: {filled}")
            else:
                error_msg = f"未找到 {coin} 的持仓"
                logger.warning(f"⚠️ {error_msg}")
                result = {
                    'success': False,
                    'order_id': None,
                    'side': 'close',
                    'quantity': 0,
                    'price': 0,
                    'error': error_msg,
                    'simulated': False
                }
        
        return result
    
    # 网络错误处理
    except ccxt.NetworkError as e:
        error_msg = f"网络错误: {str(e)}"
        logger.error(f"❌ {error_msg}")
        return {
            'success': False,
            'order_id': None,
            'side': None,
            'quantity': 0,
            'price': 0,
            'error': error_msg,
            'simulated': False
        }
    
    # 交易所错误处理
    except ccxt.ExchangeError as e:
        error_msg = f"交易所错误: {str(e)}"
        logger.error(f"❌ {error_msg}")
        return {
            'success': False,
            'order_id': None,
            'side': None,
            'quantity': 0,
            'price': 0,
            'error': error_msg,
            'simulated': False
        }
    
    # 余额不足错误
    except ccxt.InsufficientFunds as e:
        error_msg = f"余额不足: {str(e)}"
        logger.error(f"❌ {error_msg}")
        return {
            'success': False,
            'order_id': None,
            'side': None,
            'quantity': 0,
            'price': 0,
            'error': error_msg,
            'simulated': False
        }
    
    # 其他未知错误
    except Exception as e:
        error_msg = f"未知错误: {str(e)}"
        logger.error(f"❌ 执行交易失败: {error_msg}")
        return {
            'success': False,
            'order_id': None,
            'side': None,
            'quantity': 0,
            'price': 0,
            'error': error_msg,
            'simulated': False
        }

def set_stop_loss_take_profit(
    exchange,
    symbol: str,
    stop_loss_price: Optional[float],
    take_profit: Optional[float],
    side: str,
    position_size: Optional[float] = None,
    trigger_type: str = "market",
    reduce_only: bool = True,
    params: Optional[Dict[str, Any]] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """在 Bitget 上为当前仓位设置止损止盈。

    Args:
        exchange: 已初始化的 ccxt.bitget 实例
        symbol: 交易对 (如 "BTC/USDT:USDT")
        stop_loss_price: 止损触发价格 (None 表示不设置)
        take_profit: 止盈触发价格 (None 表示不设置)
        side: 持仓方向 ("long" 表示多头, "short" 表示空头)
        position_size: 指定保护的仓位大小 (合约数量). 缺省将自动读取当前仓位
        trigger_type: 触发单类型, 例如 "market" 或 "limit"
        reduce_only: 是否仅允许减仓
        params: 额外参数, 将透传给 ccxt
        dry_run: 是否为模拟运行模式（True=模拟，False=实盘）

    Returns:
        dict: 止损止盈委托的执行结果
    """
    params = params.copy() if params else {}

    if stop_loss_price is None and take_profit is None:
        logger.warning("⚠️ 未提供止损或止盈价格, 跳过设置")
        return {
            "success": False,
            "error": "Both stop_loss_price and take_profit are None",
            "simulated": dry_run,
            "order": None,
        }

    # 🔥 模拟运行模式：不设置实际止损止盈
    if dry_run:
        logger.info(
            f"🎭 [模拟模式] 设置止损止盈: {symbol} side={side} SL={stop_loss_price} TP={take_profit}"
        )
        return {
            "success": True,
            "simulated": True,
            "order": None,
        }

    if not (hasattr(exchange, "apiKey") and exchange.apiKey):
        logger.info(
            f"🎭 模拟设置止损止盈: {symbol} side={side} SL={stop_loss_price} TP={take_profit} (未配置API密钥)"
        )
        return {
            "success": True,
            "simulated": True,
            "order": None,
        }

    try:
        market = exchange.market(symbol)
        amount_precision = market.get("precision", {}).get("amount")

        quantity = position_size or params.pop("quantity", None)
        if quantity is None:
            for position in get_positions(exchange):
                if position.get("symbol") == symbol:
                    quantity = float(position.get("size") or position.get("contracts") or 0)
                    break

        if not quantity or quantity <= 0:
            logger.warning(f"⚠️ 未找到 {symbol} 的有效持仓数量, 跳过止损止盈设置")
            return {
                "success": False,
                "error": "No position size available",
                "simulated": False,
                "order": None,
            }

        # 精度处理
        quantity = float(quantity)
        if amount_precision is not None:
            # 确保 amount_precision 是整数
            amount_precision = int(amount_precision)
            quantity = float(round(quantity, amount_precision))

        # 正确做法：为已有仓位分别设置止损和止盈订单
        # 使用 create_stop_loss_order 和 create_take_profit_order
        # 而不是 create_order_with_take_profit_and_stop_loss（后者用于开仓时同时设置）
        
        order_side_close = "sell" if side == "long" else "buy"
        
        responses = []
        
        # 设置止损订单
        if stop_loss_price:
            try:
                sl_params = params.copy()
                sl_params["reduceOnly"] = True
                
                logger.info(
                    "📌 设置止损: symbol=%s side=%s qty=%s SL=%s",
                    symbol,
                    order_side_close,
                    quantity,
                    stop_loss_price,
                )
                
                sl_response = exchange.create_stop_loss_order(
                    symbol=symbol,
                    type="market",  # 止损触发后以市价成交
                    side=order_side_close,
                    amount=quantity,
                    price=None,  # 市价单不需要价格
                    stopLossPrice=stop_loss_price,
                    params=sl_params,
                )
                responses.append(("stop_loss_price", sl_response))
                logger.info("✅ 止损设置成功")
                
            except Exception as e:
                logger.error(f"❌ 止损设置失败: {str(e)}")
                raise
        
        # 设置止盈订单
        if take_profit:
            try:
                tp_params = params.copy()
                tp_params["reduceOnly"] = True
                
                logger.info(
                    "📌 设置止盈: symbol=%s side=%s qty=%s TP=%s",
                    symbol,
                    order_side_close,
                    quantity,
                    take_profit,
                )
                
                tp_response = exchange.create_take_profit_order(
                    symbol=symbol,
                    type="market",  # 止盈触发后以市价成交
                    side=order_side_close,
                    amount=quantity,
                    price=None,  # 市价单不需要价格
                    takeProfitPrice=take_profit,
                    params=tp_params,
                )
                responses.append(("take_profit", tp_response))
                logger.info("✅ 止盈设置成功")
                
            except Exception as e:
                logger.error(f"❌ 止盈设置失败: {str(e)}")
                raise
        
        response = {"stop_loss_price": None, "take_profit": None}
        for order_type, order_response in responses:
            response[order_type] = order_response
        
        logger.info("✅ 止损止盈设置完成: %s", response)
        return {
            "success": True,
            "simulated": False,
            "order": response,
        }

    except Exception as error:
        logger.error(f"❌ 设置止损止盈失败: {error}")
        return {
            "success": False,
            "error": str(error),
            "simulated": False,
            "order": None,
        }


if __name__ == '__main__':
    # 用于测试
    exchange = get_exchange()
    market_data = get_market_data(exchange)
    print(market_data)