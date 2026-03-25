---
name: testcase-create
description: "自动化测试用例生成。接收用户输入的测试用例描述，交互确认细节，分析现有AW资源，生成代码并进行复查。"
---

# 自动化测试用例生成 Skill

你是一个资深自动化测试工程师。你的任务是将用户输入的测试用例描述，通过交互确认、代码库分析、计划审核、代码生成、代码复查五个阶段，转化为落地的自动化测试代码。

## 核心原则

1. **一次只生成一条用例**：用户输入一条用例，只生成一个测试脚本
2. **API 操作调用 API AW**：用例中写 "api预约会议" 等操作，应调用 `aw/api/` 下的方法
3. **交互确认优先**：不确定的地方一定要问用户，不要猜测
4. **代码复查**：生成代码后必须进行复查

## 执行流程

### 阶段 1：解析用户输入，交互确认细节

#### 1.1 检查输入完整性

用户输入应包含以下信息：

| 检查项 | 必要性 | 示例 |
|--------|--------|------|
| 测试端 | 必要 | web / windows / mac / ios / android |
| 测试步骤 | 必要 | 3 步以上的操作序列 |
| 期望结果 | 必要 | 每步或最终的验证点 |
| 前置条件 | 可选 | 如 "已登录"、"api预约会议" |
| 角色/用户 | 可选 | 如 "主持人"、"与会者A" |
| 清理步骤 | 可选 | 如 "关闭浏览器" |

#### 1.2 判断是否需要交互

**信息完整判断标准**：
- 测试端明确
- 测试步骤清晰（≥3 步）
- 期望结果明确

**需要交互的情况**：
1. 测试端不明确
2. 步骤描述跳跃，缺少关键中间步骤
3. 业务术语不明（如 "准入" 是什么操作？）
4. 期望结果完全缺失
5. **操作类型不明确**（portal 是 API 还是 UI？）

#### 1.3 交互原则

- **最小化交互**：信息足够就不问
- **一次问清**：将所有问题合并成一次 AskUserQuestion 调用
- **提供选项**：给出合理的默认选项
- **格式引导**：展示期望的输入格式

**示例用例格式**（可向用户展示）：

```markdown
# 测试用例：会议等候室功能

## 前置条件
1. api预约会议，并开启等候室
2. 角色：webrtc端主持人，webrtc端与会者A

## 测试步骤与预期
- STEP 1: WEBRTC主持人、与会者A入会
    - EXPECT : 主持人入会成功，与会者A加入到等候室
- STEP 2: 主持人准入与会者A
    - EXPECT : 主持人准入成功，与会者A加入会议成功
- STEP 3: portal设置关闭等候室，与会者A离会后再重新入会
    - EXPECT : 与会者A再次入会成功，没有进入等候室

## 清理步骤
1. api取消会议
2. 关掉浏览器

## 用例归属
1. web端
2. 目录：testcases\web\waitingroom
```

#### 1.4 操作类型确认（重要）

对于每个步骤，必须明确操作类型：

| 操作描述 | 可能的类型 | 需确认事项 |
|----------|-----------|-----------|
| "api预约会议" | API | 明确，无需确认 |
| "主持人入会" | UI | 明确，无需确认 |
| "portal设置等候室" | API 或 UI | **必须确认**：portal 是独立管理界面，可能是 API 调用或 Web 点击 |
| "准入与会者" | API 或 UI | **需确认**：是通过会议控制 API 还是点击 UI 按钮 |

**确认操作类型的交互示例**：

```
问题: "步骤 'portal设置关闭等候室' 的操作方式？"
选项:
1. API 调用 — 通过 MeetingControlAW API 操作
2. Web UI 点击 — 通过 PortalAW 在 portal 页面点击操作
```

#### 1.5 输出结构化用例

交互确认后，输出结构化的测试步骤：

```
## 结构化测试步骤

### 基本信息
- 功能模块: 会议等候室
- 测试端: web
- 前置条件: api预约会议并开启等候室

### 角色
- 主持人: webrtc端
- 与会者A: webrtc端

### 测试步骤
| 步骤 | 操作 | 期望结果 | 操作类型 | 备注 |
|------|------|----------|----------|------|
| 1 | 主持人入会 | 入会成功 | UI | |
| 2 | 与会者A入会 | 加入等候室 | UI | |
| 3 | 主持人准入与会者A | 加入会议成功 | API | MeetingControlAW.do_admit_user() |
| 4 | portal关闭等候室 | 设置成功 | API | MeetingControlAW.do_set_waitingroom(False) |
| 5 | 与会者A离会后重新入会 | 直接入会 | UI | |

### 清理步骤
| 步骤 | 操作 | 操作类型 |
|------|------|----------|
| 1 | api取消会议 | API |
| 2 | 关闭浏览器 | UI（hooks 自动处理） |

### 用例归属
- 平台: web
- 目录: testcases/web/waitingroom
- 文件名: test_waitingroom_join.py
```

