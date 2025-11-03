# Money-Agent/graph.py
import json
import logging
from langchain_core.prompts import ChatPromptTemplate
from .prompts import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE
from .doge_prompts import DOGE_SYSTEM_PROMPT, DOGE_USER_PROMPT_TEMPLATE
from .state import AgentState
from .tools.exchange_data_tool import (
    get_exchange, 
    get_market_data, 
    get_account_balance, 
    get_positions,
    execute_trade_order,
    set_stop_loss_take_profit
)
from .model import create_structured_model
from .schemas import TradingDecision
from .database import get_database
from common.log_handler import logger, log_agent_thought, log_tool_event, log_state_update, log_system_event

# 初始化交易所
exchange = get_exchange()

# 初始化结构化输出模型
structured_llm = create_structured_model()

def get_decision(state: AgentState):
    """获取 Agent 的决策（使用结构化输出）。"""
    from Money_Agent.prompt_formatter import format_positions
    
    try:
        # 记录当前账户状态
        account_info = state["account_info"]
        positions = state["positions"]
        
        # 🔥 使用彩色日志展示账户状态
        positions_summary = []
        if positions:
            for pos in positions:
                positions_summary.append({
                    "币种": pos.get('symbol', 'N/A'),
                    "方向": pos.get('side', 'N/A'),
                    "数量": f"{pos.get('size', 0)} 张",
                    "未实现盈亏": f"${pos.get('unrealized_pnl', 0):.6f}"
                })
        
        log_state_update("当前账户状态", {
            "可用余额": f"${account_info.get('cash_available', 0):.6f}",
            "账户总值": f"${account_info.get('account_value', 0):.6f}",
            "收益率": f"{account_info.get('return_pct', 0):.6f}%",
            "夏普比率": f"{account_info.get('sharpe_ratio', 0):.6f}",
            "持仓": positions_summary if positions_summary else "无"
        })
        
        # 🔥 根据账户权益动态选择 Prompt
        # 统一从 state 读取低资金模式标志，确保与 update_market_data 判定一致
        from Money_Agent.config import MIN_EQUITY_FOR_MULTI_ASSET
        account_equity = account_info.get('account_value', 0)
        
        # 如果 _low_equity_mode 还未初始化（首次运行），根据账户权益判断
        if '_low_equity_mode' not in state:
            state['_low_equity_mode'] = account_equity < MIN_EQUITY_FOR_MULTI_ASSET
        
        is_low_equity_mode = state.get('_low_equity_mode', False)
        
        if is_low_equity_mode:
            # 低资金模式：使用 DOGE 专用 Prompt
            system_prompt = DOGE_SYSTEM_PROMPT
            user_prompt_template = DOGE_USER_PROMPT_TEMPLATE
            prompt_mode = "低资金模式 (DOGE 专用)"
        else:
            # 正常模式：使用多币种 Prompt
            system_prompt = SYSTEM_PROMPT
            user_prompt_template = USER_PROMPT_TEMPLATE
            prompt_mode = "正常模式 (多币种)"
        
        log_agent_thought(f"📋 使用 Prompt: {prompt_mode}", {
            "账户权益": f"${account_equity:.6f}",
            "阈值": f"${MIN_EQUITY_FOR_MULTI_ASSET:.6f}",
            "Prompt 类型": prompt_mode
        })
        
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system_prompt),
                ("user", user_prompt_template),
            ]
        )
        
        # 使用新的格式化工具生成高质量的持仓描述（传入交易历史以恢复 exit_plan）
        trade_history = state.get("trade_history", [])
        positions_formatted = format_positions(positions, trade_history)
        
        formatted_prompt = prompt.format(
            minutes_elapsed=state["minutes_elapsed"],
            market_data=state["market_data"],
            return_pct=account_info.get("return_pct", 0),
            sharpe_ratio=account_info.get("sharpe_ratio", 0),
            cash_available=account_info.get("cash_available", 10000),
            account_value=account_info.get("account_value", 10000),
            positions_formatted=positions_formatted,
        )
        
        # 🔥 记录 LLM 输入（简化版，避免过长）
        log_agent_thought("准备调用 LLM 获取交易决策", {
            "时间点": f"{state['minutes_elapsed']} 分钟",
            "可用资金": f"${account_info.get('cash_available', 0):.6f}",
            "持仓数": len(positions)
        })
        
        # 使用结构化输出模型（Langfuse 会自动追踪）
        decision: TradingDecision = structured_llm.invoke(formatted_prompt)
        
        # 🔥 验证决策有效性：开仓信号必须有有效的止盈止损
        if decision.signal in ['buy_to_enter', 'sell_to_enter']:
            if decision.profit_target <= 0 or decision.stop_loss <= 0:
                logger.warning(f"⚠️ LLM返回的开仓信号缺少有效止盈止损，强制改为hold")
                logger.warning(f"原决策: {decision.signal} {decision.coin}, 止盈: {decision.profit_target}, 止损: {decision.stop_loss}")
                decision.signal = "hold"
                decision.coin = ""
                decision.quantity = 0.0
                decision.leverage = 1
                decision.profit_target = 0.0
                decision.stop_loss = 0.0
                decision.justification = f"[系统修正] LLM返回的决策缺少有效止盈止损，已改为持有。原因: {decision.justification}"
        
        # 🔥 记录 LLM 输出
        log_agent_thought("LLM 决策输出", {
            "信号": decision.signal,
            "币种": decision.coin,
            "数量": decision.quantity,
            "杠杆": f"{decision.leverage}x",
            "信心度": f"{decision.confidence:.1%}",
            "止盈": f"${decision.profit_target:.6f}",
            "止损": f"${decision.stop_loss:.6f}",
            "理由": decision.justification
        })
        
        # ==================== 🔥 交易限制检查 ====================
        # 只限制新开仓信号（buy_to_enter, sell_to_enter），允许平仓（close）和持有（hold）
        active_coins = state.get('active_trading_coins', [])
        
        # 🐛 调试日志
        logger.info(f"🔍 交易限制检查 - active_coins: {active_coins}, 类型: {type(active_coins)}, 长度: {len(active_coins)}")
        logger.info(f"🔍 决策信号: {decision.signal}, 币种: {decision.coin}")
        
        if decision.signal in ["buy_to_enter", "sell_to_enter"] and decision.coin not in active_coins:
            # 拒绝该交易，强制改为 hold
            original_signal = decision.signal
            original_coin = decision.coin
            
            log_system_event("🚫 交易被限制", {
                "原始信号": original_signal,
                "目标币种": original_coin,
                "限制原因": f"当前只允许交易 {', '.join(active_coins)}",
                "账户权益": f"${account_info.get('account_value', 0):.6f}",
                "处理方式": "强制改为 hold 信号",
                "说明": "close 信号不受限制，可以平仓任何持仓"
            })
            
            # 修改决策为 hold
            decision.signal = "hold"
            decision.coin = ""
            decision.quantity = 0.0
            logger.info("准备修改 justification...")
            decision.justification = f"[系统限制] 原计划 {original_signal} {original_coin}，但当前低资金模式只允许交易 {', '.join(active_coins)}。{decision.justification}"
            logger.info(f"justification 修改完成: {decision.justification}")
            logger.info(f"[系统限制] 原计划 {original_signal} {original_coin}，但当前低资金模式只允许交易 {', '.join(active_coins)}。{decision.justification}")
       
        # 转换为字典格式
        state["decision"] = decision.dict()
        
    except Exception as e:
        logger.error(f"获取决策失败: {e}")
        # 回退到默认持有决策
        state["decision"] = {
            "signal": "hold",
            "coin": "",
            "quantity": 0.0,
            "leverage": 1,
            "profit_target": 0.0,
            "stop_loss": 0.0,
            "invalidation_condition": "N/A",
            "confidence": 0.0,
            "risk_usd": 0.0,
            "justification": f"Error getting decision: {str(e)}"
        }

    return state

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
        from Money_Agent.config import MIN_EQUITY_FOR_MULTI_ASSET, LOW_EQUITY_COINS, TRADING_COINS
        
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
                        "未实现盈亏": f"${pos.get('unrealized_pnl', 0):.6f}"
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
        state["market_data"] = get_market_data(exchange)
        
        # 保存市场价格到数据库（从交易所获取最新价格）
        try:
            from Money_Agent.config import TRADING_COINS
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

