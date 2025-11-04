from common.log_handler import logger, log_state_update, log_system_event
from Money_Agent.state import AgentState
from Money_Agent.database import get_database
from Money_Agent.config import MIN_EQUITY_FOR_MULTI_ASSET, LOW_EQUITY_COINS, TRADING_COINS, TRADING_COINS
from Money_Agent.tools.exchange_data_tool import (
    get_market_data, 
    get_account_balance, 
    get_positions
)
from Money_Agent.tools.exchange import exchange

def update_market_data(state: AgentState):
    """更新市场数据和账户信息。"""
    try:
        # 🔥 首次运行时，先输出初始状态
        is_first_run = state["minutes_elapsed"] == 0
        
        if is_first_run:
            log_system_event("=" * 60, "")
            log_system_event("📊 开始获取初始状态", "")
            log_system_event("=" * 60, "")
        
        # 更新账户信息
        balance = get_account_balance(exchange)
        
        # ==================== 🔥 资金限制逻辑 ====================
        # 根据账户权益动态调整交易币种
        
        # 🐛 调试日志 - 检查配置加载
        logger.info(f"🔍 配置检查 - LOW_EQUITY_COINS: {LOW_EQUITY_COINS}, 类型: {type(LOW_EQUITY_COINS)}, 长度: {len(LOW_EQUITY_COINS)}")
        logger.info(f"🔍 配置检查 - MIN_EQUITY_FOR_MULTI_ASSET: {MIN_EQUITY_FOR_MULTI_ASSET}")
        
        account_equity = balance.get('total_balance', 0)
        
        # 判断是否需要启用低资金模式
        if account_equity < MIN_EQUITY_FOR_MULTI_ASSET:
            # 低资金模式：只交易指定币种（默认 DOGE）
            active_coins = LOW_EQUITY_COINS
            logger.info(f"🔍 进入低资金模式 - active_coins 赋值为: {active_coins}")
            
            # 记录模式切换
            if not state.get('_low_equity_mode_logged', False):
                log_system_event("⚠️ 低资金模式已启用", {
                    "账户权益": f"${account_equity:.6f}",
                    "阈值": f"${MIN_EQUITY_FOR_MULTI_ASSET:.6f}",
                    "限制交易币种": LOW_EQUITY_COINS,
                    "其他币种": "仅作行情参考",
                    "说明": f"当账户权益低于 ${MIN_EQUITY_FOR_MULTI_ASSET:.6f} 时，为控制风险只交易 {', '.join(LOW_EQUITY_COINS)}"
                })
                state['_low_equity_mode_logged'] = True
                state['_low_equity_mode'] = True
        else:
            # 正常模式：交易所有配置的币种
            active_coins = TRADING_COINS
            
            # 如果之前是低资金模式，记录恢复
            if state.get('_low_equity_mode', False):
                log_system_event("✅ 多币种模式已恢复", {
                    "账户权益": f"${account_equity:.6f}",
                    "阈值": f"${MIN_EQUITY_FOR_MULTI_ASSET:.6f}",
                    "交易币种": TRADING_COINS,
                    "说明": "账户权益已恢复，可以交易所有配置的币种"
                })
                state['_low_equity_mode'] = False
                state['_low_equity_mode_logged'] = False
        
        # 保存当前激活的币种列表到状态
        state['active_trading_coins'] = active_coins
        
        # 🐛 调试日志
        logger.info(f"🔍 update_market_data - 设置 active_trading_coins: {active_coins}, 长度: {len(active_coins)}")
        
        # 更新持仓信息
        positions = get_positions(exchange)
        state["positions"] = positions
        
        # 🔥 首次运行时，记录初始资金和持仓
        if "initial_balance" not in state["account_info"]:
            state["account_info"]["initial_balance"] = balance["total_balance"]
            
            # 输出初始账户信息
            log_state_update("💰 初始账户信息", {
                "总余额": f"${balance['total_balance']:.6f}",
                "可用余额": f"${balance['free_balance']:.6f}",
                "占用余额": f"${balance['used_balance']:.6f}",
                "资金来源": "实际账户余额" if balance['total_balance'] != 10000 else "默认模拟资金"
            })
            
            # 输出初始持仓信息
            if positions:
                positions_detail = []
                for pos in positions:
                    # 智能格式化价格
                    entry_price = pos.get('entry_price', 0)
                    mark_price = pos.get('mark_price', 0)
                    liq_price = pos.get('liquidation_price', 0)
                    sl_p = pos.get('stop_loss_price', 0)
                    tp_p = pos.get('take_profit_price', 0)
                    
                    def fmt_price(p):
                        if p >= 1000: return f"${p:.6f}"
                        elif p >= 1: return f"${p:.6f}"
                        else: return f"${p:.8f}"
                    
                    positions_detail.append({
                        "币种": pos.get('symbol', 'N/A'),
                        "方向": pos.get('side', 'N/A'),
                        "数量": pos.get('size', 0),
                        "杠杆": f"{pos.get('leverage', 1)}x",
                        "入场价": fmt_price(entry_price),
                        "当前价": fmt_price(mark_price),
                        "强平价": fmt_price(liq_price),
                        "未实现盈亏": f"${pos.get('unrealized_pnl', 0):.6f}",
                        "回报率": f"${pos.get('percentage', 0):.6f}",
                        "止损价": fmt_price(sl_p),
                        "止盈价": fmt_price(tp_p),
                    })
                log_state_update("📈 初始持仓信息", positions_detail)
            else:
                log_state_update("📈 初始持仓信息", "当前无持仓")
        
        state["account_info"].update({
            "cash_available": balance["free_balance"],
            "account_value": balance["total_balance"],
        })
        
        # 更新市场数据（获取各币种价格）
        # 注意：仍然获取所有币种的行情数据用于参考，但只有 active_coins 可以交易
        if is_first_run:
            log_system_event("🔍 正在获取市场数据...", "")
        
        # get_market_data 返回的是格式化的字符串，不是列表
        formatted_str, structured_data = get_market_data(exchange)
        state["market_data"] = formatted_str
        state["structured_market_data"] = structured_data
        
        # 保存市场价格到数据库（从交易所获取最新价格）
        try:

            db = get_database()
            market_prices = {}
            
            for coin in TRADING_COINS:
                try:
                    symbol = f"{coin}/USDT:USDT"
                    ticker = exchange.fetch_ticker(symbol)
                    market_prices[coin] = {
                        'price': ticker.get('last', 0),
                        'volume_24h': ticker.get('quoteVolume', 0),
                        'change_24h': ticker.get('percentage', 0),
                        'funding_rate': 0,  # 需要单独获取
                        'open_interest': 0   # 需要单独获取
                    }
                except Exception as e:
                    logger.info(f"获取 {coin} 价格失败: {e}")
                    continue
            
            if market_prices:
                db.save_market_prices(market_prices)
        except Exception as e:
            logger.warning(f"⚠️ 保存市场价格失败: {e}")
        
        # 模拟时间流逝
        state["minutes_elapsed"] += 3
        
        if is_first_run:
            log_system_event("=" * 60, "")
            log_system_event("✅ 初始状态获取完成，开始交易决策", "")
            log_system_event("=" * 60, "")
        else:
            log_state_update("市场数据更新完成", {
                "account_value": f"${balance['total_balance']:.6f}",
                "cash_available": f"${balance['free_balance']:.6f}",
                "positions_count": len(positions)
            })
        
    except Exception as e:
        logger.error(f"更新市场数据失败: {e}")
        state["minutes_elapsed"] += 3  # 即使失败也要推进时间
    
    return state
