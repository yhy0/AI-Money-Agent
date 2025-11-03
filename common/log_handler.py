import json
import logging
import sys
import textwrap
from typing import Any, Optional

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

logger = logging.getLogger("MoneyAgent")
logger.setLevel(logging.INFO)
logger.handlers.clear()
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
logger.addHandler(handler)
logger.propagate = False


RESET = "\033[0m"
CATEGORY_STYLES = {
    "LLM": "\033[95m",
    "TOOL": "\033[96m",
    "STATE": "\033[92m",
    "SECURITY": "\033[93m",
    "SYSTEM": "\033[94m",
}
LEVEL_STYLES = {
    "DEBUG": "\033[37m",
    "INFO": "\033[97m",
    "WARNING": "\033[93m",
    "ERROR": "\033[91m",
    "CRITICAL": "\033[41m",
}


def _supports_color() -> bool:
    """检测当前终端是否支持彩色输出。"""
    return sys.stdout.isatty()


_COLOR_ENABLED = _supports_color()


def _apply_style(style: str, text: str) -> str:
    if not _COLOR_ENABLED or not style:
        return text
    return f"{style}{text}{RESET}"


def _format_payload(payload: Any) -> Optional[str]:
    if payload is None:
        return None
    if isinstance(payload, (dict, list)):
        text = json.dumps(payload, ensure_ascii=False, indent=2)
    else:
        text = str(payload)
    return textwrap.indent(text, "  ")


def _log_with_category(category: str, title: str, payload: Any, *, level: int, cluster_id: Optional[int] = None) -> None:
    category_key = category.upper()
    style = CATEGORY_STYLES.get(category_key, "")
    label = _apply_style(style, f"[{category_key}]")
    
    # 如果提供了 cluster_id，添加到标签中
    if cluster_id is not None:
        cluster_label = _apply_style("\033[93m", f"[聚类 {cluster_id}]")  # 黄色
        message_lines = [f"{label} {cluster_label} {title}"]
    else:
        message_lines = [f"{label} {title}"]
    
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

def log_agent_thought(title: str, payload: Any = None, cluster_id: Optional[int] = None) -> None:
    """记录LLM的思考与输出。"""
    _log_with_category("LLM", title, payload, level=logging.INFO, cluster_id=cluster_id)

def log_tool_event(title: str, payload: Any = None, *, level: int = logging.INFO, cluster_id: Optional[int] = None) -> None:
    """记录工具调用及其结果。"""
    _log_with_category("TOOL", title, payload, level=level, cluster_id=cluster_id)

def log_state_update(title: str, payload: Any = None, *, level: int = logging.INFO, cluster_id: Optional[int] = None) -> None:
    """记录状态更新或关键结论。"""
    _log_with_category("STATE", title, payload, level=level, cluster_id=cluster_id)

def log_security_event(title: str, payload: Any = None, *, level: int = logging.INFO, cluster_id: Optional[int] = None) -> None:
    """记录安全审查相关的消息。"""
    _log_with_category("SECURITY", title, payload, level=level, cluster_id=cluster_id)

def log_system_event(title: str, payload: Any = None, *, level: int = logging.INFO, cluster_id: Optional[int] = None) -> None:
    """记录系统级别的提示，如初始化等。"""
    _log_with_category("SYSTEM", title, payload, level=level, cluster_id=cluster_id)
