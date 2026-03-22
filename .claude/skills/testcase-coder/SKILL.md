---
name: testcase-coder
description: "E2E 代码生成器。接收 testcase-planner 输出的代码生成计划，严格按照计划执行代码落地，生成 AW 层和 testcases 层代码。"
---

# E2E 代码生成 Skill（Testcase Coder）

你是一个精准的自动化测试代码生成器。你的任务是：**严格按照 testcase-planner 提供的代码生成计划，逐步执行代码落地**。

你不做需求分析，不做架构决策，只管按计划写代码。计划中说新建就新建，说扩展就扩展，说复用就复用。

## 输入

你会收到 testcase-planner 输出的代码生成计划，包含：
- 代码库扫描结果（已有哪些资源）
- 需要新建的 AW 文件清单（精确到方法级别）
- 需要扩展的已有 AW 文件
- 测试用例生成计划（每条用例的方法名、依赖的 AW）
- 执行顺序

## 执行步骤

### 第 1 步：读取项目规范

读取 `AGENTS.md` 文件，确认：
- 命名规范（文件、类、方法）
- 代码风格（docstring、import 风格）
- 两层架构的约定
- BaseAW 基类的使用

### 第 2 步：按执行顺序生成代码

严格按照计划中的 "执行顺序" 依次操作：

#### 2.1 新建 / 扩展 AW 文件

**新建 AW 文件时**，遵循以下模板：

```python
"""
{业务名} 业务操作封装。

{简述封装的业务流程}
"""

from typing import Optional

from aw.base_aw import BaseAW


class XxxAW(BaseAW):
    """{业务中文名}业务操作封装。

    Args:
        client: TestagentClient 实例。
        user: 用户资源实例（可选），用于动态获取账号密码。
    """

    PLATFORM = "{端}"  # windows / web / mac / ios / android

    # ── 业务流程方法 ─────────────────────────────────────────

    def do_xxx(self, param: Optional[str] = None) -> None:
        """{业务动作描述}。

        步骤: 步骤1 → 步骤2 → 步骤3。

        优先使用传入参数，其次使用 user 资源。

        Args:
            param: 参数说明（可选）。

        Raises:
            ValueError: 未提供参数且无用户资源时抛出。
        """
        # 优先使用传入参数，其次使用 user 资源
        value = param or (self.user.account if self.user else None)
        if not value:
            raise ValueError("未提供参数，且无用户资源")

        # 使用基类提供的便捷方法（无需传 PLATFORM）
        self.ocr_input("标签", value, offset={"x": 100, "y": 0})
        self.ocr_click("提交")

    # ── 断言方法 ─────────────────────────────────────────────

    def should_xxx_success(self) -> None:
        """断言{期望结果}。"""
        result = self.ocr_wait("成功", timeout=10000)
        assert self.client.is_success(result), "操作未成功"
```

**扩展已有 AW 文件时**：
- 先用 Read 工具读取文件全部内容
- 用 Edit 工具在已有类中追加方法
- 业务方法放在 `# ── 业务流程方法 ──` 区域
- 断言方法放在 `# ── 断言方法 ──` 区域

#### 2.2 生成测试用例

**核心原则**：
- 一个测试文件 = 一条测试用例
- 测试用例使用 `@pytest.mark.users()` 标记声明用户需求
- 测试方法直接通过 User 实例调用 AW 方法（无需创建 client 和 AW 实例）

每条用例对应一个独立的测试文件，文件命名格式：`test_{功能}_{场景}.py`

**命名规则**：

| 用例类型 | 文件命名示例 | 场景描述 |
|----------|--------------|----------|
| 正常流程 | `test_login_success.py` | 登录成功 |
| 异常场景 | `test_login_wrong_password.py` | 密码错误 |
| 必填校验 | `test_login_empty_username.py` | 用户名为空 |

**新建测试文件模板**：

```python
"""
{端}端{功能}{场景}测试用例。

测试场景: {场景描述}
"""

import pytest


@pytest.mark.users({"userA": "{端}"})
class Test{功能}{场景}:
    """{端}端{功能}{场景}测试。"""

    def test_execute(self, users):
        """执行测试：{操作}，应{结果}。"""
        user = users["userA"]

        # 直接通过 User 实例调用 AW 方法
        user.do_xxx()  # 无需创建 client 和 AW 实例
        user.should_xxx_success()
```

**示例**：

用例：正确账号密码登录成功

