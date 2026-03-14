# AGENTS.md — 测试用例工程项目规范

本文档定义了 testcase 工程的架构、命名规范和编码约定。所有 Skill 生成的代码必须遵循本规范。

---

## 一、项目架构

### 1.1 整体架构

```
testcase/
├── common/           # 公共模块
│   ├── testagent_client.py   # testagent HTTP 客户端
│   ├── assertions.py         # 断言函数
│   ├── data_factory.py       # 测试数据工厂
│   ├── config_loader.py      # 配置加载器
│   ├── user_manager.py       # 用户资源管理器
│   └── utils.py              # 工具函数
│
├── windows/          # Windows 端
│   ├── aw/           # 业务操作封装层
│   └── testcase/     # 测试用例
│
├── web/              # Web 端
├── mac/              # Mac 端
├── ios/              # iOS 端
└── android/          # Android 端
```

### 1.2 两层架构

本工程采用 **AW 层 + testcase 层** 的两层架构：

| 层级 | 目录 | 职责 | 使用者 |
|------|------|------|--------|
| AW 层 | `{端}/aw/` | 封装多步骤业务流程，调用 testagent HTTP API | 测试开发 |
| testcase 层 | `{端}/testcase/` | 测试用例业务代码，调用 AW 层方法 | 测试人员 |

**核心原则**：
- **测试人员只关注 testcase 层**，通过调用 AW 层方法完成测试
- **AW 层封装底层细节**，通过 HTTP 调用 testagent 服务
- **testcase 层不直接调用 testagent**，保持关注点分离

### 1.3 与 testagent 工程的关系

```
┌─────────────────────────────────────────────┐
│            testcase 工程（本工程）            │
│  ┌─────────────┐     ┌─────────────────┐    │
│  │ testcase 层 │ ──▶ │     AW 层       │    │
│  └─────────────┘     └────────┬────────┘    │
└───────────────────────────────┼─────────────┘
                                │ HTTP API
                                ▼
┌─────────────────────────────────────────────┐
│           testagent 工程（已封装）            │
│   Web / Win / Mac / iOS / Android 操作      │
└─────────────────────────────────────────────┘
```

---

## 二、命名规范

### 2.1 文件命名

| 类型 | 命名规则 | 示例 |
|------|----------|------|
| AW 文件 | `{业务名}_aw.py` | `login_aw.py`, `order_aw.py` |
| 测试文件 | `test_{功能名}_{场景}.py` | `test_login_success.py`, `test_login_wrong_password.py` |

**核心原则：一个测试文件 = 一条测试用例**

### 2.2 类命名

| 类型 | 命名规则 | 示例 |
|------|----------|------|
| AW 类 | `{业务名}AW` | `LoginAW`, `OrderAW` |
| 测试类 | `Test{功能}{场景}` | `TestLoginSuccess`, `TestLoginWrongPassword` |

### 2.3 方法命名

| 类型 | 命名规则 | 示例 |
|------|----------|------|
| AW 方法 | `do_{业务动作}` | `do_login()`, `do_logout()`, `do_create_order()` |
| AW 断言方法 | `should_{期望结果}` | `should_login_success()`, `should_show_error()` |
| 测试方法 | `test_execute` | 固定方法名 |

---

## 三、AW 层编码规范

### 3.1 AW 类结构

```python
"""
{业务名} 业务操作封装。

{简述封装的业务流程}
"""

from common.testagent_client import TestagentClient


class XxxAW:
    """{业务中文名}业务操作封装。

    Args:
        client: TestagentClient 实例。
    """

    PLATFORM = "{端}"  # windows / web / mac / ios / android

    def __init__(self, client: TestagentClient):
        self.client = client

    # ── 业务流程方法 ─────────────────────────────────────────

    def do_xxx(self, param1: str, param2: str) -> None:
        """{业务动作描述}。

        步骤: 步骤1 → 步骤2 → 步骤3。

        Args:
            param1: 参数1说明。
            param2: 参数2说明。
        """
        # 调用 testagent_client 执行操作（使用 OCR 识别）
        self.client.ocr_input(self.PLATFORM, param1, offset={"x": 100, "y": 0})
        self.client.ocr_input(self.PLATFORM, param2, offset={"x": 100, "y": 0})
        self.client.ocr_click(self.PLATFORM, "提交")

    # ── 断言方法 ─────────────────────────────────────────────

    def should_xxx_success(self) -> None:
        """断言{期望结果}。"""
        result = self.client.ocr_wait(self.PLATFORM, "成功", match_mode="contains")
        assert self.client.is_success(result), "操作未成功"
```

### 3.2 AW 方法规范

