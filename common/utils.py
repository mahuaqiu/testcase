"""
工具函数。

提供通用的工具方法。
"""

import base64
import difflib
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


def find_similar_templates(image_path: str, images_root: Path, max_n: int = 3) -> list:
    """在 images_root 下找与 image_path 最相近的模板文件。

    Args:
        image_path: 目标图片路径（取文件名做相近度匹配）。
        images_root: 模板根目录（通常是 <项目根>/images）。
        max_n: 最多返回条数。

    Returns:
        list[str]: 形如 "images/web/摄像头_关闭.png（相似 0.91）" 的提示列表。
    """
    if not images_root.exists():
        return []
    name = os.path.basename(image_path)
    stem = os.path.splitext(name)[0]
    candidates = [
        str(p.relative_to(images_root))
        for p in images_root.rglob("*")
        if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".bmp")
    ]
    if not candidates:
        return []
    basenames = [os.path.basename(c) for c in candidates]
    close = difflib.get_close_matches(name, basenames, n=max_n, cutoff=0.6)
    result = []
    for m in close:
        for rel in candidates:
            if os.path.basename(rel) == m:
                ratio = difflib.SequenceMatcher(None, stem, os.path.splitext(m)[0]).ratio()
                result.append(f"{rel}（相似 {ratio:.2f}）")
                break
    return result