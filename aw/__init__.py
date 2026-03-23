"""AW 业务封装层。"""

import importlib
from pathlib import Path
from typing import List, Type

from aw.base_aw import BaseAW


def get_platform_aw_classes(platform: str) -> List[Type[BaseAW]]:
    """获取指定平台或公共的 AW 类列表。

    自动发现并导入 {platform}/*_aw.py 文件中的 AW 类。

    Args:
        platform: 平台名称，如 windows、web、ios、android、mac、common。

    Returns:
        该平台下所有 AW 类的列表。
    """
    aw_classes: List[Type[BaseAW]] = []
    platform_dir = Path(__file__).parent / platform

    if not platform_dir.exists():
        return aw_classes

    # 遍历 *_aw.py 文件
    for aw_file in platform_dir.glob("*_aw.py"):
        module_name = f"aw.{platform}.{aw_file.stem}"
        try:
            module = importlib.import_module(module_name)
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (
                    isinstance(attr, type)
                    and issubclass(attr, BaseAW)
                    and attr is not BaseAW
                ):
                    aw_classes.append(attr)
        except ImportError:
            continue

    return aw_classes