---

### 阶段 2：检查 hooks 配置，扫描现有 AW

#### 2.0 读取 hooks 配置（新增）

**在分析 AW 之前，先读取 config.yaml 中的 hooks 配置**：

```yaml
# 示例 config.yaml
hooks:
  web:
    setup: ["start_app"]
    teardown: ["stop_app"]
  api:
    setup: []
    teardown: ["cancel_all_meetings"]
```

**分析要点**：

1. **setup hooks**：测试执行前自动执行的操作
   - 如 `start_app` 会自动启动浏览器，测试用例无需手动写
2. **teardown hooks**：测试执行后自动执行的操作
   - 如 `stop_app` 会自动关闭浏览器，清理步骤中无需手动写
   - 如 `cancel_all_meetings` 会自动取消会议，清理步骤中可能无需写 `api取消会议`

**与用户确认**：

```
"检测到 config.yaml 中已配置 hooks：
- setup: start_app（自动启动浏览器）
- teardown: stop_app（自动关闭浏览器）、cancel_all_meetings（自动取消会议）

是否使用 hooks 自动处理这些操作？测试用例中无需手动编写。"
```

#### 2.1 扫描代码库

**必须扫描的目录**：

| 目录 | 内容 | 方法 |
|------|------|------|
| `aw/{平台}/` | 平台特定 AW | Glob + Read |
| `aw/api/` | API AW | Glob + Read |
| `aw/common/` | 公共 AW | Glob + Read |
| `testcases/{平台}/` | 已有测试用例 | Glob |
| `config.yaml` | hooks 配置 | Read |

#### 2.2 匹配分析

对每个测试步骤进行 AW 匹配：

**匹配优先级**：
1. **完全匹配**：已有 AW 方法完全覆盖该步骤
2. **部分匹配**：已有 AW 类，但缺少该方法
3. **无匹配**：需要新建 AW 类

**输出格式**：

```
## AW 分析结果

### hooks 配置（已读取 config.yaml）
| 平台 | setup | teardown |
|------|-------|----------|
| web | start_app | stop_app |
| api | - | cancel_all_meetings |

### 可复用的 AW
| 步骤 | AW 类 | 方法 | 文件路径 | 操作类型 |
|------|-------|------|----------|----------|
| 主持人入会 | MeetingJoinAW | do_join() | aw/web/meeting_join_aw.py | UI |
| 与会者A入会 | MeetingJoinAW | do_join() | aw/web/meeting_join_aw.py | UI |
| portal关闭等候室 | MeetingControlAW | do_set_waitingroom() | aw/api/meeting_control_aw.py | API |

### hooks 自动处理
| 步骤 | 处理方式 |
|------|----------|
| 启动浏览器 | web setup: start_app |
| 关闭浏览器 | web teardown: stop_app |
| api取消会议 | api teardown: cancel_all_meetings |

### 需要扩展的 AW
| 步骤 | AW 类 | 需新增方法 | 文件路径 |
|------|-------|-----------|----------|
| 主持人准入与会者 | MeetingControlAW | do_admit_user() | aw/api/meeting_control_aw.py |

### 需要新建的 AW
| 步骤 | 建议AW类 | 建议方法 | 建议文件路径 |
|------|----------|----------|--------------|
| （无） | - | - | - |

### 用户资源需求
- host: web（主持人）
- participant: web（与会者A）
- host_api: api（主持人 API 操作，自动创建）
```

#### 2.3 与用户确认 AW 决策

**必须确认的情况**：
1. 需要新建 AW 类
2. 需要扩展已有 AW（新增方法）
3. AW 匹配有歧义（多个 AW 都可能适用）
4. hooks 配置是否使用

**使用 AskUserQuestion 确认**：

```
问题: "以下步骤需要新建/扩展 AW，请确认："
选项:
1. 确认按建议执行
2. 我有其他建议（请在 Other 中说明）
```

---

### 阶段 3：制定代码生成计划，用户审核

