"""
AI Money Agent 的完整工作流定义
"""
from langgraph.graph import StateGraph, END
from langfuse.langchain import CallbackHandler
from .state import AgentState
from .graph import (
    update_market_data,
    get_decision,
    execute_trade,
    calculate_performance_metrics
)
from .database import get_database
from common.log_handler import logger, log_system_event


def create_trading_workflow():
    """创建交易工作流（带 Langfuse 监控）"""
    
    # 创建状态图
    workflow = StateGraph(AgentState)
    
    # 添加节点
    workflow.add_node("update_market_data", update_market_data)
    workflow.add_node("get_decision", get_decision)
    workflow.add_node("execute_trade", execute_trade)
    workflow.add_node("calculate_performance", calculate_performance_metrics)
    
    # 定义工作流路径
    workflow.set_entry_point("update_market_data")
    
    workflow.add_edge("update_market_data", "get_decision")
    workflow.add_edge("get_decision", "execute_trade")
    workflow.add_edge("execute_trade", "calculate_performance")
    workflow.add_edge("calculate_performance", END)
    
    # 初始化 Langfuse CallbackHandler
    try:
        langfuse_handler = CallbackHandler()
        # 编译工作流并添加 Langfuse 回调（自动追踪整个图）
        app = workflow.compile().with_config({"callbacks": [langfuse_handler]})
        log_system_event("✅ 交易工作流创建完成", "已启用 Langfuse 监控")
    except Exception as e:
        logger.warning(f"⚠️ Langfuse 初始化失败，使用无监控模式: {e}")
        # 如果 Langfuse 初始化失败，使用普通编译
        app = workflow.compile()
        log_system_event("✅ 交易工作流创建完成", "无监控模式")
    
    return app


def run_trading_cycle(app, state: AgentState) -> AgentState:
    """运行一个完整的交易周期"""
    try:
        cycle_num = state['minutes_elapsed']//3 + 1
        log_system_event(f"🚀 开始交易周期", f"第 {cycle_num} 轮")
        
        # 执行工作流（Langfuse 会自动追踪整个流程）
        result = app.invoke(state)
        
        # 保存数据到数据库
        db = get_database()
        
        # 1. 保存账户快照
        db.save_account_snapshot(result['account_info'])
        
        # 2. 保存持仓
        if result.get('positions'):
            db.save_positions(result['positions'])
        
        # 3. 保存决策
        if result.get('decision'):
            db.save_decision(cycle_num, result['decision'])
        
        # 4. 保存交易记录（如果有交易）
        if result.get('decision', {}).get('signal') not in ['hold', None]:
            db.save_trade(cycle_num, result['decision'])
        
        log_system_event(f"✅ 交易周期完成", "数据已保存到数据库")
        return result
        
    except Exception as e:
        logger.error(f"❌ 交易周期执行失败: {e}")
        return state


def initialize_agent_state(dry_run: bool = False) -> AgentState:
    """初始化 Agent 状态
    
    Args:
        dry_run: 是否为模拟运行模式（不执行实际交易）
    """
    return {
        "minutes_elapsed": 0,
        "market_data": "",
        "decision": {},
        "positions": [],
        "account_info": {
            "cash_available": 3.0,
            "account_value": 3.0,
            "return_pct": 0.0,
            "sharpe_ratio": 0.0,
        },
        "trade_history": [],
        "dry_run": dry_run,
        "active_trading_coins": [],  # 将在 update_market_data 中根据账户权益设置
        "_low_equity_mode": False,  # 低资金模式标志
        "_low_equity_mode_logged": False  # 避免重复日志
    }


if __name__ == "__main__":
    # 测试工作流（默认使用模拟模式）
    app = create_trading_workflow()
    state = initialize_agent_state(dry_run=True)
    
    # 运行一个交易周期
    result = run_trading_cycle(app, state)
    
    print("=== 交易结果 ===")
    print(f"模拟模式: {result.get('dry_run', False)}")
    print(f"决策: {result['decision']}")
    print(f"账户信息: {result['account_info']}")
    print(f"持仓: {result['positions']}")