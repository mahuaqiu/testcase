# 伴生平台（web+windows）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 支持 `@pytest.mark.users({"userA": "web+windows"})` 声明伴生平台，伴生用户复用主平台机器与账号，申请/释放/keepalive 只针对主平台，伴生用户 hooks 懒触发。

**Architecture:** 在 `users` fixture 层解析复合平台语法（新增 `common/users_marker.py` 纯函数），`UserManager` 与平台 API 契约零改动；伴生 `User` 复用主用户资源（同 ip/port/账号），setup hooks 通过 `User` 上的懒执行回调在首次取 AW 方法时触发；报告/截图按 `_is_companion` + `_used` 过滤。

**Tech Stack:** Python 3.10+ / pytest，工程为 D:\code\testcase

**Spec:** [docs/superpowers/specs/2026-11-13-companion-platform-design.md](../specs/2026-11-13-companion-platform-design.md)

## Global Constraints

- 所有命令在 `D:\code\testcase` 下运行（Git Bash 路径 `/d/code/testcase`）
- 不修改 `testcases/` 目录任何文件（架构契约测试 `tests/architecture/test_testcase_contract.py` 会 git diff 检查）
- 不修改 `common/user_manager.py`、`common/keepalive.py`（平台契约零改动）
- `{"userA": "web"}` 现有行为完全不变；`{"userA_windows": "windows"}`（无伴生声明）仍是普通独立用户
- 代码注释与 docstring 用中文，匹配现有风格
- 单测运行命令：`python -m pytest tests/unit/test_users_companion.py -v`（pytest.ini 的 testpaths 不含 tests/，必须显式传路径）
- 每个 Task 结束必须 commit，commit message 用中文

---

### Task 1: users 标记语法解析模块 `common/users_marker.py`

**Files:**
- Create: `common/users_marker.py`
- Test: `tests/unit/test_users_companion.py`

**Interfaces:**
- Consumes: 无（纯函数模块）
- Produces:
  - `parse_users_requirement(users_requirement: Dict[str, str]) -> Tuple[Dict[str, str], Dict[str, str]]` — 返回 `(platform_requests, companions)`；非法声明抛 `ValueError`
  - `validate_companion_platforms(companions: Dict[str, str]) -> None` — 伴生平台无 `aw/{platform}/` 目录时抛 `ValueError`

- [ ] **Step 1: 写失败测试**

创建 `tests/unit/test_users_companion.py`：

```python
"""伴生平台（web+windows）解析与懒 hooks 测试。"""

import pytest

from common.users_marker import parse_users_requirement, validate_companion_platforms


def test_parse_plain_platform_unchanged():
    """纯主平台声明：申请体不变，无伴生。"""
    requests_, companions = parse_users_requirement({"userA": "web", "userB": "windows"})
    assert requests_ == {"userA": "web", "userB": "windows"}
    assert companions == {}


def test_parse_companion_platform():
    """web+windows：只申请 web，伴生映射 userA -> windows。"""
    requests_, companions = parse_users_requirement({"userA": "web+windows"})
    assert requests_ == {"userA": "web"}
    assert companions == {"userA": "windows"}


def test_parse_mixed_users():
    """多用户各自声明：仅声明了伴生的用户有伴生映射。"""
    requests_, companions = parse_users_requirement({"userA": "web+windows", "userB": "web"})
    assert requests_ == {"userA": "web", "userB": "web"}
    assert companions == {"userA": "windows"}


def test_parse_rejects_api_main_platform():
    """主平台不能是 api。"""
    with pytest.raises(ValueError, match="主平台不能是 api"):
        parse_users_requirement({"userA": "api+windows"})


def test_parse_rejects_api_companion():
    """伴生平台不能是 api。"""
    with pytest.raises(ValueError, match="伴生平台不能是 api"):
        parse_users_requirement({"userA": "web+api"})


def test_parse_rejects_triple_platform():
    """不支持多伴生。"""
    with pytest.raises(ValueError, match="只支持"):
        parse_users_requirement({"userA": "web+windows+mac"})


def test_parse_rejects_conflicting_explicit_key():
    """显式声明的伴生键与伴生映射冲突时报错。"""
    with pytest.raises(ValueError, match="冲突"):
        parse_users_requirement({"userA": "web+windows", "userA_windows": "windows"})


def test_validate_companion_platforms_accepts_windows():
    """windows 有对应 AW 目录，校验通过。"""
    validate_companion_platforms({"userA": "windows"})  # 不抛异常


def test_validate_companion_platforms_rejects_unknown():
    """不存在的平台没有 AW 目录，报错。"""
    with pytest.raises(ValueError, match="AW 目录"):
        validate_companion_platforms({"userA": "no_such_platform"})
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/unit/test_users_companion.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'common.users_marker'`）