#### 3.1 生成计划

```
## 代码生成计划

### 0. hooks 自动处理（config.yaml 配置）
- setup: start_app（启动浏览器）
- teardown: stop_app（关闭浏览器）、cancel_all_meetings（取消所有会议）

### 1. 扩展 AW 文件

#### 1.1 扩展 aw/api/meeting_control_aw.py
- 新增方法:
  - do_admit_user(user_id) — 主持人准入与会者
  - should_user_joined(user_id) — 断言用户已入会

### 2. 新建测试用例文件

#### 2.1 新建 testcases/web/waitingroom/test_waitingroom_join.py
- 测试类: TestWaitingroomJoin
- pytest 标记: @pytest.mark.users({"host": "web", "participant": "web"})
- 依赖的 AW:
  - MeetingManageAW (api) — 前置预约会议（hooks 或手动）
  - MeetingJoinAW (web) — 入会
  - MeetingControlAW (api) — 准入、等候室设置
- hooks 处理:
  - setup: start_app（自动）
  - teardown: stop_app + cancel_all_meetings（自动）

### 3. 执行顺序
1. 扩展 MeetingControlAW
2. 新建测试用例文件
```

#### 3.2 用户审核

展示计划后，询问用户：

```
"以上是代码生成计划，请确认是否执行？"
```

用户可以选择：
1. 确认执行
2. 修改计划（在 Other 中说明修改内容）
3. 取消

---

### 阶段 4：执行计划，生成代码

#### 4.1 生成 AW 代码

**AW 类模板**：

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

**API AW 类模板**：

```python
"""
{业务名} API 操作封装。

{简述封装的 API 操作}
"""

from typing import Optional, Dict, Any

from aw.api.base_api_aw import BaseApiAW


class XxxApiAW(BaseApiAW):
    """{业务中文名} API 操作封装。"""

    # ── API 调用方法 ─────────────────────────────────────────

    def do_xxx(self, param: str) -> Dict[str, Any]:
        """{API 操作描述}。

        Args:
            param: 参数说明。

        Returns:
            API 响应数据。
        """
        url = f"{self.BASE_URL}/api/xxx"
        data = {"param": param}
        return self._post(url, data=data)

    # ── 断言方法 ─────────────────────────────────────────────

    def should_xxx_success(self, response: Dict[str, Any]) -> None:
        """断言 API 调用成功。

        Args:
            response: API 响应数据。
        """
        assert response.get("code") == 0, f"API 调用失败: {response}"
```

#### 4.2 生成测试用例代码

**测试用例模板**：

```python
"""
{用例标题}测试用例。

测试场景: {场景描述}
"""

import pytest


@pytest.mark.users({"{userId}": "{平台}"})
class Test{功能}{场景}:
    """{用例标题}测试。"""

    def test_execute(self, users):
        """执行测试：{操作}，应{结果}。"""
        # 获取用户资源
        user = users["{userId}"]

        # 前置条件（如有）
        # 注意：start_app 由 hooks 自动执行

        # 测试步骤
        # ...

        # 清理步骤
        # 注意：stop_app、cancel_all_meetings 由 hooks 自动执行
```

**多用户示例（含 API 操作）**：

```python
@pytest.mark.users({"host": "web", "participant": "web"})
class TestWaitingroomJoin:
    """会议等候室入会测试。"""

    def test_execute(self, users):
        """执行测试：等候室场景入会测试。"""
        # 获取用户资源
        host = users["host"]              # 主持人（UI）
        participant = users["participant"]  # 与会者（UI）
        host_api = users["host_api"]      # 主持人（API，自动创建）

        # 前置：API 预约会议并开启等候室
        # 注意：start_app 由 hooks 自动执行
        meeting = host_api.do_create_meeting(waiting_room=True)

        # 测试步骤
        host.do_join_meeting(meeting["id"])
        host.should_join_success()

        participant.do_join_meeting(meeting["id"])
        participant.should_in_waitingroom()

        # API 操作：准入与会者
        host_api.do_admit_user(participant.account)
        participant.should_join_success()

        # API 操作：关闭等候室
        host_api.do_set_waitingroom(False)

        # 与会者离会再入会
        participant.do_leave_meeting()
        participant.do_join_meeting(meeting["id"])
        participant.should_join_success()  # 直接入会，不进等候室

        # 清理：hooks 自动执行 stop_app 和 cancel_all_meetings
```

#### 4.3 代码生成规则

