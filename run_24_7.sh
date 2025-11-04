#!/bin/bash
# 7×24 小时不间断运行脚本
# 使用方法: ./run_24_7.sh [--dry-run]

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}================================${NC}"
echo -e "${GREEN}AI Money Agent - 7×24 运行模式${NC}"
echo -e "${GREEN}================================${NC}"
echo ""

# ==================== 🔥 清理旧进程 ====================
echo -e "${YELLOW}🔍 检查并清理旧进程...${NC}"

# 查找并 kill main.py 进程
MAIN_PIDS=$(ps aux | grep "python main.py" | grep -v grep | awk '{print $2}')
if [ -n "$MAIN_PIDS" ]; then
    echo -e "${YELLOW}发现旧的 main.py 进程: $MAIN_PIDS${NC}"
    echo "$MAIN_PIDS" | xargs kill -9
    echo -e "${GREEN}✅ 已清理 main.py 进程${NC}"
else
    echo -e "${GREEN}✅ 没有发现旧的 main.py 进程${NC}"
fi

# 查找并 kill uvicorn 进程
UVICORN_PIDS=$(ps aux | grep "uvicorn server.main:app" | grep -v grep | awk '{print $2}')
if [ -n "$UVICORN_PIDS" ]; then
    echo -e "${YELLOW}发现旧的 uvicorn 进程: $UVICORN_PIDS${NC}"
    echo "$UVICORN_PIDS" | xargs kill -9
    echo -e "${GREEN}✅ 已清理 uvicorn 进程${NC}"
else
    echo -e "${GREEN}✅ 没有发现旧的 uvicorn 进程${NC}"
fi

# 等待进程完全退出
sleep 2
echo ""

echo ""
echo -e "${GREEN}启动参数:${NC}"
echo "  - 运行模式: 无限运行 (cycles=0)"
echo "  - 交易间隔: 180 秒 (3 分钟)"
echo "  - 缓存清理: 每 10 个周期"
echo ""

# 创建日志目录
LOG_DIR="logs"
mkdir -p $LOG_DIR

# 生成日志文件名
LOG_FILE="$LOG_DIR/trading.log"
WEB_LOG_FILE="$LOG_DIR/web.log"

echo -e "${GREEN}日志文件: $LOG_FILE${NC}"
echo -e "${GREEN}Server 日志文件: $WEB_LOG_FILE${NC}"
echo ""

# 启动交易机器人
echo -e "${GREEN}🚀 启动交易机器人...${NC}"
echo ""

# 🎨 强制启用颜色输出（用于 tee 和 tail 查看日志）
export FORCE_COLOR=1

# 使用 nohup 在后台运行（可选）
# nohup uv run python main.py --cycles 0 --interval 180 $DRY_RUN_FLAG > $LOG_FILE 2>&1 &
# 启动后端
nohup uv run uvicorn server.main:app --host 0.0.0.0 --port 80 > $WEB_LOG_FILE 2>&1 &
# 或者直接运行（推荐，可以看到实时日志）
uv run python main.py --cycles 0 --interval 120 --clear-cache-interval 10 2>&1 | tee $LOG_FILE

# 捕获退出状态
EXIT_CODE=$?

echo ""
echo -e "${YELLOW}================================${NC}"
echo -e "${YELLOW}交易机器人已停止${NC}"
echo -e "${YELLOW}退出代码: $EXIT_CODE${NC}"
echo -e "${YELLOW}日志已保存到: $LOG_FILE${NC}"
echo -e "${YELLOW}================================${NC}"

exit $EXIT_CODE
