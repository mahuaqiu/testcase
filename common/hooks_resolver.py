"""Hooks 解析器。"""

from typing import Dict, List, Any


class HooksResolver:
    """Hooks 解析器。

    合并平台默认 hooks 和用例级别 hooks。
    支持字符串和字典格式的 hooks：
    - 字符串: "start_app" - 使用默认参数
    - 字典: {"start_app": "edge"} - 传入参数
    """

    @staticmethod
    def resolve(
        platform: str,
        default_hooks: Dict[str, Dict[str, List[Any]]],
        case_hooks: Dict[str, List[Any]] = None
    ) -> Dict[str, List[Any]]:
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

            # 分析前缀。无前缀字典是一个可执行 hook，不能像无前缀字符串
            # 一样把同一列表中的 + hook 过滤掉。
            to_add = []
            to_remove = []
            has_unprefixed_string = False
            has_unprefixed_dict = False

            for item in case_list:
                # 提取 hook 名称（支持字符串和字典格式）
                if isinstance(item, dict):
                    hook_name = next(iter(item.keys()))
                else:
                    hook_name = item

                if hook_name.startswith("+"):
                    to_add.append(item)
                elif hook_name.startswith("-"):
                    to_remove.append(hook_name[1:])
                elif isinstance(item, dict):
                    has_unprefixed_dict = True
                else:
                    has_unprefixed_string = True

            if has_unprefixed_string:
                # 完全覆盖
                result[hook_type] = [
                    item for item in case_list
                    if not (isinstance(item, str) and item.startswith(("+", "-")))
                    and not (isinstance(item, dict) and next(iter(item.keys())).startswith(("+", "-")))
                ]
            elif has_unprefixed_dict and (to_add or to_remove):
                # 混合模式下，按用例声明顺序执行显式 hook；未声明的默认 hook
                # 仍然保留，但放在显式 hook 之后。
                result[hook_type] = HooksResolver._merge_ordered(
                    result[hook_type], case_list
                )
            elif has_unprefixed_dict:
                # 纯字典列表保持原有的完全覆盖语义。
                result[hook_type] = list(case_list)
            else:
                # 增量修改
                for item in to_remove:
                    # 移除匹配的 hook（支持字符串和字典格式）
                    result[hook_type] = [
                        h for h in result[hook_type]
                        if not (h == item or (isinstance(h, dict) and item in h))
                    ]
                for item in to_add:
                    # 添加新 hook（去除前缀）
                    if isinstance(item, dict):
                        # 字典格式：{"+hook_name": arg} → {"hook_name": arg}
                        original_key = next(iter(item.keys()))
                        clean_key = original_key[1:]  # 去除前缀
                        clean_item = {clean_key: item[original_key]}
                    else:
                        # 字符串格式："+hook_name" → "hook_name"
                        clean_item = item[1:]  # 去除前缀

                    # 检查是否已存在
                    hook_name = clean_item if isinstance(clean_item, str) else next(iter(clean_item.keys()))
                    exists = any(
                        h == hook_name or (isinstance(h, dict) and hook_name in h)
                        for h in result[hook_type]
                    )
                    if not exists:
                        result[hook_type].append(clean_item)

        return result

    @staticmethod
    def _merge_ordered(default_list: List[Any], case_list: List[Any]) -> List[Any]:
        """按用例顺序合并混合格式 hooks。"""
        removed_names = set()
        explicit_items = []
        explicit_names = set()

        for item in case_list:
            hook_name = HooksResolver._hook_name(item)
            if hook_name.startswith("-"):
                removed_names.add(hook_name[1:])
                continue

            clean_item = HooksResolver._clean_hook_item(item)
            clean_name = HooksResolver._hook_name(clean_item)
            if clean_name not in explicit_names:
                explicit_items.append(clean_item)
                explicit_names.add(clean_name)

        # 显式 hook 以用例顺序为准，未显式声明的默认 hook 按原顺序追加。
        remaining_defaults = [
            item for item in default_list
            if HooksResolver._hook_name(item) not in removed_names
            and HooksResolver._hook_name(item) not in explicit_names
        ]
        return explicit_items + remaining_defaults

    @staticmethod
    def _hook_name(item: Any) -> str:
        """获取 hook 名称。"""
        if isinstance(item, dict):
            return next(iter(item.keys()))
        return item

    @staticmethod
    def _clean_hook_item(item: Any) -> Any:
        """移除增量 hook 名称上的 + 前缀。"""
        if isinstance(item, dict):
            hook_name, hook_arg = next(iter(item.items()))
            if hook_name.startswith("+"):
                return {hook_name[1:]: hook_arg}
            return item
        if isinstance(item, str) and item.startswith("+"):
            return item[1:]
        return item