1. **业务流程方法以 `do_` 开头**：表示执行一个业务动作
2. **断言方法以 `should_` 开头**：表示验证一个期望结果
3. **每个业务方法必须有中文 docstring**：说明步骤和参数
4. **使用 `self.PLATFORM` 常量**：避免硬编码平台名
5. **优先使用 OCR 操作**：`ocr_click`, `ocr_input`, `ocr_wait` 等跨平台通用方法

### 3.3 操作方法说明

testagent 支持 OCR 识别、图像识别和坐标操作三种方式：

| 方法 | 说明 | 适用场景 |
|------|------|----------|
| `ocr_click(platform, text)` | OCR 识别文字并点击 | 跨平台通用，推荐 |
| `ocr_input(platform, text, offset)` | OCR 定位后输入内容 | 输入框操作 |
| `ocr_wait(platform, text)` | 等待文字出现 | 同步等待、断言 |
| `ocr_assert(platform, text)` | 断言文字存在 | 验证结果 |
| `image_click(platform, image_path)` | 图像识别点击 | 图标、按钮等 |
| `click(platform, x, y)` | 坐标点击 | 精确位置 |
| `swipe(platform, direction)` | 滑动操作 | 移动端 |
| `navigate(platform, url)` | 导航 URL | Web 端 |
| `launch_app(platform, bundle_id)` | 启动应用 | 移动端/桌面端 |

---

## 四、testcase 层编码规范

### 4.1 测试类结构

**核心原则**：
- 一个测试文件 = 一条测试用例
- 测试用例使用 `@pytest.mark.users()` 标记声明用户需求
- 测试方法通过 `users` 参数获取用户资源

```python
"""
{用例标题}测试用例。

测试场景: {场景描述}
"""

import pytest

from common.testagent_client import TestagentClient
from {端}.aw.xxx_aw import XxxAW


@pytest.mark.users({"userA": "{端}"})
class Test{功能}{场景}:
    """{用例标题}测试。"""

    def test_execute(self, users):
        """执行测试：{操作}，应{结果}。"""
        user = users["userA"]

        client = TestagentClient()
        xxx_aw = XxxAW(client, user=user)
        xxx_aw.do_xxx()  # 使用 user 资源
        xxx_aw.should_xxx_success()
```

### 4.2 测试方法规范

1. **测试方法命名**：统一使用 `test_execute`
2. **docstring 格式**：`执行测试：{操作}，应{结果}`
3. **测试方法只调用 AW 层**：不直接调用 testagent_client
4. **每个测试文件独立**：一个文件对应一条用例

---

## 五、断言规范

### 5.1 使用 common/assertions.py

优先使用公共断言函数：

```python
from common.assertions import assert_text_contains, assert_response_ok

# 断言文本包含
assert_text_contains(text, "成功")

# 断言响应成功
assert_response_ok(response)
```

### 5.2 AW 层断言

AW 层应提供 `should_*` 断言方法，使用 OCR 断言：

```python
def should_login_success(self) -> None:
    """断言登录成功。"""
    result = self.client.ocr_wait(self.PLATFORM, "欢迎", timeout=10000)
    assert self.client.is_success(result), f"登录未成功"
```

### 5.3 断言消息规范

断言失败时应提供清晰的错误信息：

```python
# 好
assert actual == expected, f"值不匹配: 期望 '{expected}', 实际 '{actual}'"

# 不好
assert actual == expected
```

---

## 六、目录结构规范

### 6.1 按功能划分文件

```
web/
├── aw/
│   ├── login_aw.py        # 登录业务
│   ├── order_aw.py        # 订单业务
│   └── user_aw.py         # 用户管理业务
└── testcase/
    ├── test_login_success.py         # 登录成功用例
    ├── test_login_wrong_password.py  # 密码错误用例
    └── test_order_create_success.py  # 创建订单用例
```

### 6.2 避免过深的目录层级

测试用例文件按功能模块划分，但 **不超过两级目录**：

```
# 推荐
web/testcase/test_login_success.py
web/testcase/test_order_create_success.py

# 不推荐（层级过深）
web/testcase/user/test_login.py
web/testcase/order/create/test_create_order.py
```

---

## 七、代码风格

### 7.1 Import 顺序

```python
# 标准库
import json
from typing import Dict, Optional

# 第三方库
import pytest
import requests

# 本地模块
from common.testagent_client import TestagentClient
from common.assertions import assert_response_ok
```

### 7.2 Docstring 格式

使用 Google 风格的 docstring：

```python
def do_login(self, username: str, password: str) -> None:
    """执行登录操作。

    步骤: 打开登录页 → 输入用户名 → 输入密码 → 点击登录。

    Args:
        username: 用户名。
        password: 密码。

    Raises:
        TestagentError: 操作执行失败时抛出。
    """
```