def execute_trade(state: AgentState):
    """执行交易（支持模拟模式）。"""
    decision = state["decision"]
    account_info = state["account_info"]
    positions = state["positions"]
    dry_run = state.get("dry_run", False)  # 获取模拟运行标志
    
    # 🔥 使用彩色日志展示交易决策
    positions_before = []
    if positions:
        for pos in positions:
            positions_before.append(f"{pos.get('symbol', 'N/A')} {pos.get('side', 'N/A')} {pos.get('contracts', 0)}张")
    
    mode_indicator = "🎭 [模拟模式]" if dry_run else "💰 [实盘模式]"
    log_state_update(f"{mode_indicator} 准备执行交易", {
        "信号": decision['signal'],
        "币种": decision['coin'],
        "数量": decision['quantity'],
        "杠杆": f"{decision['leverage']}x",
        "止盈": f"${decision['profit_target']:.6f}",
        "止损": f"${decision['stop_loss']:.6f}",
        "信心度": f"{decision['confidence']:.2%}",
        "理由": decision['justification'],
        "执行前余额": f"${account_info.get('cash_available', 0):.6f}",
        "执行前总值": f"${account_info.get('account_value', 0):.6f}",
        "执行前持仓": positions_before if positions_before else "无"
    })
    
    # 如果是持有信号，不执行任何交易
    if decision["signal"] == "hold":
        log_state_update(f"{mode_indicator} 持有决策", "无需执行交易")
        return state
    
    try:
        # 执行交易（传递 dry_run 参数）
        trade_result = execute_trade_order(exchange, decision, dry_run=dry_run)
        
        if trade_result["success"]:
            # 🔥 将成交价格添加到 decision 中，供数据库保存使用
            decision['entry_price'] = trade_result.get('price', 0)
            decision['side'] = trade_result.get('side', 'N/A')
            
            # 🔥 使用彩色日志记录交易成功
            mode_tag = "🎭 [模拟]" if trade_result.get('simulated', False) else "✅"
            # 确保价格不为 None
            trade_price = trade_result.get('price') or 0
            # 智能格式化价格
            if trade_price >= 1000:
                price_str = f"${trade_price:.6f}"
            elif trade_price >= 1:
                price_str = f"${trade_price:.6f}"
            else:
                price_str = f"${trade_price:.8f}"
            
            log_state_update(f"{mode_tag} 交易执行成功", {
                "订单ID": trade_result.get('order_id', 'N/A'),
                "成交价格": price_str,
                "成交数量": trade_result.get('amount', 0),
                "模拟交易": "是" if trade_result.get('simulated', False) else "否"
            })
            
            # 获取最新账户信息
            try:
                updated_balance = get_account_balance(exchange)
                updated_positions = get_positions(exchange)
                
                positions_after = []
                if updated_positions:
                    for pos in updated_positions:
                        positions_after.append({
                            "币种": pos.get('symbol', 'N/A'),
                            "方向": pos.get('side', 'N/A'),
                            "数量": f"{pos.get('size', 0)} 张",
                            "未实现盈亏": f"${pos.get('unrealized_pnl', 0):.6f}"
                        })
                
                log_state_update("交易后账户状态", {
                    "余额": f"${updated_balance.get('free_balance', 0):.6f}",
                    "账户总值": f"${updated_balance.get('total_balance', 0):.6f}",
                    "持仓": positions_after if positions_after else "无"
                })
                
            except Exception as e:
                logger.warning(f"⚠️ 获取执行后账户信息失败: {e}")
            
            # 设置止损止盈（如果支持）
            if decision["signal"] in ["buy_to_enter", "sell_to_enter"]:
                symbol = f"{decision['coin']}/USDT:USDT"
                side = "long" if decision["signal"] == "buy_to_enter" else "short"
                sl_tp_result = set_stop_loss_take_profit(
                    exchange, 
                    symbol, 
                    decision["stop_loss"], 
                    decision["profit_target"], 
                    side,
                    dry_run=dry_run
                )
                
                # 验证止损止盈是否设置成功
                if sl_tp_result.get("success"):
                    mode_tag = "🎭 [模拟]" if sl_tp_result.get('simulated', False) else "✅"
                    log_state_update(f"{mode_tag} 止损止盈设置成功", {
                        "止损价": f"${decision['stop_loss']:.6f}",
                        "止盈价": f"${decision['profit_target']:.6f}",
                        "模拟模式": "是" if sl_tp_result.get('simulated', False) else "否"
                    })
                else:
                    log_state_update("⚠️ 止损止盈设置失败", {
                        "错误": sl_tp_result.get('error', 'Unknown error'),
                        "警告": "仓位已开启但无止损保护！请手动设置止损"
                    }, level=logging.WARNING)
            
            # 更新状态中的交易记录
            if "trade_history" not in state:
                state["trade_history"] = []
            
            state["trade_history"].append({
                "timestamp": state["minutes_elapsed"],
                "decision": decision,
                "result": trade_result,
                "account_value": state["account_info"].get("account_value", 0)
            })
            
        else:
            # 🔥 使用彩色日志记录交易失败
            log_state_update("❌ 交易执行失败", {
                "错误信息": trade_result.get('error', 'Unknown error')
            }, level=logging.ERROR)
            
    except Exception as e:
        logger.error(f"❌ 交易执行异常: {e}")
    
    return state

