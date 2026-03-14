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
│   └── utils.py              # 工具函数
│
├── windows/          # Windows 端
│   ├── aw/           # 业务操作封装层
│   ├── testcase/     # 测试用例
│   └── conftest.py   # 端级 fixtures
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
| 测试文件 | `test_{功能名}.py` | `test_login.py`, `test_order.py` |
| conftest | `conftest.py` | 固定名称 |

### 2.2 类命名

| 类型 | 命名规则 | 示例 |
|------|----------|------|
| AW 类 | `{业务名}AW` | `LoginAW`, `OrderAW` |
| 测试类 | `Test{功能名}` | `TestLogin`, `TestOrder` |

### 2.3 方法命名

| 类型 | 命名规则 | 示例 |
|------|----------|------|
| AW 方法 | `do_{业务动作}` | `do_login()`, `do_logout()`, `do_create_order()` |
| AW 断言方法 | `should_{期望结果}` | `should_login_success()`, `should_show_error()` |
| 测试方法 | `test_{场景描述}` | `test_login_success()`, `test_login_with_wrong_password()` |

### 2.4 fixture 命名

| 类型 | 命名规则 | 示例 |
|------|----------|------|
| 客户端 fixture | `{端}_client` | `windows_client`, `web_client` |
| AW fixture | `{业务名}_aw` | `login_aw`, `order_aw` |
| 配置 fixture | `{端}_config` | `windows_config`, `web_config` |

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
        self.client.ocr_wait(self.PLATFORM, "成功", match_mode="contains")
```

### 3.2 AW 方法规范

1. **业务流程方法以 `do_` 开头**：表示执行一个业务动作
2. **断言方法以 `should_` 开头**：表示验证一个期望结果
3. **每个业务方法必须有中文 docstring**：说明步骤和参数
4. **使用 `self.PLATFORM` 常量**：避免硬编码平台名
5. **优先使用 OCR 操作**：`ocr_click`, `ocr_input`, `ocr_wait` 等跨平台通用方法
6. **需要会话复用时使用 session_id**：调用 `create_session()` 创建会话

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

```python
"""
{功能名称}测试用例。

测试范围: {简述测试覆盖的功能}
"""

import pytest

from {端}.aw.login_aw import LoginAW


@pytest.mark.{端}  # windows / web / mac / ios / android
class TestXxx:
    """{功能}测试集。"""

    def test_xxx_success(self, {端}_client, login_aw):
        """正常场景：{操作}，应{结果}。"""
        login_aw.do_login("testuser", "Test@123")
        login_aw.should_login_success()

    def test_xxx_with_error(self, {端}_client, login_aw):
        """异常场景：{操作}，应{结果}。"""
        login_aw.do_login("testuser", "wrong_password")
        login_aw.should_show_error("密码错误")
```

### 4.2 测试方法规范

1. **测试方法命名**：`test_{场景描述}`
   - 正常场景：`test_login_success`, `test_create_order_success`
   - 异常场景：`test_login_with_wrong_password`, `test_create_order_without_required_field`

2. **docstring 格式**：`{场景类型}：{操作}，应{结果}`
   - 示例：`"""正常场景：正确账号密码登录，应跳转首页。"""`
   - 示例：`"""异常场景：密码错误登录，应显示错误提示。"""`

3. **测试方法只调用 AW 层**：不直接调用 testagent_client
4. **每个测试方法独立**：不依赖其他测试方法的执行结果
5. **使用 pytest.mark 标记**：
   - 端标记：`@pytest.mark.windows`, `@pytest.mark.web` 等
   - 类型标记：`@pytest.mark.smoke`, `@pytest.mark.regression`

### 4.3 测试用例优先级

| 优先级 | 标记 | 说明 | 示例 |
|--------|------|------|------|
| P0 | `@pytest.mark.smoke` | 冒烟测试 | 核心功能主流程 |
| P1 | 无特殊标记 | 核心功能 | 正常场景 + 主要异常 |
| P2 | `@pytest.mark.regression` | 回归测试 | 边界值、次要场景 |

---

## 五、fixture 规范

### 5.1 fixture 定义位置

| fixture 类型 | 定义位置 | scope |
|--------------|----------|-------|
| 全局配置 | `conftest.py` (根目录) | session |
| 端级客户端/配置 | `{端}/conftest.py` | session |
| AW fixture | `{端}/conftest.py` | function |

### 5.2 AW fixture 定义

在 `{端}/conftest.py` 中注册 AW fixture：

```python
@pytest.fixture
def login_aw(windows_client) -> LoginAW:
    """登录业务操作封装。

    Returns:
        LoginAW 实例。
    """
    return LoginAW(windows_client)
```

### 5.3 fixture 使用示例

```python
@pytest.mark.windows
class TestLogin:
    """登录测试集。"""

    def test_login_success(self, windows_client, login_aw):
        """正常场景：正确账号密码登录，应登录成功。"""
        login_aw.do_login("testuser", "Test@123")
        login_aw.should_login_success()
```

---

## 六、断言规范

### 6.1 使用 common/assertions.py

优先使用公共断言函数：

```python
from common.assertions import assert_text_contains, assert_response_ok

# 断言文本包含
assert_text_contains(text, "成功")

# 断言响应成功
assert_response_ok(response)
```

### 6.2 AW 层断言

AW 层应提供 `should_*` 断言方法，使用 OCR 断言：

```python
def should_login_success(self) -> None:
    """断言登录成功。"""
    result = self.client.ocr_wait(self.PLATFORM, "欢迎", timeout=10000)
    assert self.client.is_success(result), f"登录未成功"
