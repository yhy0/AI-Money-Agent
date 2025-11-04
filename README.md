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