- [ ] **Step 3: 实现 `common/users_marker.py`**

```python
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
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/unit/test_users_companion.py -v`
Expected: 9 个测试全部 PASS

- [ ] **Step 5: Commit**

```bash
git add common/users_marker.py tests/unit/test_users_companion.py
git commit -m "feat: users 标记伴生平台语法解析模块"
```

---

### Task 2: User 懒执行 setup hooks 机制

**Files:**
- Modify: `common/user.py`
- Test: `tests/unit/test_users_companion.py`（追加）

**Interfaces:**
- Consumes: 无
- Produces（Task 3 依赖）:
  - `User._is_companion: bool` 属性（默认 `False`，fixture 置 True）
  - `User.set_deferred_setup(callback: Callable[[], None]) -> None`
  - `User.__getattr__` 取到可调用 AW 方法时触发一次 `_run_deferred_setup()`

- [ ] **Step 1: 追加失败测试**

在 `tests/unit/test_users_companion.py` 末尾追加（import 区增加 `from common.user import User`）：

```python
from common.user import User


def _make_windows_user() -> User:
    return User(user_id="userA_windows", platform="windows", ip="127.0.0.1", port=8080)


def test_deferred_setup_runs_once_on_first_aw_fetch():
    """首次取 AW 方法触发一次，之后不再触发。"""
    user = _make_windows_user()
    calls = []
    user.set_deferred_setup(lambda: calls.append(1))

    method = user.should_toast_exists  # 仅取方法，不调用
    assert callable(method)
    assert calls == [1]
    assert user._used is True

    _ = user.should_toast_exists  # 再次取不再触发
    assert calls == [1]


def test_deferred_setup_not_triggered_without_registration():
    """未注册回调时取 AW 方法不报错、行为不变。"""
    user = _make_windows_user()
    assert callable(user.should_toast_exists)


def test_deferred_setup_not_triggered_by_non_callable():
    """extra 字段访问不触发懒执行。"""
    user = _make_windows_user()
    calls = []
    user.set_deferred_setup(lambda: calls.append(1))
    user.extra["env"] = "test"

    assert user.env == "test"
    assert calls == []


def test_deferred_setup_exception_propagates_and_cleared():
    """懒执行失败：异常从取方法处抛出，且回调已清空不重复执行。"""
    user = _make_windows_user()

    def boom():
        raise RuntimeError("start_app failed")

    user.set_deferred_setup(boom)
    with pytest.raises(RuntimeError, match="start_app failed"):
        _ = user.should_toast_exists

    _ = user.should_toast_exists  # 已清空，不再触发
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/unit/test_users_companion.py -v`
Expected: 新增 4 个测试 FAIL（`AttributeError: ... no attribute 'set_deferred_setup'`），原有 9 个 PASS

- [ ] **Step 3: 修改 `common/user.py`**

3a. `__init__` 中，在 `self._used = False` 之后加两行（保持原注释风格）：

```python
        self._used = False  # 新增：用户是否被实际使用
        self._is_companion = False  # 伴生平台用户（web+windows 的 windows 端），fixture 中置 True
        self._deferred_setup = None  # 伴生用户 setup hooks 懒执行回调（users fixture 注入）
```

3b. 修改 `__getattr__` 的 AW 方法查找段（原样保留其余部分），在标记 `_used` 后触发懒执行：

```python
        # 1. 查找 AW 方法
        for aw_instance in self._aw_instances.values():
            if hasattr(aw_instance, name):
                attr = getattr(aw_instance, name)
                # 如果是可调用方法，标记用户已使用
                if callable(attr):
                    self._used = True
                    # 伴生用户 setup hooks 懒执行：首次取 AW 方法时触发
                    self._run_deferred_setup()
                return attr
```

3c. 在 `mark_used` 方法之后新增两个方法：

```python
    def set_deferred_setup(self, callback) -> None:
        """注册伴生用户 setup hooks 懒执行回调（由 users fixture 注入）。

        Args:
            callback: 无参回调，首次取 AW 方法时执行一次。
        """
        self._deferred_setup = callback

    def _run_deferred_setup(self) -> None:
        """触发并清空待执行的 setup hooks（仅伴生用户会注册回调）。"""
        try:
            callback = object.__getattribute__(self, "_deferred_setup")
        except AttributeError:
            return
        if callback is None:
            return
        # 先清空再执行：避免 hooks 内部再取 AW 方法导致重复触发
        object.__setattr__(self, "_deferred_setup", None)
        callback()
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/unit/test_users_companion.py -v`
Expected: 13 个测试全部 PASS