```

### 6.3 断言消息规范

断言失败时应提供清晰的错误信息：

```python
# 好
assert actual == expected, f"值不匹配: 期望 '{expected}', 实际 '{actual}'"

# 不好
assert actual == expected
```

---

## 七、目录结构规范

### 7.1 按功能划分文件

当测试用例增多时，按功能模块划分文件：

```
web/
├── aw/
│   ├── login_aw.py        # 登录业务
│   ├── order_aw.py        # 订单业务
│   └── user_aw.py         # 用户管理业务
├── testcase/
│   ├── test_login.py      # 登录测试
│   ├── test_order.py      # 订单测试
│   └── test_user.py       # 用户管理测试
└── conftest.py
```

### 7.2 避免过深的目录层级

测试用例文件按功能模块划分，但 **不超过两级目录**：

```
# 推荐
web/testcase/test_login.py
web/testcase/test_order.py

# 不推荐（层级过深）
web/testcase/user/test_login.py
web/testcase/order/create/test_create_order.py
```

---

## 八、代码风格

### 8.1 Import 顺序

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

### 8.2 Docstring 格式

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

### 8.3 类型注解

所有 public 方法应添加类型注解：

```python
def do_login(self, username: str, password: str) -> None:
    ...

def get_user_info(self, user_id: int) -> Dict[str, Any]:
    ...
```

---

## 九、测试端对应关系

| 端 | 目录 | fixture 前缀 | pytest.mark |
|------|------|--------------|-------------|
| Windows | `windows/` | `windows_` | `@pytest.mark.windows` |
| Web | `web/` | `web_` | `@pytest.mark.web` |
| Mac | `mac/` | `mac_` | `@pytest.mark.mac` |
| iOS | `ios/` | `ios_` | `@pytest.mark.ios` |
| Android | `android/` | `android_` | `@pytest.mark.android` |

---

## 十、示例代码

### 10.1 完整 AW 示例

```python
"""
登录业务操作封装。

封装登录、登出等用户认证相关流程。
"""

from common.testagent_client import TestagentClient


class LoginAW:
    """登录业务操作封装。

    Args:
        client: TestagentClient 实例。
    """

    PLATFORM = "web"

    def __init__(self, client: TestagentClient):
        self.client = client

    # ── 业务流程方法 ─────────────────────────────────────────

    def do_login(self, username: str, password: str) -> None:
        """执行登录操作。

        步骤: 输入用户名 → 输入密码 → 点击登录按钮。

        Args:
            username: 用户名。
            password: 密码。
        """
        # 使用 OCR 识别并输入
        self.client.ocr_input(self.PLATFORM, username, offset={"x": 100, "y": 0})
        self.client.ocr_input(self.PLATFORM, password, offset={"x": 100, "y": 0})
        self.client.ocr_click(self.PLATFORM, "登录")

    def do_logout(self) -> None:
        """执行登出操作。

        步骤: 点击用户菜单 → 点击退出登录。
        """
        self.client.ocr_click(self.PLATFORM, "用户")
        self.client.ocr_click(self.PLATFORM, "退出")

    # ── 断言方法 ─────────────────────────────────────────────

    def should_login_success(self) -> None:
        """断言登录成功。"""
        result = self.client.ocr_wait(self.PLATFORM, "欢迎", timeout=10000)
        assert self.client.is_success(result), "登录失败"

    def should_show_error(self, error_msg: str) -> None:
        """断言显示错误提示。

        Args:
            error_msg: 期望的错误信息。
        """
        result = self.client.ocr_wait(self.PLATFORM, error_msg, timeout=5000, match_mode="contains")
        assert self.client.is_success(result), f"未显示错误提示: {error_msg}"
```

### 10.2 完整测试用例示例

```python
"""
登录功能测试用例。

测试范围: 用户登录功能，包括正常登录、异常登录场景。
"""

import pytest

from common.data_factory import DataFactory


@pytest.mark.web
class TestLogin:
    """登录测试集。"""

    @pytest.mark.smoke
    def test_login_success(self, web_client, login_aw):
        """正常场景：正确账号密码登录，应登录成功。"""
        user = DataFactory.get_test_user("user")
        login_aw.do_login(user["username"], user["password"])
        login_aw.should_login_success()

    def test_login_with_wrong_password(self, web_client, login_aw):
        """异常场景：密码错误登录，应显示错误提示。"""
        login_aw.do_login("testuser", "wrong_password")
        login_aw.should_show_error("密码错误")

    def test_login_with_empty_username(self, web_client, login_aw):
        """异常场景：用户名为空，应显示提示。"""
        login_aw.do_login("", "Test@123")
        login_aw.should_show_error("请输入用户名")
```

---

## 十一、Skill 生成代码检查清单

当 testcase-coder Skill 生成代码时，必须确保：

- [ ] AW 文件命名符合 `{业务名}_aw.py` 格式
- [ ] AW 类命名符合 `{业务名}AW` 格式
- [ ] AW 方法以 `do_` 或 `should_` 开头
- [ ] 测试文件命名符合 `test_{功能名}.py` 格式
- [ ] 测试类命名符合 `Test{功能名}` 格式
- [ ] 测试方法以 `test_` 开头
- [ ] 所有类和方法有中文 docstring
- [ ] 测试方法只调用 AW 层，不直接调用 testagent_client
- [ ] 使用正确的端标记（`@pytest.mark.{端}`）
- [ ] 在 conftest.py 中注册新的 AW fixture
- [ ] import 路径正确，模块存在