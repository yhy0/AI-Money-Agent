
# Money-Agent/state.py
from typing import TypedDict, List, Dict, Any

class AgentState(TypedDict):
    # 运行的分钟数
    minutes_elapsed: int
    # 市场数据 (格式化为字符串，给 LLM 使用)
    market_data: str
    # 结构化的市场数据 (用于内部逻辑，如趋势验证)
    structured_market_data: Dict[str, Any]
    # 当前持仓
    positions: List[Dict[str, Any]]
    # 账户信息
    account_info: Dict[str, Any]
    # Agent 的决策
    decision: Dict[str, Any]
    # 交易历史
    trade_history: List[Dict[str, Any]]
    # 模拟运行模式（不执行实际交易）
    dry_run: bool
    # 当前允许交易的币种列表（低资金模式限制）
    active_trading_coins: List[str]
    # 是否处于低资金模式（内部状态标志）
    _low_equity_mode: bool
    # 低资金模式日志是否已记录（避免重复日志）
    _low_equity_mode_logged: bool
