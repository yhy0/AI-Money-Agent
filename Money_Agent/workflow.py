"""
AI Money Agent 的完整工作流定义
"""
import asyncio
from langgraph.graph import StateGraph, END
from langfuse.langchain import CallbackHandler
from Money_Agent.state import AgentState
from Money_Agent.graph import (
    get_agent_decision,
    execute_trade,
)
from Money_Agent.tools.exchange import exchange
from Money_Agent.utils.market import update_market_data
from Money_Agent.utils.performance import calculate_performance_metrics
# 新增导入
from Money_Agent.tools.trade_history_analyzer import generate_llm_data
from Money_Agent.database import get_database
from common.log_handler import logger, log_system_event

# --- 新增节点函数 ---
def update_historical_analysis(state: AgentState) -> AgentState:
    """获取历史交易分析并更新状态（同步包装）"""
    logger.info("📥 正在更新历史交易分析...")
    # 使用 asyncio.run 在同步函数中调用异步函数
    analysis_data = asyncio.run(generate_llm_data(exchange))
    state['historical_analysis'] = analysis_data
    logger.info("✅ 历史交易分析更新完毕")
    return state


def create_trading_workflow():
    """创建交易工作流（带 Langfuse 监控）"""
    
    workflow = StateGraph(AgentState)
    
    # 添加所有节点，包括新的分析节点
    workflow.add_node("update_market_data", update_market_data)
    workflow.add_node("update_historical_analysis", update_historical_analysis) # 新节点
    workflow.add_node("get_agent_decision", get_agent_decision)
    workflow.add_node("execute_trade", execute_trade)
    workflow.add_node("calculate_performance", calculate_performance_metrics)
    
    # 定义新的工作流路径
    workflow.set_entry_point("update_market_data")
    workflow.add_edge("update_market_data", "update_historical_analysis") # 先更新市场数据
    workflow.add_edge("update_historical_analysis", "get_agent_decision") # 然后更新历史分析，再交给 LLM
    workflow.add_edge("get_agent_decision", "execute_trade")
    workflow.add_edge("execute_trade", "calculate_performance")
    workflow.add_edge("calculate_performance", END)
    
    try:
        langfuse_handler = CallbackHandler()
        app = workflow.compile().with_config({"callbacks": [langfuse_handler]})
        log_system_event("✅ 交易工作流创建完成, 已启用 Langfuse 监控", {})
    except Exception as e:
        logger.warning(f"⚠️ Langfuse 初始化失败，使用无监控模式: {e}")
        app = workflow.compile()
        log_system_event("✅ 交易工作流创建完成, 无监控模式", {})
    
    return app


def run_trading_cycle(app, state: AgentState) -> AgentState:
    """运行一个完整的交易周期"""
    try:
        cycle_num = state['minutes_elapsed']//3 + 1
        log_system_event(f"🚀 开始交易周期 第 {cycle_num} 轮", {})
        
        result = app.invoke(state)
        
        db = get_database()
        db.save_account_snapshot(result['account_info'])
        if result.get('positions'):
            db.save_positions(result['positions'])
        if result.get('decision'):
            db.save_decision(cycle_num, result['decision'])
        if result.get('decision', {}).get('signal') not in ['hold', None]:
            db.save_trade(cycle_num, result['decision'])
        
        log_system_event(f"✅ 交易周期完成,数据已保存到数据库", {})
        return result
        
    except Exception as e:
        logger.error(f"❌ 交易周期执行失败: {e}")
        return state


def initialize_agent_state(dry_run: bool = False) -> AgentState:
    """初始化 Agent 状态"""
    return {
        "minutes_elapsed": 0,
        "market_data": "",
        "structured_market_data": {},
        "decision": {},
        "positions": [],
        "account_info": {
            "cash_available": 3.0,
            "account_value": 3.0,
            "return_pct": 0.0,
            "sharpe_ratio": 0.0,
        },
        "historical_analysis": {}, # 初始化新字段
        "trade_history": [],
        "dry_run": dry_run,
        "active_trading_coins": [],
        "_low_equity_mode": False,
        "_low_equity_mode_logged": False
    }


if __name__ == "__main__":
    app = create_trading_workflow()
    state = initialize_agent_state(dry_run=True)
    result = run_trading_cycle(app, state)
    
    print("=== 交易结果 ===")
    print(f"模拟模式: {result.get('dry_run', False)}")
    print(f"决策: {result['decision']}")
    print(f"账户信息: {result['account_info']}")
    print(f"持仓: {result['positions']}")
