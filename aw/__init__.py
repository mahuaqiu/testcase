"""AW 业务封装层。"""

from typing import List, Type
from aw.base_aw import BaseAW


def get_platform_aw_classes(platform: str) -> List[Type[BaseAW]]:
    """获取指定平台的 AW 类列表。

    Args:
        platform: 平台名称，如 windows、web、ios、android、mac。

    Returns:
        该平台下所有 AW 类的列表。
    """
    aw_classes = []

    try:
        platform_module = __import__(f"aw.{platform}", fromlist=[""])
        for attr_name in dir(platform_module):
            attr = getattr(platform_module, attr_name)
            if isinstance(attr, type) and issubclass(attr, BaseAW) and attr is not BaseAW:
                aw_classes.append(attr)
    except ImportError:
        pass

    return aw_classes