### 7.3 类型注解

所有 public 方法应添加类型注解：

```python
def do_login(self, username: str, password: str) -> None:
    ...

def get_user_info(self, user_id: int) -> Dict[str, Any]:
    ...
```

---

## 八、示例代码

### 8.1 完整 AW 示例

```python
"""
登录业务操作封装。

封装登录、登出等用户认证相关流程。
"""

from typing import Optional

from common.testagent_client import TestagentClient
from common.user_manager import UserResource


class LoginAW:
    """登录业务操作封装。

    Args:
        client: TestagentClient 实例。
        user: 用户资源实例（可选）。
    """

    PLATFORM = "web"

    def __init__(
        self,
        client: TestagentClient,
        user: Optional[UserResource] = None
    ):
        self.client = client
        self.user = user

    # ── 业务流程方法 ─────────────────────────────────────────

    def do_navigate_to_login(self, url: str) -> None:
        """导航到登录页面。

        步骤: 使用浏览器导航到指定的登录 URL。

        Args:
            url: 登录页面 URL。
        """
        self.client.navigate(self.PLATFORM, url)

    def do_login(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None
    ) -> None:
        """执行登录操作。

        步骤: 输入用户名 → 输入密码 → 点击登录按钮。

        优先使用传入参数，其次使用 user 资源。

        Args:
            username: 用户名（可选）。
            password: 密码（可选）。

        Raises:
            ValueError: 未提供账号密码且无用户资源时抛出。
        """
        account = username or (self.user.account if self.user else None)
        pwd = password or (self.user.password if self.user else None)

        if not account or not pwd:
            raise ValueError("未提供账号密码，且无用户资源")

        self.client.ocr_input(self.PLATFORM, account, offset={"x": 100, "y": 0})
        self.client.ocr_input(self.PLATFORM, pwd, offset={"x": 100, "y": 0})
        self.client.ocr_click(self.PLATFORM, "登录")

    def do_accept_privacy(self) -> None:
        """接受隐私政策。

        步骤: 点击同意按钮。
        """
        self.client.ocr_click(self.PLATFORM, "同意")

    # ── 断言方法 ─────────────────────────────────────────────

    def should_login_success(self) -> None:
        """断言登录成功。"""
        result = self.client.ocr_wait(self.PLATFORM, "会议", timeout=10000)
        assert self.client.is_success(result), "登录失败"

    def should_show_error(self, error_msg: str) -> None:
        """断言显示错误提示。

        Args:
            error_msg: 期望的错误信息。
        """
        result = self.client.ocr_wait(self.PLATFORM, error_msg, timeout=5000, match_mode="contains")
        assert self.client.is_success(result), f"未显示错误提示: {error_msg}"
```

### 8.2 完整测试用例示例

```python
"""
正确账号密码登录成功测试用例。

测试场景: 使用动态申请的用户资源登录华为云会议 Web 端
"""

import pytest

from common.testagent_client import TestagentClient
from web.aw.login_aw import LoginAW


@pytest.mark.users({"userA": "web"})
class TestLoginSuccess:
    """正确账号密码登录成功测试。"""

    def test_execute(self, users):
        """执行测试：正确账号密码登录，应登录成功。"""
        user = users["userA"]

        client = TestagentClient()
        login_aw = LoginAW(client, user=user)
        login_aw.do_navigate_to_login("https://meeting.huaweicloud.com/#/login")
        login_aw.do_login()  # 使用 user 资源，无需传参
        login_aw.do_accept_privacy()
        login_aw.should_login_success()
```

---

## 九、Skill 生成代码检查清单

当 testcase-coder Skill 生成代码时，必须确保：

- [ ] AW 文件命名符合 `{业务名}_aw.py` 格式
- [ ] AW 类命名符合 `{业务名}AW` 格式
- [ ] AW 方法以 `do_` 或 `should_` 开头
- [ ] 测试文件命名符合 `test_{功能名}_{场景}.py` 格式
- [ ] 测试类命名符合 `Test{功能}{场景}` 格式
- [ ] 测试方法使用 `test_execute`
- [ ] 所有类和方法有中文 docstring
- [ ] 测试方法只调用 AW 层，不直接调用 testagent_client
- [ ] 测试用例使用 `@pytest.mark.users()` 标记声明用户需求
- [ ] import 路径正确，模块存在

---

## 十、用户资源管理

### 10.1 概述

测试用例不再硬编码账号密码，而是通过 `@pytest.mark.users()` 标记声明用户需求，运行时自动从资源管理服务申请用户机器资源。

**核心流程**：

