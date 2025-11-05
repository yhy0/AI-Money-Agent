"""
异步交易数据获取与分析测试脚本（最终版）

调用 trade_history_analyzer 模块，分别获取并展示
为用户设计的报告和为 LLM 设计的结构化数据。
"""

import asyncio
import time
import json
from dotenv import load_dotenv
from Money_Agent.tools.exchange_data_tool import get_exchange, validate_api_credentials
from Money_Agent.tools.trade_history_analyzer import generate_user_report, generate_llm_data
from common.log_handler import logger, log_system_event, log_state_update


# 加载环境变量
load_dotenv()

def print_separator(title="", char="=", width=100):
    """打印分隔线"""
    if title:
        print(f"\n{char * width}")
        print(f"{title:^{width}}")
        print(f"{char * width}")
    else:
        print(f"{char * width}")


async def main():
    """主函数"""
    print_separator("🧪 交易历史分析测试", "=")
    
    exchange = get_exchange()
    
    if not validate_api_credentials(exchange):
        logger.warning("⚠️ API凭据验证失败，无法获取真实数据")
        return
    
    start_time = time.time()
    
    # 1. 生成并展示为用户准备的 Markdown 报告
    logger.info("\n📥 正在生成用户交易分析报告...")
    markdown_report = await generate_user_report(exchange)

    # 2. 生成并展示为 LLM 准备的 JSON 数据
    logger.info("\n📥 正在生成LLM结构化数据...")
    llm_data = await generate_llm_data(exchange)

    print_separator("🤖 LLM 结构化数据 (JSON)", "-")
    if llm_data:
        print(json.dumps(llm_data, indent=2, ensure_ascii=False))
    else:
        print("无交易数据")

    elapsed_time = time.time() - start_time
    logger.info(f"\n✅ 分析完成，总耗时: {elapsed_time:.2f} 秒")

if __name__ == "__main__":
    asyncio.run(main())