# Money-Agent/graph.py
import numpy as np
from Money_Agent.state import AgentState
from common.log_handler import logger, log_state_update


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