- [ ] **Step 5: 回归现有单测**

Run: `python -m pytest tests/unit tests/architecture -v`
Expected: 全部 PASS（架构契约测试确认 User 公共行为未变）

- [ ] **Step 6: Commit**

```bash
git add common/user.py tests/unit/test_users_companion.py
git commit -m "feat: User 支持伴生 setup hooks 懒执行"
```

---

### Task 3: users fixture 接线（解析/伴生创建/懒执行/过滤）

**Files:**
- Modify: `conftest.py`
- Test: `tests/unit/test_users_companion.py`（追加）

**Interfaces:**
- Consumes:
  - `parse_users_requirement` / `validate_companion_platforms`（Task 1）
  - `User.set_deferred_setup` / `User._is_companion`（Task 2）
- Produces:
  - `conftest._build_report_user_details(user_instances: Dict[str, User]) -> Dict[str, Dict[str, Any]]`
  - `conftest._build_keepalive_resources(user_instances: Dict[str, User], raw_resources: Dict[str, Any]) -> Dict[str, Any]`
  - `conftest._execute_deferred_setup(user: User, hooks: list, user_id: str) -> None`

- [ ] **Step 1: 追加失败测试**

在 `tests/unit/test_users_companion.py` 末尾追加（import 区增加 `from conftest import _build_keepalive_resources, _build_report_user_details`）：

```python
from conftest import _build_keepalive_resources, _build_report_user_details


def _make_user_triple():
    """构造 主用户(web) + 伴生用户(windows) + api 用户 三元组。"""
    main = User(user_id="userA", platform="web", ip="127.0.0.1", port=8080)
    companion = User(user_id="userA_windows", platform="windows", ip="127.0.0.1", port=8080)
    companion._is_companion = True
    api = User(user_id="userA_api", platform="api", ip="127.0.0.1", port=8080)
    return main, companion, api


def test_report_details_filters_unused_api_and_companion():
    """未使用的伴生用户与 api 用户不进报告；使用过的伴生用户正常展示。"""
    main, companion, api = _make_user_triple()
    instances = {"userA": main, "userA_windows": companion, "userA_api": api}

    details = _build_report_user_details(instances)
    assert set(details) == {"userA"}

    companion._used = True
    details = _build_report_user_details(instances)
    assert set(details) == {"userA", "userA_windows"}
    assert details["userA_windows"]["platform"] == "windows"
    assert details["userA_windows"]["is_api"] is False


def test_keepalive_resources_only_include_applied_machines():
    """keepalive 只包含平台实际返回的机器（伴生/api 用户天然不在其中）。"""
    main, companion, api = _make_user_triple()
    raw = {"userA": {"id": "machine-1", "ip": "1.1.1.1"}}

    result = _build_keepalive_resources(
        {"userA": main, "userA_windows": companion, "userA_api": api}, raw
    )
    assert result == {"userA": {"id": "machine-1", "ip": "1.1.1.1"}}
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/unit/test_users_companion.py -v`
Expected: 整个文件收集失败（`ImportError: cannot import name '_build_keepalive_resources'`），15 个测试均未运行——因为 import 在模块顶部；这即预期的"失败"状态

- [ ] **Step 3: 修改 `conftest.py`**

3a. import 区（`from common.user import User` 之后）加：

```python
from common.users_marker import parse_users_requirement, validate_companion_platforms
```

3b. `users` fixture 中，`if not users_requirement: return {}` 之后、`ReportLogger.reset()` 之前插入解析与校验：

```python
    # 解析伴生平台声明（如 "web+windows"），申请体只保留主平台
    try:
        platform_requests, companions = parse_users_requirement(users_requirement)
        validate_companion_platforms(companions)
    except ValueError as e:
        pytest.fail(f"users 标记解析失败: {e}")
```

3c. 同 fixture 中 `resources = manager.apply(users_requirement, ...)` 改为传主平台申请体：

```python
        resources = manager.apply(platform_requests, testcase_id=testcase_id)
```

3d. 创建 User 实例的主循环之后（`user_instances[api_user_id] = api_user` 所在 for 循环结束、`# 设置 API User 的 user_instances 引用` 之前）插入伴生用户创建：

