# 按用户/平台控制 Setup/Teardown Hooks 设计

## 问题背景

多端、多用户用例（如 windows + mac，或双 web）中，经常需要：

- 只让部分用户执行某个 setup（例如仅主持人 `login`）
- 只让部分用户执行某个 teardown（例如仅 userB `leave`，userA 保持默认）
- 同平台多用户需要不同 hooks

### 现状

```
config.yaml（按平台默认）
        ↓
@pytest.mark.hooks(setup=..., teardown=...)   # 用例级，全局一份
        ↓
HooksResolver.resolve(platform, defaults, case_hooks)
        ↓
对每个 user 执行「平台默认 ⊕ 同一份用例 hooks」
```

| 能力 | 现状 |
|------|------|
| 按平台默认不同 hooks | ✅ `config.yaml` |
| 用例级全局覆盖/增量 | ✅ `@pytest.mark.hooks` |
| 按 user_id 区分 | ❌ |
| 用例级按 platform 批量覆盖 | ❌ |
| 同平台双用户不同 hooks | ❌ |

**根因**：`case_hooks` 只有一份，解析维度只有 `platform`，没有 `user_id`。

## 设计目标

1. **按用户控制**：可指定 `userA` / `userB` / `userA_api` 各自的 setup/teardown
2. **按平台控制（糖）**：可指定 `windows` / `mac` 等平台下所有用户的覆盖
3. **向后兼容**：现有全局 `setup` / `teardown` 写法行为不变
4. **语义统一**：继续复用 `+` / `-` / 无前缀覆盖 / 字典参数
5. **配置错误早暴露**：hooks 中引用未声明的 user 直接 fail

## 非目标

- 不改 `@pytest.mark.users` 结构（不把 hooks 嵌进 users）
- 不新增独立的 `@pytest.mark.user_hooks` 标记
- 不改变 hook 方法命名约定（仍为 `do_{name}`）
- 不做 hooks 并行执行
- 不引入 host/guest 角色抽象（用 user_id 表达即可）

## 方案选择

对比过三种方案：

| 方案 | 描述 | 结论 |
|------|------|------|
| **A. 扩展 `@pytest.mark.hooks`** | 增加可选 user / platform 键 | **采用** |
| B. hooks 嵌进 `users` | `userA: {platform, setup, teardown}` | 破坏资源标记、职责过重 |
| C. 新标记 `user_hooks` | 与 hooks 并列 | 两套标记，表达力重复 |

**采用方案 A**：零破坏、控制最细、心智仍在 hooks 标记内。

## 语法设计

### 1. 兼容旧写法（行为不变）

```python
@pytest.mark.hooks(setup=["+login"], teardown=["-stop_app"])
```

所有用户：`平台默认` → 应用全局 `setup` / `teardown`。

### 2. 按用户覆盖（核心）

```python
@pytest.mark.users({"userA": "windows", "userB": "mac"})
@pytest.mark.hooks(
    setup=["+login"],  # 可选全局层
    userA={"setup": ["+login"], "teardown": ["+leave"]},
    userB={"teardown": ["-stop_app"]},
)
```

允许**只写 user 键、不写全局** `setup` / `teardown`：

```python
@pytest.mark.hooks(
    userA={"setup": ["+login"]},
)
```

此时仅 `userA` 在平台默认上增量；其它用户只使用平台默认。

### 3. 按平台覆盖（批量糖）

```python
@pytest.mark.hooks(
    windows={"setup": ["+login"]},
    mac={"teardown": ["-stop_app"]},
)
```

该平台下所有对应用户生效。

### 4. Hook 项格式（不变）

- 字符串：`"start_app"` / `"+login"` / `"-stop_app"`
- 字典：`{"start_app": "edge"}` / `{"+start_app": "edge"}` / `{"leave": True}`

## 解析模型

### 标记键分类

`@pytest.mark.hooks` 的 kwargs 分为：

| 键 | 类型 | 含义 |
|----|------|------|
| `setup` / `teardown` | 全局层 | 现有语义，作用于所有用户 |
| 出现在 `config.hooks` 中的平台名 | 平台层 | 值是 dict，可含 `setup` / `teardown`（可只写其一） |
| 其它键（`userA`、`userB`、`userA_api`…） | 用户层 | 值同上 |

平台键集合取自 `default_hooks.keys()`（即 `config.yaml` 的 `hooks` 段），避免硬编码平台列表。

### 合并优先级

对用户 `U`（平台 `P`），按层叠加：

```
① config.yaml hooks[P]           # 平台默认
② case 全局 setup / teardown     # 若声明
③ case 平台键 P={...}            # 若声明
④ case 用户键 U={...}            # 若声明（最终层）
```

每一层的合并规则与现有 `HooksResolver` 完全一致（`+` 增量、`-` 移除、无前缀字符串完全覆盖、混合字典有序合并等）。

### API 用户规则

