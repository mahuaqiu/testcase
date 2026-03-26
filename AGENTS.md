# AGENTS.md — 测试用例工程项目规范

本文档定义了 testcase 工程的架构、命名规范和编码约定。所有 Skill 生成的代码必须遵循本规范。

---

## 一、项目架构

### 1.1 两层架构

| 层级 | 目录 | 职责 |
|------|------|------|
| AW 层 | `aw/{平台}/` | 封装业务流程，继承 BaseAW |
| testcases 层 | `testcases/{平台}/` | 测试用例，通过 User 调用 AW 方法 |

**核心原则**：
- 测试用例通过 User 实例调用 AW 方法（`user.do_login()`）
- AW 类继承 BaseAW，使用便捷方法（`self.ocr_click(text)`）
- API 平台独立：`users["userA_api"]` 提供 HTTP API 能力

### 1.2 目录结构

```
testcases/
├── {平台}/
│   └── {业务模块}/
│       └── test_*.py
└── integration/

aw/
├── base_aw.py               # UI 操作 AW 基类
├── api/base_api_aw.py       # API 操作 AW 基类
├── common/                  # 公共 AW
├── api/                     # API 平台 AW
└── {平台}/                   # windows/web/mac/ios/android
    └── {业务模块}_aw.py
```

---

## 二、命名规范

| 类型 | 命名规则 | 示例 |
|------|----------|------|
| AW 文件 | `{业务名}_aw.py` | `login_aw.py` |
| AW 类 | `{业务名}AW` | `LoginAW` |
| AW 业务方法 | `do_{动作}` | `do_login()` |
| AW 断言方法 | `should_{期望}` | `should_login_success()` |
| 测试文件 | `test_{功能}_{场景}_{编号}.py` | `test_login_success_001.py` |
| 测试类 | `TestClass` | 固定名称 |
| 测试方法 | `test_{文件名}` | `test_login_success_001` |

**核心原则：一个测试文件 = 一条测试用例**

---

## 三、AW 层编码规范

### 3.1 AW 类结构

```python
"""
{业务名}业务操作封装。
"""

from aw.base_aw import BaseAW


class XxxAW(BaseAW):
    """{业务中文名}业务操作封装。"""

    PLATFORM = "{端}"  # windows / web / mac / ios / android

    # ── 业务流程方法 ─────────────────────────────────────────

    def do_xxx(self, param: str) -> None:
        """执行{业务动作}。

        步骤: 步骤1 → 步骤2 → 步骤3。

        Args:
            param: 参数说明。
        """
        # 使用 BaseAW 便捷方法，无需传 platform
        self.ocr_input("用户名", param)
        self.ocr_click("提交")

    # ── 断言方法 ─────────────────────────────────────────────

    def should_xxx_success(self) -> None:
        """断言{期望结果}。"""
        self.ocr_wait("成功", timeout=5000)
```

### 3.2 AW 方法规范

1. **业务方法以 `do_` 开头**：表示执行一个业务动作
2. **断言方法以 `should_` 开头**：表示验证一个期望结果
3. **每个方法必须有中文 docstring**：说明步骤和参数
4. **使用 `self.PLATFORM` 常量**：避免硬编码平台名
5. **使用 BaseAW 便捷方法**：`self.ocr_click(text)` 而非 `self.client.ocr_click(self.PLATFORM, text)`

### 3.3 BaseAW 便捷方法

BaseAW 封装了 testagent_client 调用，自动传入 platform，失败时抛出 AWError：

| 方法 | 说明 |
|------|------|
| `ocr_click(text, **kwargs)` | OCR 识别并点击 |
| `ocr_input(label, content, **kwargs)` | OCR 定位后输入 |
| `ocr_wait(text, **kwargs)` | 等待文字出现 |
| `ocr_assert(text, **kwargs)` | 断言文字存在 |
| `ocr_get_text(**kwargs)` | 获取屏幕所有文字 |
| `ocr_paste(text, content, **kwargs)` | OCR 定位后粘贴 |
| `image_click(image_path, **kwargs)` | 图像识别点击 |
| `image_wait(image_path, **kwargs)` | 等待图像出现 |
| `image_click_near_text(image_path, text, **kwargs)` | 点击文本附近图像 |
| `click(x, y)` | 坐标点击 |
| `swipe(from_x, from_y, to_x, to_y, **kwargs)` | 滑动操作 |
| `input_text(x, y, text)` | 在指定坐标输入 |
| `press(key)` | 按键操作 |
| `wait(duration_ms)` | 固定等待 |
| `screenshot()` | 截图（返回 base64） |
| `start_app(app_id)` | 启动应用 |
| `stop_app(app_id)` | 关闭应用 |
| `navigate(url)` | 导航 URL（Web） |

