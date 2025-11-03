import os
from typing import Union, Optional
from langchain_deepseek import ChatDeepSeek
from langchain_openai import ChatOpenAI
from langfuse.langchain import CallbackHandler
from common.log_handler import logger
from .schemas import TradingDecision, HoldDecision

DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")

def create_model(
    model_name: str = "deepseek-v3.1-terminus",
    temperature: float = 0.1,
    max_tokens: int = 12800,
    timeout: int = 300,  # 延长超时至 5 分钟
    max_retries: int = 2
) -> ChatDeepSeek:
    """
    创建模型实例

    Args:
        model_name: 模型名称
        temperature: 温度参数
        max_tokens: 最大token数
        timeout: 超时时间
        max_retries: 重试次数

    Returns:
        ChatOpenAI: 模型实例
    """
    # 创建模型实例
    model_name = "deepseek-v3.1-terminus"
    model = ChatDeepSeek(
            api_base=DEEPSEEK_BASE_URL,
            api_key=DEEPSEEK_API_KEY,
            model=model_name,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            max_retries=max_retries,
            streaming=False,  # 禁用流式输出以支持结构化输出
        )


    logger.info(f"✅ 创建Apt-Agents 模型实例: {model_name} (temperature={temperature})")

    return model



def create_structured_model(
    model_name: str = "deepseek-chat",
    temperature: float = 0.1,
    max_tokens: int = 12800,
    timeout: int = 300,
    max_retries: int = 2
) -> ChatOpenAI:
    """
    创建支持结构化输出的模型实例

    Args:
        model_name: 模型名称
        temperature: 温度参数
        max_tokens: 最大token数
        timeout: 超时时间
        max_retries: 重试次数

    Returns:
        ChatOpenAI: 配置了结构化输出的模型实例
    """
    base_model = create_model(
        model_name=model_name,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
        max_retries=max_retries
    )
    
    # 使用 with_structured_output 约束输出格式
    structured_model = base_model.with_structured_output(TradingDecision)
    
    logger.info("✅ 创建结构化输出模型实例")
    
    return structured_model

