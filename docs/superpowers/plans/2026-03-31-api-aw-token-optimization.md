# API AW Token 优化实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 优化 API AW token 获取流程，优先使用 Web 端已有 token，避免 token 冲突，并为所有 API 请求添加 x-request-id header。

**Architecture:** API User 通过 `_ui_user_id` 属性关联对应的 UI User，获取其 TestagentClient 来调用 worker 的 `get_token` action。401 时优先尝试复用 Web token，失败则 fallback 到 API login。

**Tech Stack:** Python, pytest, requests

---

## 文件结构

| 文件 | 作用 |
|------|------|
| `common/user.py` | User 类核心修改，新增 UI User 关联机制 |
| `conftest.py` | 修改 API User 创建逻辑，传入 `_ui_user_id` 并设置引用 |
| `aw/api/base_api_aw.py` | Token 获取流程优化，新增 `_get_token_from_worker`，修改 401 处理 |

---

### Task 1: User 类修改 - 新增 UI User 关联机制

**Files:**
- Modify: `common/user.py`

- [ ] **Step 1: 修改 User.__init__ 方法签名**

在 `__init__` 方法中新增 `_ui_user_id` 参数：

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
    self._user_instances_ref: Optional[Dict[str, "User"]] = None  # 新增：user_instances 引用
    # ... 其他原有代码不变
```

- [ ] **Step 2: 新增 `_get_ui_client` 方法**

在 User 类中新增方法：

```python
def _get_ui_client(self) -> Optional["TestagentClient"]:
    """获取关联 UI User 的 TestagentClient。

    用于 API User 调用 worker 的 get_token action。

    Returns:
        TestagentClient 实例，或 None（无关联 UI User 时）。
    """
    if not self._ui_user_id:
        return None

    if not self._user_instances_ref:
        return None

    ui_user = self._user_instances_ref.get(self._ui_user_id)
    if not ui_user:
        return None

    return ui_user.client
```

- [ ] **Step 3: 新增 `_get_ui_platform` 方法**

在 User 类中新增方法：

```python
def _get_ui_platform(self) -> Optional[str]:
    """获取关联 UI User 的平台类型。

    Returns:
        平台类型（如 "web"），或 None（无关联 UI User 时）。
    """
    if not self._ui_user_id:
        return None

    if not self._user_instances_ref:
        return None

    ui_user = self._user_instances_ref.get(self._ui_user_id)
    if not ui_user:
        return None

    return ui_user.platform
```

- [ ] **Step 4: 添加必要的 import**

在 `common/user.py` 头部添加 Optional 和 Dict 的 import（如果已有则跳过）：

```python
from typing import Any, Dict, Optional
```

- [ ] **Step 5: 提交 User 类修改**

```bash
git add common/user.py
git commit -m "feat(user): 新增 API User 与 UI User 关联机制"
```

---

### Task 2: conftest.py 修改 - 传入 `_ui_user_id` 并设置引用

**Files:**
- Modify: `conftest.py:99-122`

- [ ] **Step 1: 修改 API User 创建逻辑**

修改 `conftest.py` 中创建 API User 的部分（约第 111-122 行）：

```python
# 支持 _api 后缀：创建同一账号的 API 实例
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
```

- [ ] **Step 2: 在 User 实例创建完成后设置引用**

在 `for user_id, resource in resources.items()` 循环结束后（约第 123 行），添加：

```python
# 设置 API User 的 user_instances 引用
for user_id, user in user_instances.items():
    if user_id.endswith("_api"):
        user._user_instances_ref = user_instances
