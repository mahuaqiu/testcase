"""
工具函数。

提供通用的工具方法。
"""

import base64
import os
from pathlib import Path
from typing import Optional

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