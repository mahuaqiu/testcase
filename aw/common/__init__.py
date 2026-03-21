"""公共 AW 模块。"""

from typing import List, Type
from aw.base_aw import BaseAW


def get_aw_classes() -> List[Type[BaseAW]]:
    """获取公共 AW 类列表。"""
    try:
        from aw.common.check_aw import CheckAW
        return [CheckAW]
    except ImportError:
        return []