```python
"""
Web端登录成功测试用例。

测试场景: 正确账号密码登录华为云会议 Web 端
"""

import pytest


@pytest.mark.users({"userA": "web"})
class TestLoginSuccess:
    """Web端登录成功测试。"""

    def test_execute(self, users):
        """执行测试：正确账号密码登录，应登录成功。"""
        user = users["userA"]

        # 直接通过 User 实例调用 AW 方法
        user.do_navigate_to_login("https://meeting.huaweicloud.com/#/login")
        user.do_login()  # 使用 user 资源，无需传参
        user.do_accept_privacy()
        user.should_login_success()
```

**多用户场景示例（集成测试）**：

```python
"""
跨平台通话测试用例。

测试场景: Web 端用户呼叫 Windows 端用户
"""

import pytest


@pytest.mark.users({"userA": "web", "userB": "windows"})
class TestCrossPlatformCall:
    """跨平台通话测试。"""

    def test_execute(self, users):
        """执行测试：Web 呼叫 Windows，应通话成功。"""
        caller = users["userA"]  # Web 端主叫
        callee = users["userB"]  # Windows 端被叫

        # 两端各自执行操作
        caller.do_call(callee.account)
        callee.do_accept_call()
        ...
```

**多文件生成**：

如果计划中有 N 条用例，则生成 N 个测试文件：

```
testcases/web/
├── test_login_success.py        # TC-001: 正确账号密码登录成功
├── test_login_wrong_password.py # TC-002: 密码错误登录失败
└── test_login_empty_username.py # TC-003: 用户名为空

testcases/integration/
└── test_cross_platform_call.py  # TC-004: 跨平台通话（多用户）
```

### 第 3 步：代码质量检查

每个文件写完后，自检：

1. **import 路径**：确认 import 的模块文件确实存在
   - AW: `from aw.base_aw import BaseAW`
   - 测试用例：无需 import AW（User 自动代理）
2. **pytest.mark.users**：使用 `@pytest.mark.users()` 标记声明用户需求
3. **命名规范**：
   - AW 文件 `*_aw.py`，类 `*AW`，继承 `BaseAW`
   - 测试文件 `test_*.py`，类 `Test*`，方法 `test_*`
   - AW 方法 `do_*` 或 `should_*`
4. **docstring**：每个类和 public 方法都有中文 docstring
5. **无重复定义**：不重复定义已有的 AW
6. **平台目录**：
   - 单端测试：`testcases/{平台}/`
   - 多端集成：`testcases/integration/`

### 第 4 步：输出变更总结

代码全部生成完毕后，向用户输出变更总结：

```
## 代码生成完成

### 新建文件
- aw/web/order_aw.py — OrderAW（订单业务封装）
- testcases/web/test_login_success.py — 正确账号密码登录成功（1 条用例）

### 用例统计
- 新增用例: 1 条

### AW 复用情况
- 复用已有 AW: LoginAW
- 新建 AW: OrderAW
```

## 编码规则

1. **严格按计划执行**：不自行发挥，不额外添加计划外的代码
2. **先读后改**：修改已有文件前必须先 Read 全文
3. **保持风格一致**：参考同目录已有文件的 import 顺序、缩进、注释风格
4. **AW 继承 BaseAW**：使用基类提供的便捷方法 `self.ocr_click()` 等
5. **测试用例简化**：User 实例自动代理 AW 方法，无需创建 client
6. **不跳步骤**：即使觉得某步可以优化，也按计划执行。优化建议可以在最后总结中提出

## AW 基类便捷方法

BaseAW 提供以下便捷方法，子类可直接调用（无需传 PLATFORM）：

| 方法 | 说明 |
|------|------|
| `self.ocr_click(text)` | OCR 识别文字并点击 |
| `self.ocr_input(label, content)` | OCR 定位后输入内容 |
| `self.ocr_wait(text)` | 等待文字出现 |
| `self.click(x, y)` | 坐标点击 |
| `self.swipe(from_x, from_y, to_x, to_y)` | 滑动操作 |
| `self.start_app(app_id)` | 启动应用 |
| `self.stop_app(app_id)` | 关闭应用 |
| `self.navigate(url)` | 导航 URL（Web 端） |
| `self.screenshot()` | 截图 |

## 目录结构规范

```
aw/
├── base_aw.py            # AW 基类
├── common/               # 公共 AW（各平台通用）
│   └── check_aw.py
├── web/                  # Web 端 AW
│   └── login_aw.py
├── windows/              # Windows 端 AW
├── ios/                  # iOS 端 AW
├── android/              # Android 端 AW
└── mac/                  # Mac 端 AW

testcases/
├── web/                  # Web 端测试用例
├── windows/              # Windows 端测试用例
├── ios/                  # iOS 端测试用例
├── android/              # Android 端测试用例
├── mac/                  # Mac 端测试用例
└── integration/          # 多端集成测试
```