```python
        # 创建伴生平台 User：复用主用户资源（同机器同 worker 同账号），
        # 不额外申请机器、不生成 _api 用户
        for main_user_id, companion_platform in companions.items():
            resource = resources[main_user_id]
            companion_id = f"{main_user_id}_{companion_platform}"
            companion = User(
                user_id=companion_id,
                platform=companion_platform,
                ip=resource.ip,
                port=resource.port,
                device_id=resource.device_id,
                account=resource.account,
                password=resource.password,
                name=resource.name,
                **resource.extra
            )
            companion._is_companion = True
            user_instances[companion_id] = companion
```

3e. keepalive 启动段整体替换（原 for 循环 + api 跳过逻辑改为按 raw_resources 过滤）：

```python
        # 启动保活（远程模式）——只对平台实际返回的机器；
        # 伴生用户未申请机器，天然不在 raw_resources 中
        rm_config = config.get("resource_manager", {})
        base_url = rm_config.get("base_url", "")
        if base_url:
            for user_id, resource_data in _build_keepalive_resources(user_instances, raw_resources).items():
                keepalive = KeepAliveManager(base_url, rm_config.get("timeout", 30))
                keepalive.start({user_id: resource_data})
                _keepalive_managers[user_id] = keepalive
```

3f. setup 执行循环改为：伴生用户注册懒执行回调并跳过直接执行。原：

```python
        for user_id, user in user_instances.items():
            final_hooks = final_hooks_map[user_id]
            try:
                _execute_hooks(
                    user, final_hooks.get("setup", []), hook_type="setup",
                    user_id=user_id,
                )
            except HookFailureError as e:
```

改为：

```python
        for user_id, user in user_instances.items():
            final_hooks = final_hooks_map[user_id]
            # 伴生用户 setup hooks 懒执行：首次取 AW 方法时才触发，
            # 用例未涉及伴生端则全程不执行
            if user._is_companion:
                setup_hooks = final_hooks.get("setup", [])
                if setup_hooks:
                    user.set_deferred_setup(
                        lambda u=user, hooks=setup_hooks, uid=user_id:
                            _execute_deferred_setup(u, hooks, uid)
                    )
                continue
            try:
                _execute_hooks(
                    user, final_hooks.get("setup", []), hook_type="setup",
                    user_id=user_id,
                )
            except HookFailureError as e:
```

（`except HookFailureError` 起的失败处理逻辑保持原样不动）

3g. `_run_teardown_phase` 中的使用过滤加强（伴生用户在 setup 失障清理路径 `only_used=False` 下也只清理实际使用过的）：

```python
    for user_id, user in _sort_users_for_teardown(user_instances):
        # only_used：普通路径只执行使用过的用户；伴生用户额外收紧：
        # 未使用的伴生端全程不动作（含 setup 失障清理路径）
        if not user._used and (only_used or user._is_companion):
            continue
```

3h. `pytest_runtest_makereport` 失败补充截图循环，`user_id.endswith("_api")` 跳过之后加伴生跳过：

```python
            for user_id, user in users.items():
                if user_id.endswith("_api"):
                    continue
                # 伴生用户与主用户同一台机器，主用户截图已覆盖同一桌面
                if getattr(user, "_is_companion", False):
                    continue
                if user_id in users_with_screenshot:
                    continue  # 已有失败截图，跳过
```

3i. `_generate_report` 中的 user_details 构建段整体替换为调用新辅助函数。原：

```python
    report_user_details = {}
    for user_id, user in user_instances.items():
        if user.platform == "api" and not getattr(user, "_used", False):
            continue
        report_user_details[user_id] = {
            "name": user.name,
            "ip": user.ip,
            "account": user.account,
            "device_sn": user.device_id,
            "platform": user.platform,
            # API 用户只用于 HTTP 数据操作，不展示关联 UI 用户的设备类型。
            "display_platform": "" if user.platform == "api" else user.platform,
            "is_api": user.platform == "api",
        }
```

改为：

```python
    report_user_details = _build_report_user_details(user_instances)
```

3j. 在 `_generate_report` 之前新增三个辅助函数：