- 自动创建的 `userA_api` **不继承** `userA` 的用户层覆盖
- 仅当显式写 `userA_api={...}` 或 `api={...}` 时改变 API 用户 hooks
- `api={...}` 作用于所有 `platform == "api"` 的用户；`userA_api` 只作用于该用户

### 未知 user 键

在 setup 执行前校验：

```text
case_hooks 中的用户层键 ⊆ user_instances.keys()
```

若存在未声明用户（例如写了 `userC` 但 `users` 只有 `userA`/`userB`），**直接 fail**，错误信息需列出非法键与合法用户集合。

### 其它边界（保持现状）

| 场景 | 行为 |
|------|------|
| setup 失败 | 中断后续用户 setup；非连接错误时对已创建用户执行 teardown |
| teardown | 跳过 `user._used == False` 的用户 |
| teardown 顺序 | API 用户优先，其它用户保持原顺序 |
| hook 执行 | 仍走 `_execute_hooks` / `do_{name}`，逻辑不变 |

## 实现设计

### 1. `common/hooks_resolver.py`

扩展解析 API：

```python
class HooksResolver:
    @staticmethod
    def resolve(
        platform: str,
        default_hooks: Dict[str, Dict[str, List[Any]]],
        case_hooks: Dict[str, Any] = None,
        user_id: str = None,
    ) -> Dict[str, List[Any]]:
        """按 平台默认 → 全局 → 平台键 → 用户键 合并最终 hooks。"""
        ...

    @staticmethod
    def validate_user_keys(
        case_hooks: Dict[str, Any],
        known_user_ids: Iterable[str],
        known_platforms: Iterable[str],
    ) -> None:
        """用户层键若不在 known_user_ids 中，抛出 ValueError。"""
        ...

    @staticmethod
    def split_case_hooks(
        case_hooks: Dict[str, Any],
        known_platforms: Iterable[str],
    ) -> tuple[Dict, Dict, Dict]:
        """拆成 (global_hooks, platform_hooks, user_hooks)。"""
        ...
```

内部建议将「单层合并」抽成可复用方法（现有 `resolve` 的 case 合并逻辑），避免四层复制粘贴。

### 2. `conftest.py`

setup / teardown 循环改为：

```python
case_hooks = _get_case_hooks(request.node)
HooksResolver.validate_user_keys(
    case_hooks,
    known_user_ids=user_instances.keys(),
    known_platforms=hooks_config.keys(),
)

for user_id, user in user_instances.items():
    final_hooks = HooksResolver.resolve(
        user.platform,
        hooks_config,
        case_hooks,
        user_id=user_id,
    )
    _execute_hooks(user, final_hooks.get("setup", []), hook_type="setup")
```

teardown（含 setup 失败后的清理路径）同样传入 `user_id`。

marker 注册说明更新为支持 per-user / per-platform 示例。

### 3. 单测 `tests/unit/test_hooks.py`

至少覆盖：

1. 旧全局写法结果不变（回归）
2. 仅 `userA` 键：userA 增量，userB 仅默认
3. 全局 + user 叠加：优先级正确
4. 平台键 `windows` 影响 windows 用户，不影响 mac
5. 用户键优先于平台键
6. `userA` 不影响 `userA_api`；`userA_api` 显式覆盖生效
7. 未知 user 键 `validate_user_keys` 抛错
8. 混合 `+/−`/字典格式在用户层仍按既有规则工作

### 4. 文档

更新：

- `AGENTS.md` 第七章 Hooks 配置
- `CLAUDE.md` Hooks 小节

补充多用户示例与优先级说明。

## 用例作者目标体验

```python
@pytest.mark.users({"userA": "windows", "userB": "mac"})
@pytest.mark.hooks(
    userA={"setup": ["+login"]},              # 仅 Win 用户 setup 登录
    userB={"teardown": ["-stop_app"]},        # 仅 Mac 用户跳过关应用
    userA_api={"teardown": ["-cancel_all_meetings"]},  # 按需关闭 API 清理
)
class TestClass:
    def test_cross_platform_001(self, users):
        userA = users["userA"]
        userB = users["userB"]
        ...
```

## 兼容性与迁移

- 未使用 user/platform 键的用例：**零改动**
- 新能力为纯增量；不强制迁移
- Skill / 代码生成在多用户差异场景下优先写 user 键，避免误用全局 `-xxx` 误伤所有用户

## 测试与验收

1. 单元测试全部通过（含新增分层场景）
2. 现有 `test_hooks.py` 回归通过
3. 手工或示例用例验证：双用户不同 setup/teardown 日志中可见差异
4. 非法 user 键时用例以明确错误失败

## 实现顺序建议

1. 重构 `HooksResolver`：抽出单层合并 + `split` + `validate`
2. 扩展 `resolve(..., user_id=)` 并补单测
3. 改 `conftest` 调用点
4. 更新 `AGENTS.md` / `CLAUDE.md`
5. 全量 hooks 相关单测回归
