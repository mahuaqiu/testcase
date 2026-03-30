# API AW Token 优化设计文档

## 问题背景

API AW 和 Web AW 使用同一账号时，token 会互相挤掉，造成 Web 登录失败。

**解决方案**：优化 API AW 的 token 获取流程，当出现 401 时，优先从 worker 的 `get_token` action 获取 Web 端已登录的 token，避免重复登录导致 token 冲突。

## 设计目标

1. API AW 优先使用 Web 端已有的 token
2. 减少 API 登录次数，避免 token 冲突
3. 所有 API 请求增加 `x-request-id` header（随机 UUID）

## 详细设计

### 1. User 类修改

**修改 `__init__` 方法签名：**
```python
def __init__(
    self,
    user_id: str,
    platform: str,
    ip: str,
    port: int,
    account: str,
    password: str,
    _ui_user_id: Optional[str] = None,  # 新增：API User 关联的 UI User ID
    **extra: Any
):
    self._ui_user_id = _ui_user_id  # 独立属性，不存入 extra
    ...
```

**新增属性 `_user_instances_ref`：**
- 保存 `user_instances` 字典的引用，用于查找对应的 UI User
- 在 conftest.py 创建 User 后设置

**新增方法 `_get_ui_client`：**
- API User 通过此方法获取对应 UI User 的 TestagentClient
- 用于调用 worker 的 `get_token` action
- 返回 TestagentClient 或 None

**新增方法 `_get_ui_platform`：**
- 返回对应 UI User 的 platform（如 "web"）
- 通过 `_user_instances_ref[_ui_user_id].platform` 获取

### 2. conftest.py 修改

创建 API User 时传入 `_ui_user_id`，并在创建完成后设置 `_user_instances_ref`：

```python
# 创建 API User
api_user_id = f"{user_id}_api"
api_user = User(
    user_id=api_user_id,
    platform="api",
    ip=resource.ip,
    port=resource.port,
    account=resource.account,
    password=resource.password,
    _ui_user_id=user_id,  # 新增：关联 UI User
    **resource.extra
)
user_instances[api_user_id] = api_user

# 创建完成后，设置引用
api_user._user_instances_ref = user_instances
```

### 3. BaseApiAW Token 流程修改

**新增 `_get_token_from_worker` 方法：**

```python
def _get_token_from_worker(self) -> Optional[Dict[str, str]]:
    """从 worker 获取 Web 端已有的 token。

    通过 client.execute 调用 get_token action。

    Returns:
        Token dict 如 {"X-Auth-Token": "xxx"}，或 None。
    """
    client = self.user._get_ui_client()
    if not client:
        return None

    ui_platform = self.user._get_ui_platform()
    if not ui_platform:
        return None

    result = client.execute(
        platform=ui_platform,  # 使用 UI User 的平台类型（如 "web"）
        actions=[{"action_type": "get_token"}]
    )

    if result.get("status") == "SUCCESS" and result.get("actions"):
        output = result["actions"][0].get("output", "")
        if output:
            try:
                return json.loads(output)
            except json.JSONDecodeError:
                # JSON 解析失败，返回 None，fallback 到 API login
                return None
    return None
```

**修改 `_ensure_token` 方法逻辑：**

```
确保 token 有效流程：
1. 如果已有有效 token（未过期） → 返回 token
2. 如果 _ui_user_id 存在且有 UI client：
   a. 尝试 _get_token_from_worker()
   b. 如果获取到 X-Auth-Token → 直接使用，不执行 login
   c. 如果获取失败 → 执行原有 API login
3. 如果 _ui_user_id 不存在 → 执行原有 API login
```

**修改 `_request_with_log` 的 401 处理逻辑：**

```
请求返回 401 时的处理：
1. 清除缓存的 token
2. 如果 _ui_user_id 存在且有 UI client：
   a. 尝试 _get_token_from_worker()
   b. 如果获取到 token → 用该 token 重试请求
   c. 如果重试仍然 401 → 执行 API login 再重试
3. 如果 _ui_user_id 不存在或 get_token 失败 → 执行 API login 再重试
```

### 4. x-request-id Header

在 `_request_with_log` 中为每个请求添加 `x-request-id` header：

```python
import uuid

final_headers["x-request-id"] = str(uuid.uuid4())
```

## 修改文件清单

| 文件 | 修改内容 |
|------|----------|
| `common/user.py` | 修改 `__init__` 接收 `_ui_user_id` 参数，新增 `_user_instances_ref` 属性，新增 `_get_ui_client`、`_get_ui_platform` 方法 |
| `conftest.py` | 创建 API User 时传入 `_ui_user_id`，设置 `_user_instances_ref` |
| `aw/api/base_api_aw.py` | 新增 `_get_token_from_worker` 方法，修改 `_ensure_token` 和 `_request_with_log` |

## Worker get_token Action 说明

**请求：**
```json
{
  "action_type": "get_token"
}
```

**响应：**
```json
{
  "number": 0,
  "action_type": "get_token",
  "status": "SUCCESS",
  "output": "{\"X-Auth-Token\": \"abc123\", \"Authorization\": \"Bearer xyz\"}"
}
```

## 测试验证

1. 验证 API User 能正确获取 UI User 的 client
2. 验证 401 时优先尝试 get_token
3. 验证 get_token 成功后能正确使用 token
4. 验证 get_token 失败时 fallback 到 API login
5. 验证 `x-request-id` header 正确添加且每次请求不同