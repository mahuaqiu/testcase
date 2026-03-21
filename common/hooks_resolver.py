"""Hooks 解析器。"""

from typing import Dict, List, Any


class HooksResolver:
    """Hooks 解析器。

    合并平台默认 hooks 和用例级别 hooks。
    """

    @staticmethod
    def resolve(
        platform: str,
        default_hooks: Dict[str, Dict[str, List[str]]],
        case_hooks: Dict[str, List[str]] = None
    ) -> Dict[str, List[str]]:
        """解析最终的 hooks 列表。

        Args:
            platform: 平台类型。
            default_hooks: 平台默认 hooks 配置。
            case_hooks: 用例级别的 hooks 标记。

        Returns:
            最终的 hooks 字典: {"setup": [...], "teardown": [...]}
        """
        result = {"setup": [], "teardown": []}

        # 1. 获取平台默认 hooks
        platform_defaults = default_hooks.get(platform, {})
        result["setup"] = list(platform_defaults.get("setup", []))
        result["teardown"] = list(platform_defaults.get("teardown", []))

        # 2. 用例级别 hooks 覆盖或修改
        if not case_hooks:
            return result

        for hook_type in ["setup", "teardown"]:
            case_list = case_hooks.get(hook_type, [])
            if not case_list:
                continue

            # 分析前缀
            to_add = []
            to_remove = []
            to_replace = None

            for item in case_list:
                if item.startswith("+"):
                    to_add.append(item[1:])
                elif item.startswith("-"):
                    to_remove.append(item[1:])
                else:
                    to_replace = True

            if to_replace:
                # 完全覆盖
                result[hook_type] = [item for item in case_list if not item.startswith(("+", "-"))]
            else:
                # 增量修改
                for item in to_remove:
                    if item in result[hook_type]:
                        result[hook_type].remove(item)
                for item in to_add:
                    if item not in result[hook_type]:
                        result[hook_type].append(item)

        return result