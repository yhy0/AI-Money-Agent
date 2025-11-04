import json
import logging
import os
import sys
import textwrap
from typing import Any, Optional

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

logger = logging.getLogger("MoneyAgent")
logger.setLevel(logging.INFO)
logger.handlers.clear()
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
logger.addHandler(handler)
logger.propagate = False


RESET = "\033[0m"
CATEGORY_STYLES = {
    "LLM": "\033[95m",      # 紫色
    "TOOL": "\033[96m",     # 青色
    "STATE": "\033[92m",    # 绿色
    "SECURITY": "\033[93m", # 黄色
    "SYSTEM": "\033[94m",   # 蓝色
    "CRITICAL": "\033[91m", # 红色（重点标记）
}


def _supports_color() -> bool:
    """检测当前终端是否支持彩色输出。
    
    支持以下方式启用颜色：
    1. 环境变量 FORCE_COLOR=1 或 FORCE_COLOR=true
    2. 环境变量 NO_COLOR 未设置且 stdout 是 tty
    """
    # 1. 检查是否强制禁用颜色
    if os.getenv('NO_COLOR'):
        return False
    
    # 2. 检查是否强制启用颜色（用于 tee、less -R 等场景）
    force_color = os.getenv('FORCE_COLOR', '').lower()
    if force_color in ('1', 'true', 'yes'):
        return True
    
    # 3. 默认检测 tty
    return sys.stdout.isatty()


_COLOR_ENABLED = _supports_color()


def _apply_style(style: str, text: str) -> str:
    """应用颜色样式到文本。"""
    if not _COLOR_ENABLED or not style:
        return text
    return f"{style}{text}{RESET}"


def _format_payload(payload: Any) -> Optional[str]:
    if not payload:
        return None
    if isinstance(payload, (dict, list)):
        text = json.dumps(payload, ensure_ascii=False, indent=2)
    else:
        text = str(payload)
    return textwrap.indent(text, "  ")


def _log_with_category(category: str, title: str, payload: Any, *, level: int) -> None:
    """记录带分类标签的日志。
    
    Args:
        category: 日志分类（LLM/TOOL/STATE/SECURITY/SYSTEM）
        title: 日志标题
        payload: 附加数据（可选）
        level: 日志级别
    """
    category_key = category.upper()
    style = CATEGORY_STYLES.get(category_key, "")
    
    # 🎨 将整行标题（包括标签和内容）都应用颜色
    full_title = f"[{category_key}] {title}"
    colored_title = _apply_style(style, full_title)
    
    message_lines = [colored_title]
    
    formatted_payload = _format_payload(payload)
    if formatted_payload:
        message_lines.append(formatted_payload)
    
    message = "\n".join(message_lines)
    logger.log(level, "%s", message)
    
    # 同时保存到数据库（避免循环导入，动态导入）
    try:
        from Money_Agent.database import get_database
        db = get_database()
        
        # 将日志级别转换为字符串
        level_name = logging.getLevelName(level)
        
        # 保存到数据库
        db.save_log(
            level=level_name,
            category=category_key,
            message=title,
            details=payload if isinstance(payload, dict) else None
        )
    except Exception:
        # 如果保存失败，静默忽略（避免影响主流程）
        pass

def log_agent_thought(title: str, payload: Any = None) -> None:
    """记录 LLM 的思考与输出。"""
    _log_with_category("LLM", title, payload, level=logging.INFO)


def log_tool_event(title: str, payload: Any = None, *, level: int = logging.INFO) -> None:
    """记录工具调用及其结果。"""
    _log_with_category("TOOL", title, payload, level=level)


def log_state_update(title: str, payload: Any = None, *, level: int = logging.INFO) -> None:
    """记录状态更新或关键结论。"""
    _log_with_category("STATE", title, payload, level=level)


def log_security_event(title: str, payload: Any = None, *, level: int = logging.INFO) -> None:
    """记录安全审查相关的消息。"""
    _log_with_category("SECURITY", title, payload, level=level)


def log_system_event(title: str, payload: Any = None, *, level: int = logging.INFO) -> None:
    """记录系统级别的提示，如初始化等。"""
    _log_with_category("SYSTEM", title, payload, level=level)


def log_critical_event(title: str, payload: Any = None, *, level: int = logging.WARNING) -> None:
    """记录重点标记的事件（红色高亮）。"""
    _log_with_category("CRITICAL", title, payload, level=level)
