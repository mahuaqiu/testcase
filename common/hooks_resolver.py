"""Hooks 解析器。"""

from typing import Dict, List, Any, Iterable


class HooksResolver:
    """Hooks 解析器。

    合并平台默认 hooks 和用例级别 hooks。
    支持字符串和字典格式的 hooks：
    - 字符串: "start_app" - 使用默认参数
    - 字典: {"start_app": "edge"} - 传入单个参数
    - 字典: {"create_meeting": ["a", "b"]} - 列表按位置参数展开（多参数）

    解析支持分层合并：
    平台默认 → 目录 conftest 层 → 全局 setup/teardown → 平台键 → 用户键。
    目录 conftest 层与用例标记层使用同一套键结构和合并规则，通过
    resolve + apply_case 两遍组合实现叠加。

    app_type 是标量（非空字符串）而非列表，不参与 setup/teardown 的
    列表合并机制，由各层单独识别、直接覆盖：用户键 > 平台键 > 全局，
    且每一层覆盖其 base（config.yaml 平台默认 → conftest 各层 → 用例标记）。
    """

    @staticmethod
    def resolve(
        platform: str,
        default_hooks: Dict[str, Dict[str, Any]],
        case_hooks: Dict[str, Any] = None,
        user_id: str = None,
    ) -> Dict[str, Any]:
        """在平台默认 hooks 上叠加一层 case hooks。

        Args:
            platform: 用户所在平台。
            default_hooks: 平台默认 hooks 配置（config.yaml 的 hooks 段）。
            case_hooks: 一层 case hooks（目录 conftest 的 get_hooks() 或用例标记）。
            user_id: 当前用户 ID（用于定位用户层覆盖）。

        Returns:
            最终的 hooks 字典: {"setup": [...], "teardown": [...], "app_type": ...}
        """
        platform_defaults = default_hooks.get(platform, {})
        base = {
            "setup": list(platform_defaults.get("setup", [])),
            "teardown": list(platform_defaults.get("teardown", [])),
        }
        if platform_defaults.get("app_type"):
            base["app_type"] = platform_defaults["app_type"]
        return HooksResolver.apply_case(
            base, case_hooks, list(default_hooks.keys()),
            platform=platform, user_id=user_id
        )

    @staticmethod
    def apply_case(
        base: Dict[str, Any],
        case_hooks: Dict[str, Any],
        known_platforms: Iterable[str],
        platform: str = None,
        user_id: str = None,
        teardown_prepend: bool = False,
    ) -> Dict[str, Any]:
        """在已解析的 base 上叠加一层 case hooks（全局 → 平台键 → 用户键）。

        app_type 为标量覆盖：本层全局/平台键/用户键中声明的非空值按
        用户键 > 平台键 > 全局取最具体者，覆盖 base 透传的值。

        Args:
            base: 底层 hooks（平台默认，或已叠加目录 conftest 层的结果）。
            case_hooks: 一层 case hooks，键结构同 @pytest.mark.hooks。
            known_platforms: 已知平台名集合（用于区分平台键和用户键）。
            user_id: 当前用户 ID。
            teardown_prepend: True 时本层 teardown 的增量项前插到列表头部，
                即本层 teardown 先于 base 中的 teardown 执行。用于用例标记层
                的 teardown 优先执行；setup 及目录 conftest 层不受影响。

        Returns:
            最终的 hooks 字典: {"setup": [...], "teardown": [...], "app_type": ...}
        """
        result = {
            "setup": list(base.get("setup", [])),
            "teardown": list(base.get("teardown", [])),
        }
        if base.get("app_type") is not None:
            result["app_type"] = base["app_type"]

        if not case_hooks:
            return result

        # 拆分 case_hooks（全局 / 平台 / 用户 / app_type）
        global_hooks, platform_hooks, user_hooks, case_app_type = (
            HooksResolver.split_case_hooks(case_hooks, known_platforms)
        )

        # 1. 全局层（setup/teardown）
        for hook_type in ["setup", "teardown"]:
            case_list = global_hooks.get(hook_type, [])
            if case_list:
                HooksResolver._apply_case_hooks(result, hook_type, case_list, prepend=teardown_prepend and hook_type == "teardown")

        # 2. 平台键覆盖（windows/mac/web/api 等）
        if platform and platform in platform_hooks:
            for hook_type in ["setup", "teardown"]:
                case_list = platform_hooks[platform].get(hook_type, [])
                if case_list:
                    HooksResolver._apply_case_hooks(result, hook_type, case_list, prepend=teardown_prepend and hook_type == "teardown")

        # 3. 用户键覆盖（userA/userB/userA_api 等）
        if user_id and user_id in user_hooks:
            for hook_type in ["setup", "teardown"]:
                case_list = user_hooks[user_id].get(hook_type, [])
                if case_list:
                    HooksResolver._apply_case_hooks(result, hook_type, case_list, prepend=teardown_prepend and hook_type == "teardown")

        # 4. app_type 标量覆盖，作用域越具体优先级越高：
        # 用户键 > 平台键 > 全局；本层声明的值直接覆盖 base 中的值。
        if (
            user_id
            and user_id in user_hooks
            and user_hooks[user_id].get("app_type")
        ):
            result["app_type"] = user_hooks[user_id]["app_type"]
        elif (
            platform
            and platform in platform_hooks
            and platform_hooks[platform].get("app_type")
        ):
            result["app_type"] = platform_hooks[platform]["app_type"]
        elif case_app_type is not None:
            result["app_type"] = case_app_type

        return result

    @staticmethod
    def _apply_case_hooks(
        result: Dict[str, List[Any]],
        hook_type: str,
        case_list: List[Any],
        prepend: bool = False,
    ) -> None:
        """应用单层 case hooks（复用原有逻辑，避免各层重复代码）。

        Args:
            result: 累积中的 hooks 字典。
            hook_type: "setup" 或 "teardown"。
            case_list: 本层该类型的 hooks 列表。
            prepend: True 时增量项（+ 前缀）插入列表头部，保持声明顺序，
                使本层 teardown 先于已有 teardown 执行。
        """
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
            new_items = []
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
                    for h in result[hook_type] + new_items
                )
                if not exists:
                    new_items.append(clean_item)
            if new_items:
                if prepend:
                    # 前插且保持声明顺序
                    result[hook_type][0:0] = new_items
                else:
                    result[hook_type].extend(new_items)

    @staticmethod
    def split_case_hooks(
        case_hooks: Dict[str, Any],
        known_platforms: Iterable[str],
    ) -> tuple[
        Dict[str, List[Any]],
        Dict[str, Dict[str, List[Any]]],
        Dict[str, Dict[str, List[Any]]],
        Any,
    ]:
        """拆分 case_hooks 为 (global, platform, user, app_type)。

        - setup/teardown → 全局层
        - app_type → 全局层标量覆盖值（不是用户键）
        - 已知平台名 → 平台层
        - 其它键 → 用户层
        """
        platform_set = set(known_platforms)
        global_hooks: Dict[str, List[Any]] = {}
        platform_hooks: Dict[str, Dict[str, List[Any]]] = {}
        user_hooks: Dict[str, Dict[str, List[Any]]] = {}
        app_type: Any = None

        for key, value in case_hooks.items():
            if key == "app_type":
                if value is not None:
                    app_type = value
            elif key in ("setup", "teardown"):
                if isinstance(value, list):
                    global_hooks[key] = value
            elif key in platform_set:
                platform_hooks[key] = HooksResolver._normalize_scoped_hooks(value)
            else:
                # 用户键（userA、userB、userA_api 等）
                user_hooks[key] = HooksResolver._normalize_scoped_hooks(value)

        return global_hooks, platform_hooks, user_hooks, app_type

    @staticmethod
    def _normalize_scoped_hooks(value: Any) -> Dict[str, Any]:
        """将平台/用户作用域值规范为 {setup, teardown, app_type} 字典。"""
        scoped: Dict[str, Any] = {}
        if isinstance(value, dict):
            for hk in ("setup", "teardown"):
                if hk in value and isinstance(value[hk], list):
                    scoped[hk] = value[hk]
            if value.get("app_type"):
                scoped["app_type"] = value["app_type"]
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
        _, _, user_hooks, _ = HooksResolver.split_case_hooks(
            case_hooks, known_platforms
        )
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