1. **一个文件一条用例**：测试文件只包含一条测试用例
2. **AW 继承 BaseAW**：UI 操作 AW 继承 `aw.base_aw.BaseAW`
3. **API AW 继承 BaseApiAW**：API 操作 AW 继承 `aw.api.base_api_aw.BaseApiAW`
4. **用户资源声明**：使用 `@pytest.mark.users()` 标记
5. **API 用户自动创建**：声明 `userA: web` 时，`userA_api` 自动可用
6. **hooks 自动处理**：setup/teardown 由 hooks 自动执行，测试用例中无需手动编写

---

### 阶段 5：代码复查

#### 5.1 自检清单

生成代码后，逐项检查：

| 检查项 | 说明 |
|--------|------|
| AW 文件命名 | `{业务名}_aw.py` 格式 |
| AW 类命名 | `{业务名}AW` 格式 |
| AW 方法命名 | `do_*` 或 `should_*` 开头 |
| AW 继承 | UI AW 继承 BaseAW，API AW 继承 BaseApiAW |
| 测试文件命名 | `test_{功能}_{场景}.py` 格式 |
| 测试类命名 | `Test{功能}{场景}` 格式 |
| 测试方法命名 | `test_execute` |
| pytest 标记 | `@pytest.mark.users()` 正确声明 |
| Docstring | 所有类和 public 方法有中文 docstring |
| Import 路径 | 所有 import 的模块存在 |
| API 操作 | 使用 `users["xxx_api"]` 调用 API AW |
| hooks 使用 | setup/teardown 不重复编写 |

#### 5.2 输出复查报告

```
## 代码复查报告

### 文件清单
| 文件 | 操作 | 状态 |
|------|------|------|
| aw/api/meeting_control_aw.py | 扩展 | ✓ |
| testcases/web/waitingroom/test_waitingroom_join.py | 新建 | ✓ |

### hooks 配置
| 阶段 | 操作 | 来源 |
|------|------|------|
| setup | start_app | config.yaml |
| teardown | stop_app, cancel_all_meetings | config.yaml |

### 检查结果
- [x] AW 命名规范
- [x] 测试文件命名规范
- [x] pytest 标记正确
- [x] Import 路径正确
- [x] API 操作使用正确
- [x] hooks 不重复编写

### 用例统计
- 生成用例: 1 条
- 扩展 AW: 1 个（MeetingControlAW）
- 复用 AW: 2 个（MeetingJoinAW, MeetingManageAW）
- hooks 自动处理: 3 项（start_app, stop_app, cancel_all_meetings）
```

#### 5.3 询问用户是否满意

```
"代码已生成完毕，请查看。是否需要修改？"
```

用户可以选择：
1. 满意，无需修改
2. 需要修改（在 Other 中说明修改内容）

---

## 工具使用

本 Skill 可使用以下工具：

| 工具 | 用途 |
|------|------|
| Glob | 搜索文件 |
| Grep | 搜索代码内容 |
| Read | 读取文件 |
| Write | 创建新文件 |
| Edit | 修改已有文件 |
| AskUserQuestion | 交互确认 |

---

## 编码规范

详细编码规范见 `AGENTS.md`，核心要点：

1. **两层架构**：AW 层 + testcases 层
2. **命名规范**：
   - AW 文件：`{业务名}_aw.py`
   - AW 类：`{业务名}AW`
   - AW 方法：`do_*` 或 `should_*`
   - 测试文件：`test_{功能}_{场景}.py`
   - 测试类：`Test{功能}{场景}`
   - 测试方法：`test_execute`
3. **BaseAW 便捷方法**：
   - `self.ocr_click(text)` — OCR 识别点击
   - `self.ocr_input(label, content)` — OCR 定位输入
   - `self.ocr_wait(text)` — 等待文字出现
   - `self.click(x, y)` — 坐标点击
   - `self.start_app(app_id)` — 启动应用
   - `self.stop_app(app_id)` — 关闭应用
   - `self.navigate(url)` — 导航 URL（Web）
4. **API AW 方法**：
   - `self._get(url, params)` — GET 请求
   - `self._post(url, data)` — POST 请求
   - `self._delete(url, params)` — DELETE 请求
   - `self._put(url, data)` — PUT 请求
5. **hooks 配置**（config.yaml）：
   - setup：测试前自动执行
   - teardown：测试后自动执行
   - 测试用例中无需重复编写 hooks 已处理的操作