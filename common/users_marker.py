"""users 标记语法解析。

支持 "{主平台}+{伴生平台}" 复合平台声明，如 "web+windows"：
主平台向资源平台申请，伴生平台复用主平台资源（同机器同 worker）。
"""

from pathlib import Path
from typing import Dict, Tuple

# 工程根目录下的 aw 目录（伴生平台必须存在对应 AW 目录）
_AW_ROOT = Path(__file__).resolve().parent.parent / "aw"


def parse_users_requirement(
    users_requirement: Dict[str, str],
) -> Tuple[Dict[str, str], Dict[str, str]]:
    """解析 users 标记声明，拆分主平台申请与伴生平台映射。

    Args:
        users_requirement: users 标记字典，如 {"userA": "web+windows"}。

    Returns:
        (platform_requests, companions) 二元组：
        - platform_requests: 传给资源平台的申请体，如 {"userA": "web"}
        - companions: 伴生映射，如 {"userA": "windows"}；无伴生为 {}

    Raises:
        ValueError: 声明非法（主平台为 api、伴生平台为 api、多伴生、
            显式声明的 "{user}_{platform}" 键与伴生键冲突）。
    """
    platform_requests: Dict[str, str] = {}
    companions: Dict[str, str] = {}

    for user_id, platform_spec in users_requirement.items():
        parts = str(platform_spec).split("+")
        if len(parts) > 2:
            raise ValueError(
                f"用户 '{user_id}' 平台声明 '{platform_spec}' 非法，"
                f"只支持 '{{主平台}}' 或 '{{主平台}}+{{伴生平台}}'"
            )
        main_platform = parts[0].strip()
        if not main_platform:
            raise ValueError(f"用户 '{user_id}' 主平台为空")
        if main_platform == "api":
            raise ValueError(
                f"用户 '{user_id}' 主平台不能是 api（api 用户由 UI 用户自动创建）"
            )
        platform_requests[user_id] = main_platform

        if len(parts) == 2:
            companion_platform = parts[1].strip()
            if not companion_platform:
                raise ValueError(f"用户 '{user_id}' 伴生平台为空")
            if companion_platform == "api":
                raise ValueError(
                    f"用户 '{user_id}' 伴生平台不能是 api"
                    f"（{user_id}_api 已自动创建，无需伴生）"
                )
            companion_id = f"{user_id}_{companion_platform}"
            if companion_id in users_requirement:
                raise ValueError(
                    f"伴生用户键 '{companion_id}' 与显式声明的用户冲突，"
                    f"请勿在 users 标记中同时声明 "
                    f"'{user_id}: {main_platform}+{companion_platform}' 和 '{companion_id}'"
                )
            companions[user_id] = companion_platform

    return platform_requests, companions


def validate_companion_platforms(companions: Dict[str, str]) -> None:
    """校验伴生平台存在对应 AW 目录。

    Args:
        companions: parse_users_requirement 返回的伴生映射。

    Raises:
        ValueError: 伴生平台没有对应 AW 目录。
    """
    for user_id, companion_platform in companions.items():
        if not (_AW_ROOT / companion_platform).is_dir():
            raise ValueError(
                f"用户 '{user_id}' 伴生平台 '{companion_platform}' 不存在对应 "
                f"AW 目录（aw/{companion_platform}/），无法创建伴生用户"
            )