```

- [ ] **Step 3: 提交 conftest.py 修改**

```bash
git add conftest.py
git commit -m "feat(conftest): API User 创建时关联 UI User"
```

---

### Task 3: BaseApiAW 修改 - 新增 `_get_token_from_worker` 方法

**Files:**
- Modify: `aw/api/base_api_aw.py`

- [ ] **Step 1: 添加必要的 import**

在文件头部添加：

```python
import json
import uuid
```

- [ ] **Step 2: 新增 `_get_token_from_worker` 方法**

在 `_login` 方法之前（约第 67 行），新增方法：

```python
def _get_token_from_worker(self) -> Optional[Dict[str, str]]:
    """从 worker 获取 UI User 端已有的 token。

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

    try:
        result = client.execute(
            platform=ui_platform,
            actions=[{"action_type": "get_token"}]
        )

        if result.get("status") == "SUCCESS" and result.get("actions"):
            output = result["actions"][0].get("output", "")
            if output:
                try:
                    return json.loads(output)
                except json.JSONDecodeError:
                    return None
    except Exception:
        # worker 调用失败，返回 None
        return None

    return None
```

- [ ] **Step 3: 提交 `_get_token_from_worker` 方法**

```bash
git add aw/api/base_api_aw.py
git commit -m "feat(base_api_aw): 新增 _get_token_from_worker 方法"
```

---

### Task 4: BaseApiAW 修改 - 修改 `_ensure_token` 方法

**Files:**
- Modify: `aw/api/base_api_aw.py:126-139`

- [ ] **Step 1: 修改 `_ensure_token` 方法**

修改 `_ensure_token` 方法，增加优先从 worker 获取 token 的逻辑：

```python
def _ensure_token(self) -> str:
    """确保 token 有效，返回 access_token。

    如果 token 不存在或已过期：
    1. 优先尝试从 worker get_token 获取 UI User 的 token
    2. 如果获取成功则直接使用
    3. 如果获取失败则执行原有 API 登录

    Returns:
        access_token 字符串。
    """
    if self._token_info and time.time() < self._token_info.expire_time:
        return self._token_info.access_token

    # 优先尝试从 worker 获取 UI User 的 token
    if self.user and self.user._ui_user_id:
        token_dict = self._get_token_from_worker()
        if token_dict:
            # 使用从 worker 获取的 token
            access_token = token_dict.get("X-Auth-Token")
            if access_token:
                # 设置一个较短的过期时间（5分钟），因为 UI token 可能随时失效
                expire_time = time.time() + 300
                self._token_info = TokenInfo(
                    access_token=access_token,
                    expire_time=expire_time,
                    user_uuid=""
                )
                return access_token

    # fallback 到原有 API 登录
    token_info = self._login()
    return token_info.access_token
```

- [ ] **Step 2: 提交 `_ensure_token` 修改**

```bash
git add aw/api/base_api_aw.py
git commit -m "feat(base_api_aw): _ensure_token 优先从 worker 获取 token"
```

---

### Task 5: BaseApiAW 修改 - 修改 `_request_with_log` 的 401 处理

**Files:**
- Modify: `aw/api/base_api_aw.py:143-266`

- [ ] **Step 1: 在 `_request_with_log` 中添加 x-request-id header**

在合并 headers 之后、添加 token 之前（约第 179 行），添加：

```python
# 添加 x-request-id header（随机 UUID）
final_headers["x-request-id"] = str(uuid.uuid4())
```

- [ ] **Step 2: 修改 401 处理逻辑**

修改 `_request_with_log` 方法中的 401 处理部分（约第 202-235 行）：

```python
# 401 时尝试从 worker 获取 token 或重新登录
if response.status_code == 401 and need_token:
    # 清除缓存的 token
    self._token_info = None

    # 尝试从 worker 获取 UI User 的 token
    worker_token = None
    if self.user and self.user._ui_user_id:
        worker_token = self._get_token_from_worker()

    if worker_token:
        # 使用 worker token 重试
        access_token = worker_token.get("X-Auth-Token")
        if access_token:
            final_headers["x-auth-token"] = access_token
            final_headers["x-access-token"] = access_token
            response = self._session.request(
                method=method,
                url=url,
                headers=final_headers,
                params=params,
                json=json_data,
                timeout=timeout,
                verify=False
            )

            # worker token 也 401，则执行 API login
            if response.status_code == 401:
                token = self._ensure_token()
                final_headers["x-auth-token"] = token
                final_headers["x-access-token"] = token
                response = self._session.request(
                    method=method,
                    url=url,
                    headers=final_headers,
                    params=params,
                    json=json_data,
                    timeout=timeout,
                    verify=False
                )
    else:
        # 没有 UI User 或 get_token 失败，执行 API login 重试
        token = self._ensure_token()
        final_headers["x-auth-token"] = token
        final_headers["x-access-token"] = token
        response = self._session.request(
            method=method,
            url=url,
            headers=final_headers,
            params=params,
            json=json_data,
            timeout=timeout,
            verify=False
        )

    duration_ms = int((time.time() - start_time) * 1000)
    success = response.ok

    # 记录重试日志
    retry_reason = "worker_token" if worker_token else "api_login"
    logger.log_aw_call(
        aw_name=self._aw_name,
        method=f"{method}_retry_after_401_{retry_reason}",
        args=log_args,
        success=success,
        result={"status_code": response.status_code, "body": response.text[:500]},
        duration_ms=duration_ms
    )

    if not success:
        raise ApiError(method, response.status_code, response.text[:200])

    return response
```

- [ ] **Step 3: 提交 `_request_with_log` 修改**

```bash
git add aw/api/base_api_aw.py
git commit -m "feat(base_api_aw): 401 处理优先使用 worker token，新增 x-request-id header"
```

---

### Task 6: 验证测试

**Files:**
- Run: 验证现有测试是否通过

- [ ] **Step 1: 运行现有测试验证修改不影响原有功能**

```bash
source .venv/bin/activate && pytest testcases/web/test_login_success.py -v
```

Expected: 测试通过或能正常运行（可能有环境相关因素）

- [ ] **Step 2: 检查代码语法**

```bash
python -m py_compile common/user.py aw/api/base_api_aw.py conftest.py
```

Expected: 无语法错误

- [ ] **Step 3: 最终提交**

如果所有修改已完成且验证通过：

```bash
git add -A
git status  # 确认所有修改已提交
```

---

## 完成检查

- [ ] User 类新增 `_ui_user_id`、`_user_instances_ref` 属性
- [ ] User 类新增 `_get_ui_client`、`_get_ui_platform` 方法
- [ ] conftest.py 创建 API User 时传入 `_ui_user_id` 并设置 `_user_instances_ref`
- [ ] BaseApiAW 新增 `_get_token_from_worker` 方法
- [ ] BaseApiAW `_ensure_token` 优先从 worker 获取 token
- [ ] BaseApiAW `_request_with_log` 401 处理优化
- [ ] 所有请求添加 `x-request-id` header
- [ ] 现有测试验证通过