```python
def _build_report_user_details(user_instances: Dict[str, User]) -> Dict[str, Dict[str, Any]]:
    """构建报告用户明细，过滤未使用的 api 用户与伴生用户。

    Args:
        user_instances: 用户 ID 到 User 实例的映射。

    Returns:
        报告 user_details 字典。
    """
    report_user_details = {}
    for user_id, user in user_instances.items():
        is_api = user.platform == "api"
        is_companion = getattr(user, "_is_companion", False)
        if (is_api or is_companion) and not user._used:
            continue
        report_user_details[user_id] = {
            "name": user.name,
            "ip": user.ip,
            "account": user.account,
            "device_sn": user.device_id,
            "platform": user.platform,
            # API 用户只用于 HTTP 数据操作，不展示关联 UI 用户的设备类型。
            "display_platform": "" if is_api else user.platform,
            "is_api": is_api,
        }
    return report_user_details


def _build_keepalive_resources(
    user_instances: Dict[str, User], raw_resources: Dict[str, Any]
) -> Dict[str, Any]:
    """构建 keepalive 资源映射，只保留平台实际返回的机器。

    伴生用户未申请机器、api 用户不在申请响应中，天然被排除。

    Args:
        user_instances: 用户 ID 到 User 实例的映射。
        raw_resources: 平台申请响应的原始资源字典。

    Returns:
        {user_id: 原始机器资源} 字典。
    """
    return {
        user_id: raw_resources[user_id]
        for user_id in user_instances
        if user_id in raw_resources
    }


def _execute_deferred_setup(user: User, hooks: list, user_id: str) -> None:
    """伴生用户 setup hooks 懒执行入口（User 首次取 AW 方法时触发）。

    执行失败记录到报告日志（跟随伴生用户显示）后原样抛出，
    由用例调用点失败终结本用例。

    Args:
        user: 伴生 User 实例。
        hooks: 解析后的 setup hooks 列表。
        user_id: 伴生用户 ID，用于日志归属。
    """
    logger = ReportLogger.get_current()
    try:
        _execute_hooks(user, hooks, hook_type="setup", user_id=user_id)
    except HookFailureError as e:
        logger.log_error(f"伴生用户 setup hook 失败: {e}", user_id=user_id)
        raise
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/unit/test_users_companion.py -v`
Expected: 15 个测试全部 PASS

- [ ] **Step 5: 全量回归**

Run: `python -m pytest tests/unit tests/architecture -v`
Expected: 全部 PASS

- [ ] **Step 6: Commit**

```bash
git add conftest.py tests/unit/test_users_companion.py
git commit -m "feat: users fixture 接线伴生平台（申请/创建/懒执行/过滤）"
```

---

### Task 4: 文档更新与最终回归

**Files:**
- Modify: `AGENTS.md`（五、用户资源管理 末尾新增小节）
- Modify: `CLAUDE.md`（核心规则速记 加一行）

**Interfaces:**
- Consumes: 无
- Produces: 无（文档）

- [ ] **Step 1: AGENTS.md 五章末尾（5.5 运行参数之后、六章之前）新增 5.6**

```markdown
### 5.6 伴生平台（web+windows）

同一账号需要同时操作 web 端与 windows 端时，用 `"{主平台}+{伴生平台}"` 声明：

```python
@pytest.mark.users({"userA": "web+windows"})
class TestClass:
    def test_xxx(self, users):
        userA = users["userA"]            # web 端（主平台）
        userA_windows = users["userA_windows"]  # windows 端（伴生，同账号）
        userA_api = users["userA_api"]    # API 端（同账号，自动创建）
```

规则：

- **资源**：只向平台申请主平台（web）一台机器；伴生端复用同一台机器、
  同一个 worker 端口、同一账号。申请、释放、keepalive 只涉及主平台机器
- **hooks**：伴生用户沿用其平台默认 hooks（可按平台/用户键分层覆盖），
  但 setup 懒触发 —— 用例首次调用 `userA_windows` 的 AW 方法时才执行；
  用例未涉及伴生端则 setup/teardown 全程不执行，客户端不拉起
- **不生成** `userA_windows_api`（`userA_api` 已覆盖同账号 API 操作）
- **报告**：失败截图只取主用户（同机器一张即可）；未使用的伴生用户不进报告
- 校验失败（主平台为 api、伴生平台无 AW 目录、键冲突）在申请资源前直接报错
```

- [ ] **Step 2: CLAUDE.md 核心规则速记加一行**

在 `- **用户声明**` 那条之后加：

```markdown
- **伴生平台**：`@pytest.mark.users({"userA": "web+windows"})`，伴生端
  `users["userA_windows"]` 同机器同账号，只申请主平台；伴生 hooks 懒触发（详见 AGENTS.md 5.6）
```

- [ ] **Step 3: 全量回归**

Run: `python -m pytest tests/unit tests/architecture -v`
Expected: 全部 PASS

- [ ] **Step 4: Commit**

```bash
git add AGENTS.md CLAUDE.md
git commit -m "docs: 伴生平台（web+windows）使用说明"
```
