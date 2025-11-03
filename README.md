# AI Money Agent

基于 nof1.ai Alpha Arena 的加密货币交易 Agent 复刻版本，使用 Bitget 交易所和结构化输出。

## ✨ 特性

- 🤖 **智能决策**: 基于 DeepSeek 大语言模型的自主交易决策
- 📊 **实时分析**: 集成 Bitget 交易所实时市场数据分析
- 🔄 **工作流管理**: 使用 LangGraph 构建完整的交易工作流
- 💰 **风险控制**: 完整的风险管理和头寸控制系统
- 📈 **技术指标**: 支持 RSI、MACD、EMA 等多种技术指标
- 🎯 **结构化输出**: 使用 `with_structured_output` 确保决策格式一致性
- 🏦 **真实交易**: 支持 Bitget 永续合约实盘交易

## 🚀 快速开始

### 环境要求

- Python 3.8+
- uv (推荐) 或 pip

### 安装

```bash
# 克隆项目
git clone <repository-url>
cd AI-Money-Agent

# 使用 uv 安装依赖
uv sync

# 或使用 pip
pip install -e .
```

### 配置

1. 复制环境变量模板：
```bash
cp .env.example .env
```

2. 编辑 `.env` 文件，填入你的 API 密钥：
```env
# DeepSeek API 配置
DEEPSEEK_BASE_URL=https://api.lkeap.cloud.tencent.com/v1
DEEPSEEK_API_KEY=your_deepseek_api_key_here

# Bitget 交易所 API 配置
BITGET_API_KEY=your_bitget_api_key_here
BITGET_SECRET=your_bitget_secret_here
BITGET_PASSPHRASE=your_bitget_passphrase_here

# 是否使用沙盒环境
BITGET_SANDBOX=true

# 交易币种配置（逗号分隔，不要有空格）
TRADING_COINS=BTC,ETH,SOL
```

3. **配置交易币种**（可选）：

默认交易 BTC、ETH、SOL 三个币种。如需修改，编辑 `.env` 中的 `TRADING_COINS`：

```bash
# 只交易 BTC
TRADING_COINS=BTC

# 交易 BTC 和 ETH
TRADING_COINS=BTC,ETH

# 交易所有支持的币种
TRADING_COINS=BTC,ETH,SOL,BGB,DOGE,SUI,LTC
```

支持的币种：BTC, ETH, SOL, BGB, DOGE, SUI, LTC

详细配置说明请查看 [COINS_CONFIG.md](COINS_CONFIG.md)
```

### 运行

```bash
# 基本运行（5个周期，3分钟间隔）
python main.py

# 自定义参数运行
python main.py --cycles 10 --interval 300

# 模拟运行（不执行实际交易）
python main.py --dry-run

# 测试单个周期
python -c "from main import test_single_cycle; test_single_cycle()"
```

## 📁 项目结构

```
AI-Money-Agent/
├── Money_Agent/                    # 核心 Agent 代码
│   ├── __init__.py
│   ├── state.py                   # 状态定义
│   ├── schemas.py                 # 结构化输出模式
│   ├── prompts.py                 # 提示词模板
│   ├── model.py                   # 模型配置
│   ├── graph.py                   # 图节点函数
│   ├── workflow.py                # 完整工作流
│   └── tools/                     # 工具模块
│       └── exchange_data_tool.py  # 交易所数据工具
├── common/                        # 公共工具
│   ├── __init__.py
│   └── logger.py                 # 日志配置
├── main.py                       # 主程序入口
├── pyproject.toml               # 项目配置
├── .env.example                 # 环境变量模板
└── README.md                    # 项目文档
```

## 🔧 核心组件

### 1. 结构化输出 (`schemas.py`)
使用 Pydantic 定义严格的交易决策输出格式：
```python
class TradingDecision(BaseModel):
    signal: Literal["buy_to_enter", "sell_to_enter", "hold", "close"]
    coin: Literal["BTC", "ETH", "SOL", "BNB", "DOGE", "XRP"]
    quantity: float
    leverage: int
    profit_target: float
    stop_loss: float
    # ... 更多字段
```

### 2. 智能模型 (`model.py`)
- 集成 DeepSeek 大语言模型
- 支持 `with_structured_output` 约束输出格式
- 自动重试和错误处理

### 3. 交易所集成 (`exchange_data_tool.py`)
- **Bitget 永续合约**: 完整的 API 集成
- **实时数据**: 价格、技术指标、资金费率
- **交易执行**: 开仓、平仓、止损止盈
- **账户管理**: 余额查询、持仓管理

### 4. 工作流引擎 (`workflow.py`)
使用 LangGraph 构建完整的交易工作流：
```
更新市场数据 → 获取AI决策 → 执行交易 → 计算性能 → 结束
```

### 5. 提示词工程 (`prompts.py`)
基于 nof1.ai 逆向工程的完整提示词，包括：
- 🎯 **角色定义**: 专业交易 Agent 身份
- 📋 **交易规则**: 完整的交易环境规范
- ⚠️ **风险管理**: 强制性风险控制协议
- 📊 **输出格式**: 严格的 JSON 输出约束

## 📊 支持的交易对

- **BTC/USDT**: 比特币永续合约
- **ETH/USDT**: 以太坊永续合约  
- **SOL/USDT**: Solana永续合约
- **BGB/USDT**: BGB永续合约
- **DOGE/USDT**: 狗狗币永续合约

## 🛡️ 风险管理

### 内置风险控制
- ✅ **强制止损止盈**: 每笔交易必须设置
- ✅ **头寸规模限制**: 基于信心度动态调整
- ✅ **杠杆控制**: 1-20x 杠杆范围
- ✅ **清算风险**: 确保清算价格距离 >15%
- ✅ **资金管理**: 单笔交易风险 <3% 账户价值

### 性能监控
- 📈 **实时收益率**: 动态计算账户表现
- 📊 **夏普比率**: 风险调整后收益评估
- 📋 **交易历史**: 完整的交易记录追踪

## 🧪 测试和开发

```bash
# 运行系统测试
uv run python test_system.py

# 测试交易所连接
uv run python Money_Agent/tools/exchange_data_tool.py

# 测试单个交易周期
uv run python -c "from main import test_single_cycle; test_single_cycle()"

# 测试离线行为
uv run python test_offline.py

# 调试模式运行
LOG_LEVEL=DEBUG uv run python main.py --cycles 1
```

## 🔄 与原版 nof1.ai 的差异

| 特性 | nof1.ai | 本项目 |
|------|---------|--------|
| 交易所 | BitGet | Bitget |
| 输出格式 | JSON 字符串解析 | 结构化输出 |
| 工作流 | 未知 | LangGraph |
| 风险管理 | 内置 | 完整实现 |
| 开源程度 | 闭源 | 完全开源 |

## ⚠️ 风险声明

**重要提醒**：
- 本项目仅供学习和研究使用
- 加密货币交易存在极高风险，可能导致全部资金损失
- 请务必先在沙盒环境中充分测试
- 实盘交易前请确保充分理解所有风险
- 作者不对任何交易损失承担责任

## 📄 许可证

MIT License - 详见 [LICENSE](LICENSE) 文件

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

### 贡献指南
1. Fork 本项目
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

## 📞 支持

如有问题，请：
1. 查看 [Issues](../../issues) 中的已知问题
2. 创建新的 Issue 描述问题
3. 参考项目文档和代码注释