---

## 四、testcase 层编码规范

### 4.1 测试类结构

```python
"""
{用例标题}测试用例。

测试场景: {场景描述}
"""

import pytest


@pytest.mark.users({"userA": "{平台}"})
class TestClass:
    """{用例标题}测试。"""

    def test_{文件名}(self, users):
        """执行测试：{操作}，应{结果}。"""
        # 获取用户资源
        userA = users["userA"]

        # 测试步骤
        userA.do_xxx()
        userA.should_xxx_success()

        # 清理步骤（hooks 自动处理）
```

### 4.2 测试方法规范

1. **测试类命名**：固定使用 `TestClass`
2. **测试方法命名**：`test_{文件名}`，如 `test_login_success_001`
3. **docstring 格式**：`执行测试：{操作}，应{结果}`
4. **测试方法只调用 AW 层**：不直接调用 testagent_client
5. **每个测试文件独立**：一个文件对应一条用例

---

## 五、用户资源管理

### 5.1 User 代理转发

User 实例自动加载对应平台的 AW，通过 `__getattr__` 代理转发方法调用：

```python
@pytest.mark.users({"userA": "web"})
class TestClass:
    def test_login_success_001(self, users):
        userA = users["userA"]

        # User 属性
        userA.account    # 账号
        userA.password   # 密码
        userA.ip         # Worker IP

        # 直接调用 AW 方法
        userA.do_login()
        userA.should_login_success()
```

### 5.2 多用户场景

```python
@pytest.mark.users({"userA": "web", "userB": "windows"})
class TestClass:
    def test_cross_platform_call_001(self, users):
        userA = users["userA"]  # Web 端
        userB = users["userB"]  # Windows 端

        userA.do_call(userB.account)
        userB.should_receive_call()
```

### 5.3 API 用户自动创建

声明 UI 用户时自动创建对应的 API 用户：

```python
@pytest.mark.users({"userA": "web"})
class TestClass:
    def test_meeting_001(self, users):
        userA = users["userA"]         # UI 用户
        userA_api = users["userA_api"] # API 用户（自动创建）

        # API 用户用于数据准备/清理
        userA_api.do_create_meeting("test")
```

---

## 六、Hooks 配置

### 6.1 概述

Hooks 用于测试用例执行前后自动执行操作，如启动/关闭应用、登录/登出等。

**执行时机**：
- `setup` hooks：测试用例执行前
- `teardown` hooks：测试用例执行后（无论成功或失败）

### 6.2 全局配置

```yaml
# config.yaml
hooks:
  web:
    setup: ["start_app"]
    teardown: ["stop_app"]
  windows:
    setup: ["start_app"]
    teardown: ["stop_app"]
  api:
    setup: []
    teardown: ["cancel_all_meetings"]
```

### 6.3 用例级别覆盖

```python
# 完全覆盖
@pytest.mark.hooks(setup=["custom_hook"], teardown=["custom_teardown"])

# 增量增加
@pytest.mark.hooks(setup=["+custom_hook"])

# 增量移除
@pytest.mark.hooks(setup=["-start_app"])

# 组合
@pytest.mark.hooks(setup=["-start_app", "+custom_hook"])

# 带参数
@pytest.mark.hooks(setup=[{"start_app": "edge"}])
```

### 6.4 自定义 Hook 方法

在 AW 层创建 `do_{hook_name}` 方法：

```python
# aw/web/init_aw.py
class InitAW(BaseAW):
    PLATFORM = "web"

    def do_start_app(self, browser: str = "chrome") -> None:
        """启动浏览器。"""
        self.start_app(browser)

    def do_stop_app(self, browser: str = "chrome") -> None:
        """关闭浏览器。"""
        self.stop_app(browser)
```

配置中使用不带前缀的名称：`start_app` → 调用 `do_start_app()`

---

## 七、API AW 模块

### 7.1 概述

API AW 通过直接调用 HTTP API 完成数据准备和清理，无需 UI 操作。

**典型场景**：
- 用例前置条件：API 预约会议
- 用例后置清理：API 取消会议
- 数据验证：API 查询状态

### 7.2 API AW 基类

```python
from aw.api.base_api_aw import BaseApiAW


class MeetingManageAW(BaseApiAW):
    _LOGIN_URL = "https://api.example.com/auth"

    def do_create_meeting(self, subject: str) -> dict:
        """创建会议。"""
        # Token 自动管理，过期自动重新登录
        result = self._post(CONFERENCE_URL, data={"subject": subject})
        return result

    def do_cancel_meeting(self, meeting_id: str) -> None:
        """取消会议。"""
        self._delete(f"{CONFERENCE_URL}/{meeting_id}")
```

