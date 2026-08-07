"""Hooks 解析器。"""

from typing import Dict, List, Any, Iterable


class HooksResolver:
    """Hooks 解析器。

    合并平台默认 hooks 和用例级别 hooks。
    支持字符串和字典格式的 hooks：
    - 字符串: "start_app" - 使用默认参数
    - 字典: {"start_app": "edge"} - 传入参数

    用例级支持四层合并：
    平台默认 → 全局 setup/teardown → 平台键 → 用户键。
    """

    @staticmethod
    def resolve(
        platform: str,
        default_hooks: Dict[str, Dict[str, List[Any]]],
        case_hooks: Dict[str, Any] = None,
        user_id: str = None,
    ) -> Dict[str, List[Any]]:
        """解析最终的 hooks 列表。

        支持四层合并：平台默认 → 全局 case → 平台键 → 用户键。

        Args:
            platform: 用户所在平台。
            default_hooks: 平台默认 hooks 配置。
            case_hooks: 用例级别的 hooks 标记（含 setup/teardown/userX/platformY 等键）。
            user_id: 当前用户 ID（用于定位用户层覆盖）。

        Returns:
            最终的 hooks 字典: {"setup": [...], "teardown": [...]}
        """
        result = {"setup": [], "teardown": []}

        # 1. 获取平台默认 hooks
        platform_defaults = default_hooks.get(platform, {})
        result["setup"] = list(platform_defaults.get("setup", []))
        result["teardown"] = list(platform_defaults.get("teardown", []))

        if not case_hooks:
            return result

        # 拆分 case_hooks（全局 / 平台 / 用户）
        global_hooks, platform_hooks, user_hooks = HooksResolver.split_case_hooks(
            case_hooks, list(default_hooks.keys())
        )

        # 2. 全局层（setup/teardown）
        for hook_type in ["setup", "teardown"]:
            case_list = global_hooks.get(hook_type, [])
            if case_list:
                HooksResolver._apply_case_hooks(result, hook_type, case_list)

        # 3. 平台键覆盖（windows/mac/web/api 等）
        if platform in platform_hooks:
            for hook_type in ["setup", "teardown"]:
                case_list = platform_hooks[platform].get(hook_type, [])
                if case_list:
                    HooksResolver._apply_case_hooks(result, hook_type, case_list)

        # 4. 用户键覆盖（userA/userB/userA_api 等）
        if user_id and user_id in user_hooks:
            for hook_type in ["setup", "teardown"]:
                case_list = user_hooks[user_id].get(hook_type, [])
                if case_list:
                    HooksResolver._apply_case_hooks(result, hook_type, case_list)

        return result

    @staticmethod
    def _apply_case_hooks(
        result: Dict[str, List[Any]], hook_type: str, case_list: List[Any]
    ) -> None:
        """应用单层 case hooks（复用原有逻辑，避免四层重复代码）。"""
        if not case_list:
            return

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
                and not (
                    isinstance(item, dict)
                    and next(iter(item.keys())).startswith(("+", "-"))
                )
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
                hook_name = (
                    clean_item
                    if isinstance(clean_item, str)
                    else next(iter(clean_item.keys()))
                )
                exists = any(
                    h == hook_name or (isinstance(h, dict) and hook_name in h)
                    for h in result[hook_type]
                )
                if not exists:
                    result[hook_type].append(clean_item)

    @staticmethod
    def split_case_hooks(
        case_hooks: Dict[str, Any],
        known_platforms: Iterable[str],
    ) -> tuple[
        Dict[str, List[Any]],
        Dict[str, Dict[str, List[Any]]],
        Dict[str, Dict[str, List[Any]]],
    ]:
        """拆分 case_hooks 为 (global, platform, user)。

        - setup/teardown → 全局层
        - 已知平台名 → 平台层
        - 其它键 → 用户层
        """
        platform_set = set(known_platforms)
        global_hooks: Dict[str, List[Any]] = {}
        platform_hooks: Dict[str, Dict[str, List[Any]]] = {}
        user_hooks: Dict[str, Dict[str, List[Any]]] = {}

        for key, value in case_hooks.items():
            if key in ("setup", "teardown"):
                if isinstance(value, list):
                    global_hooks[key] = value
            elif key in platform_set:
                platform_hooks[key] = HooksResolver._normalize_scoped_hooks(value)
            else:
                # 用户键（userA、userB、userA_api 等）
                user_hooks[key] = HooksResolver._normalize_scoped_hooks(value)

        return global_hooks, platform_hooks, user_hooks

    @staticmethod
    def _normalize_scoped_hooks(value: Any) -> Dict[str, List[Any]]:
        """将平台/用户作用域值规范为 {setup, teardown} 字典。"""
        scoped: Dict[str, List[Any]] = {}
        if isinstance(value, dict):
            for hk in ("setup", "teardown"):
                if hk in value and isinstance(value[hk], list):
                    scoped[hk] = value[hk]
        elif isinstance(value, list):
            # 简写：直接给列表时视为 setup
            scoped["setup"] = value
        return scoped

    @staticmethod
    def validate_user_keys(
        case_hooks: Dict[str, Any],
        known_user_ids: Iterable[str],
        known_platforms: Iterable[str],
    ) -> None:
        """校验用户键合法性。

        若 hooks 中引用了未声明的用户，直接抛出 ValueError。
        """
        if not case_hooks:
            return

        known_users = set(known_user_ids)
        _, _, user_hooks = HooksResolver.split_case_hooks(case_hooks, known_platforms)
        unknown = sorted(uid for uid in user_hooks if uid not in known_users)
        if unknown:
            raise ValueError(
                f"hooks 中引用了未声明的用户: {unknown}。"
                f"合法用户: {sorted(known_users)}"
            )

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
