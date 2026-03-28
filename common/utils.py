"""
工具函数。

提供通用的工具方法。
"""

import base64
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


def wait_for(condition: callable, timeout: int = 10, interval: float = 0.5) -> bool:
    """等待条件满足。

    Args:
        condition: 条件函数，返回 bool。
        timeout: 超时时间（秒）。
        interval: 检查间隔（秒）。

    Returns:
        条件是否在超时前满足。
    """
    start = time.time()
    while time.time() - start < timeout:
        if condition():
            return True
        time.sleep(interval)
    return False


def retry(
    func: callable,
    max_retries: int = 3,
    interval: float = 1.0,
    exceptions: tuple = (Exception,),
) -> Any:
    """重试执行函数。

    Args:
        func: 要执行的函数。
        max_retries: 最大重试次数。
        interval: 重试间隔（秒）。
        exceptions: 需要重试的异常类型。

    Returns:
        函数执行结果。

    Raises:
        最后一次执行的异常。
    """
    last_error = None
    for i in range(max_retries):
        try:
            return func()
        except exceptions as e:
            last_error = e
            if i < max_retries - 1:
                time.sleep(interval)
    raise last_error


def timestamp(fmt: str = "%Y%m%d_%H%M%S") -> str:
    """获取当前时间戳字符串。

    Args:
        fmt: 时间格式。

    Returns:
        格式化的时间戳。
    """
    return datetime.now().strftime(fmt)


def ensure_dir(path: str) -> Path:
    """确保目录存在，不存在则创建。

    Args:
        path: 目录路径。

    Returns:
        Path 对象。
    """
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def load_json(file_path: str) -> Dict[str, Any]:
    """加载 JSON 文件。

    Args:
        file_path: 文件路径。

    Returns:
        JSON 数据。
    """
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(data: Dict[str, Any], file_path: str) -> None:
    """保存 JSON 文件。

    Args:
        data: 要保存的数据。
        file_path: 文件路径。
    """
    ensure_dir(str(Path(file_path).parent))
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def truncate_string(s: str, max_length: int = 100, suffix: str = "...") -> str:
    """截断字符串。

    Args:
        s: 原字符串。
        max_length: 最大长度。
        suffix: 截断后缀。

    Returns:
        截断后的字符串。
    """
    if len(s) <= max_length:
        return s
    return s[: max_length - len(suffix)] + suffix


def get_project_root() -> Path:
    """获取项目根目录。

    Returns:
        项目根目录的 Path 对象。
    """
    # common 目录的父目录即为项目根目录
    return Path(__file__).parent.parent


def load_image_as_base64(image_path: str) -> Optional[str]:
    """将本地图片转换为 base64 编码。

    Args:
        image_path: 图片路径（相对或绝对）。
            相对路径基于项目根目录解析。

    Returns:
        base64 编码的图片内容，如果文件不存在则返回 None。
    """
    if os.path.isabs(image_path):
        full_path = image_path
    else:
        full_path = get_project_root() / image_path

    if os.path.exists(full_path):
        with open(full_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    return None