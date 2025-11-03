#!/usr/bin/env python3
"""
AI Money Agent - 基于 nof1.ai 的加密货币交易 Agent
使用 Bitget 交易所和结构化输出
"""

import time
import argparse
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

from Money_Agent.workflow import create_trading_workflow, initialize_agent_state, run_trading_cycle
from Money_Agent.database import get_database
from common.log_handler import logger, log_system_event, log_state_update

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="AI Money Agent - 加密货币交易机器人")
    parser.add_argument("--cycles", type=int, default=5, help="运行的交易周期数 (默认: 5, 设为 0 表示无限运行)")
    parser.add_argument("--interval", type=int, default=180, help="交易周期间隔秒数 (默认: 180)")
    parser.add_argument("--dry-run", action="store_true", help="模拟运行，不执行实际交易")
    parser.add_argument("--clear-cache-interval", type=int, default=10, help="每N个周期清空一次缓存 (默认: 10)")
    
    args = parser.parse_args()
    
    # 导入缓存清理函数
    from Money_Agent.tools.exchange_data_tool import clear_market_data_cache
    
    run_mode = "无限运行 (7×24)" if args.cycles == 0 else f"{args.cycles} 个周期"
    log_system_event("🚀 启动 AI Money Agent", {
        "运行模式": run_mode,
        "间隔": f"{args.interval}秒",
        "模拟运行": args.dry_run,
        "缓存清理间隔": f"每 {args.clear_cache_interval} 个周期"
    })
    
    try:
        # 初始化数据库（在程序启动时）
        db = get_database()
        log_system_event("✅ 数据库初始化完成", f"路径: {db.db_path}")
        
        # 创建工作流
        app = create_trading_workflow()
        
        # 初始化状态（传递 dry_run 参数）
        state = initialize_agent_state(dry_run=args.dry_run)
        
        # 判断运行模式
        if args.cycles == 0:
            # 无限运行模式 (7×24)
            log_system_event("🔄 进入无限运行模式", "按 Ctrl+C 停止")
            cycle = 0
            
            while True:
                log_system_event(f"🔄 交易周期 {cycle + 1}", "开始执行")
                
                # 运行一个完整的交易周期
                state = run_trading_cycle(app, state)
                
                # 显示当前状态
                log_state_update("周期完成", {
                    "周期编号": cycle + 1,
                    "账户价值": f"${state['account_info']['account_value']:.6f}",
                    "收益率": f"{state['account_info']['return_pct']:.6f}%",
                    "夏普比率": f"{state['account_info']['sharpe_ratio']:.6f}",
                    "持仓数量": len(state['positions']),
                    "总交易次数": len(state.get('trade_history', []))
                })
                
                # 每 N 个周期清空缓存
                if (cycle + 1) % args.clear_cache_interval == 0:
                    log_system_event("🧹 清理市场数据缓存", f"已完成 {cycle + 1} 个周期")
                    clear_market_data_cache()
                
                # 等待下一个周期
                log_system_event(f"⏰ 等待下一周期", f"{args.interval} 秒")
                time.sleep(args.interval)
                cycle += 1
        else:
            # 有限次数运行模式
            for cycle in range(args.cycles):
                log_system_event(f"🔄 交易周期 {cycle + 1}/{args.cycles}", "开始执行")
                
                # 运行一个完整的交易周期
                state = run_trading_cycle(app, state)
                
                # 显示当前状态
                log_state_update("周期完成", {
                    "账户价值": f"${state['account_info']['account_value']:.6f}",
                    "收益率": f"{state['account_info']['return_pct']:.6f}%",
                    "夏普比率": f"{state['account_info']['sharpe_ratio']:.6f}",
                    "持仓数量": len(state['positions'])
                })
                
                # 每 N 个周期清空缓存
                if (cycle + 1) % args.clear_cache_interval == 0:
                    log_system_event("🧹 清理市场数据缓存", f"已完成 {cycle + 1}/{args.cycles} 个周期")
                    clear_market_data_cache()
                
                # 如果不是最后一个周期，等待下一个周期
                if cycle < args.cycles - 1:
                    log_system_event(f"⏰ 等待下一周期", f"{args.interval} 秒")
                    time.sleep(args.interval)
            
    except KeyboardInterrupt:
        log_system_event("👋 用户中断", "正在安全退出...")
        
        # 显示最终统计
        if 'state' in locals() and 'cycle' in locals():
            log_state_update("📊 最终统计", {
                "运行模式": "无限运行" if args.cycles == 0 else f"有限运行 ({args.cycles} 周期)",
                "完成周期数": cycle + 1 if args.cycles == 0 else min(cycle + 1, args.cycles),
                "最终账户价值": f"${state['account_info']['account_value']:.6f}",
                "总收益率": f"{state['account_info']['return_pct']:.6f}%",
                "夏普比率": f"{state['account_info']['sharpe_ratio']:.6f}",
                "总交易次数": len(state.get('trade_history', [])),
                "运行时长": f"{state['minutes_elapsed']} 分钟"
            })
                
    except Exception as e:
        logger.error(f"❌ 运行错误: {e}")
        raise
        
    finally:
        log_system_event("🏁 AI Money Agent 已停止", "")

if __name__ == "__main__":
    main()