**BaseApiAW 关键方法**：

| 方法 | 说明 |
|------|------|
| `_get(url, params)` | GET 请求 |
| `_post(url, data)` | POST 请求 |
| `_delete(url, params)` | DELETE 请求 |
| `_put(url, data)` | PUT 请求 |
| `_ensure_token()` | 确保 token 有效 |

### 7.3 UI 与 API 用户协同

声明 `@pytest.mark.users({"userA": "web"})` 时：

| 用户 ID | 平台 | 用途 |
|---------|------|------|
| `userA` | web | UI 操作 |
| `userA_api` | api | API 操作（同一账号，独立 token） |

```python
@pytest.mark.users({"userA": "web"})
class TestClass:
    def test_meeting_001(self, users):
        userA = users["userA"]
        userA_api = users["userA_api"]

        # API 数据准备
        userA_api.do_create_meeting("test")

        # UI 操作
        userA.do_login()
        userA.should_see_meeting("test")

        # API 数据清理（通过 hooks 自动执行）
```

### 7.4 与 UI AW 的区别

| 特性 | UI AW | API AW |
|------|-------|--------|
| 基类 | BaseAW | BaseApiAW |
| 依赖 | TestagentClient | requests.Session |
| 操作方式 | OCR/图像/坐标 | HTTP 请求 |
| Token | 无 | 自动管理 |
| 截图 | 支持 | 不支持 |

---

## 八、Skill 生成代码检查清单

当 testcase-coder Skill 生成代码时，必须确保：

- [ ] AW 文件命名符合 `{业务名}_aw.py` 格式
- [ ] AW 类命名符合 `{业务名}AW` 格式
- [ ] AW 方法以 `do_` 或 `should_` 开头
- [ ] AW 类继承 BaseAW，使用便捷方法
- [ ] 测试文件命名符合 `test_{功能}_{场景}_{编号}.py` 格式
- [ ] 测试类命名使用 `TestClass`
- [ ] 测试方法使用 `test_{文件名}`
- [ ] 所有类和方法有中文 docstring
- [ ] 测试方法通过 User 实例调用 AW 方法
- [ ] 测试用例使用 `@pytest.mark.users()` 标记声明用户需求

---

## 九、完整示例

### 9.1 AW 示例

```python
"""登录业务操作封装。"""

from aw.base_aw import BaseAW


class LoginAW(BaseAW):
    """登录业务操作封装。"""

    PLATFORM = "web"

    def do_navigate_to_login(self, url: str) -> None:
        """导航到登录页面。"""
        self.navigate(url)

    def do_login(self, username: str = None, password: str = None) -> None:
        """执行登录操作。

        步骤: 输入账号 → 输入密码 → 点击登录 → 同意隐私政策。

        Args:
            username: 用户名（可选，默认使用 user.account）。
            password: 密码（可选，默认使用 user.password）。
        """
        account = username or self.user.account
        pwd = password or self.user.password

        if not account or not pwd:
            raise ValueError("未提供账号密码")

        self.ocr_input("账号", account)
        self.ocr_input("密码", pwd)
        self.ocr_click("登录")
        self.ocr_click("同意")

    def should_login_success(self) -> None:
        """断言登录成功。"""
        self.ocr_wait("我的会议", timeout=5000)

    def should_show_error(self, error_msg: str) -> None:
        """断言显示错误提示。

        Args:
            error_msg: 期望的错误信息。
        """
        self.ocr_wait(error_msg, timeout=5000)
```

### 9.2 测试用例示例

```python
"""Web端登录成功测试用例。"""

import pytest


@pytest.mark.users({"userA": "web"})
class TestClass:
    """Web端登录成功测试。"""

    def test_login_success_001(self, users):
        """执行测试：正确账号密码登录，应登录成功。"""
        userA = users["userA"]

        # 直接通过 User 实例调用 AW 方法
        userA.do_login()
        userA.should_login_success()
```

### 9.3 多用户 + API 示例

```python
"""跨平台通话测试用例。"""

import pytest


@pytest.mark.users({"userA": "web", "userB": "windows"})
class TestClass:
    """跨平台通话测试。"""

    def test_cross_platform_call_001(self, users):
        """执行测试：Web呼叫Windows，应通话成功。"""
        userA = users["userA"]
        userB = users["userB"]
        userA_api = users["userA_api"]

        # API 数据准备
        userA_api.do_create_meeting("test")

        # UI 操作
        userA.do_login()
        userA.do_call(userB.account)

        userB.do_login()
        userB.should_receive_call()

        # API 数据清理（通过 hooks 自动执行）
```