def calculate_performance_metrics(state: AgentState):
    """计算性能指标"""
    try:
        account_value = state["account_info"].get("account_value", 0)
        # 🔥 使用动态获取的初始资金
        initial_value = state["account_info"].get("initial_balance", account_value)
        
        # 计算收益率
        if initial_value > 0:
            return_pct = (account_value - initial_value) / initial_value * 100
        else:
            return_pct = 0.0
        
        # 计算夏普比率（基于历史收益率）
        trade_history = state.get("trade_history", [])
        if len(trade_history) >= 2:
            # 提取历史收益率
            returns = []
            for i in range(1, len(trade_history)):
                prev_value = trade_history[i-1].get("account_value", initial_value)
                curr_value = trade_history[i].get("account_value", initial_value)
                if prev_value > 0:
                    returns.append((curr_value - prev_value) / prev_value)
            
            if returns:
                import numpy as np
                mean_return = np.mean(returns)
                std_return = np.std(returns)
                # 夏普比率 = (平均收益 - 无风险利率) / 收益标准差
                # 假设无风险利率为0
                sharpe_ratio = mean_return / std_return if std_return > 0 else 0.0
            else:
                sharpe_ratio = 0.0
        else:
            # 交易次数不足，使用简化计算
            sharpe_ratio = return_pct / 10 if return_pct > 0 else return_pct / 20
        
        state["account_info"].update({
            "return_pct": return_pct,
            "sharpe_ratio": sharpe_ratio
        })
        
        # 🔥 使用彩色日志输出性能汇总
        log_state_update("性能指标汇总", {
            "当前账户总值": f"${account_value:.6f}",
            "初始资金": f"${initial_value:.6f}",
            "总收益率": f"{return_pct:+.2f}%",
            "夏普比率": f"{sharpe_ratio:.6f}",
            "持仓数量": len(state.get('positions', [])),
            "交易次数": len(trade_history),
            "说明": "夏普比率 > 1 表示良好的风险调整收益" if len(trade_history) >= 2 else "需要至少2次交易才能准确计算夏普比率"
        })
        
    except Exception as e:
        logger.error(f"计算性能指标失败: {e}")
    
    return state
