"""Web AW 模块。"""

from typing import List, Type
from aw.base_aw import BaseAW


def get_aw_classes() -> List[Type[BaseAW]]:
    """获取 Web 平台 AW 类列表。"""
    from aw.web.login_aw import LoginAW
    return [LoginAW]