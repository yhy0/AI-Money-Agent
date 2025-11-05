"""
交易决策的结构化输出模式定义
"""
from typing import Literal
from pydantic import BaseModel, Field, model_validator

class TradingDecision(BaseModel):
    """交易决策的结构化输出模式"""
    
    signal: Literal["buy_to_enter", "sell_to_enter", "hold", "close"] = Field(
        description="交易信号：买入开仓、卖出开仓、持有、平仓"
    )
    
    # 注意：Literal 类型必须硬编码，无法从配置动态生成
    # 如需添加新币种，请同时更新 Money_Agent/config.py 中的 ALL_SUPPORTED_COINS
    coin: Literal["BTC", "ETH", "SOL", "BNB", "BGB", "DOGE", "SUI", "LTC"] = Field(
        description="交易的加密货币符号"
    )
    
    quantity: float = Field(
        ge=0,
        description="交易数量（币的数量）"
    )
    
    leverage: int = Field(
        ge=1,
        le=20,
        description="杠杆倍数，范围 1-20"
    )
    
    take_profit_price: float = Field(
        ge=0,
        description="止盈价格目标"
    )
    
    stop_loss_price: float = Field(
        ge=0,
        description="止损价格"
    )
    
    invalidation_condition: str = Field(
        max_length=200,
        description="交易论点失效的具体条件"
    )
    
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="对此次交易的信心水平，范围 0-1"
    )
    
    risk_usd: float = Field(
        ge=0,
        description="此次交易的美元风险敞口"
    )
    
    justification: str = Field(
        max_length=800,
        description="交易决策的详细理由"
    )

    @model_validator(mode='after')
    def validate_decision(self):
        """验证整个决策的一致性"""
        # hold 信号的验证
        if self.signal == 'hold':
            # hold 信号允许价格为 0
            if self.take_profit_price is None:
                self.take_profit_price = 0.0
            if self.stop_loss_price is None:
                self.stop_loss_price = 0.0
            # 持有信号时数量必须为0
            if self.quantity != 0:
                self.quantity = 0.0
            # 持有时设置默认杠杆为1
            if self.leverage != 1:
                self.leverage = 1
        else:
            # 开仓信号的验证（仅对开仓强制要求有效止盈止损）
            if self.signal in ['buy_to_enter', 'sell_to_enter']:
                # 价格必须大于 0
                if self.take_profit_price <= 0:
                    raise ValueError(f"开仓信号时止盈价格必须大于0，当前值: {self.take_profit_price}")
                if self.stop_loss_price <= 0:
                    raise ValueError(f"开仓信号时止损价格必须大于0，当前值: {self.stop_loss_price}")
                # 开仓信号时数量必须大于0
                if self.quantity <= 0:
                    raise ValueError(f"开仓信号时数量必须大于0，当前值: {self.quantity}")
            elif self.signal == 'close':
                # 平仓信号不强制要求止盈/止损；将缺省值归零，防止上游校验错误
                if self.take_profit_price is None:
                    self.take_profit_price = 0.0
                if self.stop_loss_price is None:
                    self.stop_loss_price = 0.0
        
        return self

    class Config:
        """Pydantic 配置"""
        json_schema_extra = {
            "example": {
                "signal": "buy_to_enter",
                "coin": "BTC",
                "quantity": 0.1,
                "leverage": 5,
                "take_profit_price": 105000.0,
                "stop_loss_price": 95000.0,
                "invalidation_condition": "BTC breaks below $95,000 support",
                "confidence": 0.75,
                "risk_usd": 500.0,
                "justification": "Strong bullish momentum with RSI oversold bounce and volume confirmation"
            }
        }


class HoldDecision(BaseModel):
    """持有决策的简化模式"""
    
    signal: Literal["hold"] = Field(default="hold")
    coin: str = Field(default="")
    quantity: float = Field(default=0.0)
    leverage: int = Field(default=1)
    take_profit_price: float = Field(default=0.0)
    stop_loss_price: float = Field(default=0.0)
    invalidation_condition: str = Field(default="N/A")
    confidence: float = Field(default=0.0)
    risk_usd: float = Field(default=0.0)
    justification: str = Field(description="持有决策的理由")