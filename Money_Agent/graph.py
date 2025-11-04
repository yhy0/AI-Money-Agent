# Money-Agent/graph.py
import logging
from langchain_core.prompts import ChatPromptTemplate
from Money_Agent.prompts import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE
from Money_Agent.doge_prompts import DOGE_SYSTEM_PROMPT, DOGE_USER_PROMPT_TEMPLATE
from Money_Agent.state import AgentState
from Money_Agent.tools.exchange_data_tool import (
    get_account_balance, 
    get_positions,
    execute_trade_order,
    set_stop_loss_take_profit
)
from Money_Agent.config import MIN_EQUITY_FOR_MULTI_ASSET, exchange
from Money_Agent.model import create_structured_model
from Money_Agent.schemas import TradingDecision
from common.log_handler import logger, log_agent_thought, log_state_update, log_system_event, log_security_event
from Money_Agent.utils.prompt_formatter import format_positions


# 初始化结构化输出模型
structured_llm = create_structured_model()

def get_agent_decision(state: AgentState):
    """获取 Agent 的决策（使用结构化输出）。"""
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
            if decision.take_profit_price <= 0 or decision.stop_loss_price <= 0:
                logger.warning(f"⚠️ LLM返回的开仓信号缺少有效止盈止损，强制改为hold")
                logger.warning(f"原决策: {decision.signal} {decision.coin}, 止盈: {decision.take_profit_price}, 止损: {decision.stop_loss_price}")
                decision.signal = "hold"
                decision.coin = ""
                decision.quantity = 0.0
                decision.leverage = 1
                decision.take_profit_price = 0.0
                decision.stop_loss_price = 0.0
                decision.justification = f"[系统修正] LLM返回的决策缺少有效止盈止损，已改为持有。原因: {decision.justification}"
        
        # 🔥 记录 LLM 输出
        log_agent_thought("LLM 决策输出", {
            "信号": decision.signal,
            "币种": decision.coin,
            "数量": decision.quantity,
            "杠杆": f"{decision.leverage}x",
            "信心度": f"{decision.confidence:.1%}",
            "止盈": f"${decision.take_profit_price:.6f}",
            "止损": f"${decision.stop_loss_price:.6f}",
            "理由": decision.justification
        })
        
        # ==================== 🔥 趋势一致性验证 ====================
        if decision.signal in ['buy_to_enter', 'sell_to_enter']:
            validation_result = validate_trend_consistency(
                decision.dict(),
                state["market_data"],
                state.get("trade_history", [])
            )
            
            # 记录趋势一致性检查结果
            trend_info = validation_result.get('trend_info', {})
            if trend_info:
                log_state_update("📊 趋势一致性检查", {
                    "币种": decision.coin,
                    "4h趋势": trend_info.get('4h_trend', 'N/A'),
                    "EMA20(4h)": f"${trend_info.get('ema20_4h', 0):.6f}",
                    "EMA50(4h)": f"${trend_info.get('ema50_4h', 0):.6f}",
                    "MACD(4h)": f"{trend_info.get('macd_4h', 0):.6f}",
                    "交易信号": decision.signal,
                    "信念度": f"{decision.confidence:.1%}",
                    "验证结果": "✅ 通过" if validation_result['valid'] else "❌ 未通过"
                })
            
            # 如果有警告，记录到安全事件日志
            if validation_result['warnings']:
                for warning in validation_result['warnings']:
                    log_security_event(warning, {
                        "币种": decision.coin,
                        "信号": decision.signal,
                        "信念度": f"{decision.confidence:.1%}",
                        "4h趋势": trend_info.get('4h_trend', 'N/A')
                    })
            
            # 如果验证未通过，强制改为 hold
            if not validation_result['valid']:
                original_signal = decision.signal
                original_coin = decision.coin
                
                log_security_event("🚫 趋势一致性规则违反，交易被拒绝", {
                    "原始信号": original_signal,
                    "目标币种": original_coin,
                    "拒绝原因": "; ".join(validation_result['warnings']),
                    "处理方式": "强制改为 hold 信号"
                })
                
                # 修改决策为 hold
                decision.signal = "hold"
                decision.coin = ""
                decision.quantity = 0.0
                decision.leverage = 1
                decision.take_profit_price = 0.0
                decision.stop_loss_price = 0.0
                decision.justification = f"[趋势规则限制] {'; '.join(validation_result['warnings'])}。原计划: {original_signal} {original_coin}。{decision.justification}"
        
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
            "take_profit_price": 0.0,
            "stop_loss_price": 0.0,
            "invalidation_condition": "N/A",
            "confidence": 0.0,
            "risk_usd": 0.0,
            "justification": f"Error getting decision: {str(e)}"
        }

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
    # 如果是持有信号，不执行任何交易
    if decision["signal"] == "hold":
        log_state_update(f"{mode_indicator} 持有决策, 无需执行交易", {})
        return state

    log_state_update(f"{mode_indicator} 准备执行交易", {
        "信号": decision['signal'],
        "币种": decision['coin'],
        "数量": decision['quantity'],
        "杠杆": f"{decision['leverage']}x",
        "止盈": f"${decision['take_profit_price']:.6f}",
        "止损": f"${decision['stop_loss_price']:.6f}",
        "信心度": f"{decision['confidence']:.2%}",
        "理由": decision['justification'],
        "执行前余额": f"${account_info.get('cash_available', 0):.6f}",
        "执行前总值": f"${account_info.get('account_value', 0):.6f}",
        "执行前持仓": positions_before if positions_before else "无"
    })

    
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
            
            # 🔥 验证止损止盈是否已设置（避免重复设置）
            # 开仓时已经通过 extra_params 预设了止损止盈，这里只需验证
            if decision["signal"] in ["buy_to_enter", "sell_to_enter"]:
                symbol = f"{decision['coin']}/USDT:USDT"
                
                # 🔥 检查持仓的止损止盈是否已设置
                try:
                    positions = get_positions(exchange)
                    current_position = None
                    for pos in positions:
                        if pos.get('symbol') == symbol:
                            current_position = pos
                            break
                    
                    if current_position:
                        sl_price = current_position.get('stop_loss_price', 0)
                        tp_price = current_position.get('take_profit_price', 0)
                        
                        if sl_price > 0 and tp_price > 0:
                            # 止损止盈已设置（开仓时预设成功）
                            log_state_update("✅ 止损止盈已生效", {
                                "止损价": f"${sl_price:.6f}",
                                "止盈价": f"${tp_price:.6f}",
                                "来源": "开仓时预设"
                            })
                        else:
                            # 开仓时预设失败，需要补充设置
                            logger.warning("⚠️ 开仓时止损止盈预设失败，正在补充设置...")
                            side = "long" if decision["signal"] == "buy_to_enter" else "short"
                            sl_tp_result = set_stop_loss_take_profit(
                                exchange, 
                                symbol, 
                                decision["stop_loss_price"], 
                                decision["take_profit_price"], 
                                side,
                                dry_run=dry_run
                            )
                            
                            if sl_tp_result.get("success"):
                                log_state_update("✅ 止损止盈补充设置成功", {
                                    "止损价": f"${decision['stop_loss_price']:.6f}",
                                    "止盈价": f"${decision['take_profit_price']:.6f}"
                                })
                            else:
                                log_state_update("⚠️ 止损止盈设置失败", {
                                    "错误": sl_tp_result.get('error', 'Unknown error'),
                                    "警告": "仓位已开启但无止损保护！请手动设置止损"
                                }, level=logging.WARNING)
                    else:
                        logger.warning(f"⚠️ 未找到持仓 {symbol}，无法验证止损止盈")
                        
                except Exception as e:
                    logger.error(f"❌ 验证止损止盈时出错: {e}")
            
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