```
测试用例声明 @pytest.mark.users({"userA": "web", "userB": "windows"})
                    ↓
pytest fixture (users) 拦截
                    ↓
UserManager.apply() → POST /env/create → 返回用户资源
                    ↓
测试执行，使用 users["userA"].account 等属性
                    ↓
测试结束，UserManager.release() → POST /env/release
```

### 10.2 标记声明

在测试类上使用 `@pytest.mark.users()` 标记声明用户需求：

| 标记示例 | 说明 |
|----------|------|
| `@pytest.mark.users({"userA": "web"})` | 申请 1 个 Web 端用户 |
| `@pytest.mark.users({"userA": "web", "userB": "windows"})` | 申请 2 个不同端用户 |
| `@pytest.mark.users({"userA": "ios", "userB": "android"})` | 移动端跨平台测试 |

### 10.3 在测试方法中使用

测试方法通过 `users` 参数获取已申请的资源：

```python
@pytest.mark.users({"userA": "web"})
class TestLoginSuccess:
    """登录成功测试。"""

    def test_execute(self, users):
        """执行测试。"""
        user = users["userA"]

        # 获取用户资源属性
        account = user.account    # 账号
        password = user.password  # 密码
        platform = user.platform  # 平台
        ip = user.ip              # 机器 IP

        # 传入 AW 实例
        client = TestagentClient()
        login_aw = LoginAW(client, user=user)
        login_aw.do_login()  # 无需传参，使用 user 资源
```

### 10.4 多用户场景

跨平台测试场景示例：

```python
@pytest.mark.users({"userA": "web", "userB": "windows"})
class TestCrossPlatformCall:
    """跨平台通话测试。"""

    def test_execute(self, users):
        """执行测试：Web 呼叫 Windows，应通话成功。"""
        caller = users["userA"]  # Web 端主叫
        callee = users["userB"]  # Windows 端被叫

        # 创建两个客户端和 AW 实例
        web_client = TestagentClient()
        win_client = TestagentClient()

        web_call_aw = CallAW(web_client, user=caller)
        win_call_aw = CallAW(win_client, user=callee)

        # 执行测试...
```

### 10.5 AW 层适配

AW 类构造函数支持可选 `user` 参数：

```python
from typing import Optional
from common.user_manager import UserResource


class XxxAW:
    """业务操作封装。

    Args:
        client: TestagentClient 实例。
        user: 用户资源实例（可选）。
    """

    def __init__(
        self,
        client: TestagentClient,
        user: Optional[UserResource] = None
    ):
        self.client = client
        self.user = user
```

业务方法优先使用 user 资源：

```python
def do_login(
    self,
    username: Optional[str] = None,
    password: Optional[str] = None
) -> None:
    """执行登录操作。

    优先使用传入参数，其次使用 user 资源。

    Args:
        username: 用户名（可选）。
        password: 密码（可选）。

    Raises:
        ValueError: 未提供账号密码且无用户资源时抛出。
    """
    account = username or (self.user.account if self.user else None)
    pwd = password or (self.user.password if self.user else None)

    if not account or not pwd:
        raise ValueError("未提供账号密码，且无用户资源")

    self.client.ocr_input(self.PLATFORM, account, offset={"x": 100, "y": 0})
    self.client.ocr_input(self.PLATFORM, pwd, offset={"x": 100, "y": 0})
    self.client.ocr_click(self.PLATFORM, "登录")
```

### 10.6 配置

在 `config.yaml` 中配置资源管理服务地址：

```yaml
resource_manager:
  base_url: "http://resource-server:8080"
  timeout: 30
  # 本地调试模式：预设用户资源（当 base_url 为空时生效）
  mock_users:
    userA:
      account: "test_user_a"
      password: "Password@123"
      ip: "127.0.0.1"
      type: "normal"
```

或通过环境变量覆盖：

```bash
export RESOURCE_MANAGER_URL="http://resource-server:8080"
```

### 10.7 UserResource 属性

`UserResource` 数据类提供以下属性：

| 属性 | 类型 | 说明 |
|------|------|------|
| `user_id` | str | 用户标识，如 userA、userB |
| `platform` | str | 平台类型，如 web、windows |
| `ip` | str | 机器 IP 地址 |
| `account` | str | 登录账号 |
| `password` | str | 登录密码 |
| `user_type` | str | 用户类型，如 normal、admin |
| `extra` | Dict | 扩展信息 |

### 10.8 资源生命周期

- **申请时机**：测试方法执行前，`users` fixture 自动申请
- **释放时机**：测试方法执行后（无论成功或失败），自动释放
- **隔离性**：每条测试用例独立申请和释放资源，互不影响