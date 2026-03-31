---
name: testcase-aw
description: "AW新增/扩展/修改。与用户确认平台和操作步骤，生成AW代码并更新INDEX.md。"
---

# AW 操作 Skill

处理AW的新增、扩展、修改操作，必须与用户确认平台和步骤。

---

## 执行流程

### 步骤 1：确认AW平台

**必须**使用 AskUserQuestion 让用户选择平台：

```
问题: "请选择AW平台"
选项:
1. web（Web端UI操作）
2. windows（Windows客户端）
3. mac（Mac客户端）
4. ios（iOS端）
5. android（Android端）
6. api（HTTP接口封装）
```

### 步骤 2：确认操作步骤

**必须**让用户描述每一步操作细节：

#### UI操作确认

询问用户：
```
问题: "请描述每个操作步骤（可多次输入）"
提示: 每个步骤包含：操作类型 + 操作对象

操作类型:
- ocr_click: 点击（按钮、链接）
- ocr_input: 输入（文本框）
- ocr_wait: 等待出现（元素）
- ocr_assert: 断言（文本存在）

示例:
1. ocr_click "登录按钮"
2. ocr_input "用户名" "test@example.com"
3. ocr_wait "登录成功"
```

#### API操作确认

询问用户：
```
问题: "请描述API操作详情"
提示:
- HTTP方法: GET/POST/PUT/DELETE
- 请求路径: /api/xxx
- 请求参数: {}
- 返回值字段: {}

示例:
POST /api/meeting/create
参数: {"subject": "会议主题"}
返回: {"conference_id": "xxx", "join_url": "xxx"}
```

### 步骤 3：确定命名

根据用户描述自动确定命名（遵循AGENTS.md规范）：

| 类型 | 命名规则 | 示例 |
|------|----------|------|
| AW类 | {业务名}AW | LoginAW |
| 方法 | do_{动作} / should_{期望} | do_login(), should_login_success() |
| 文件 | {业务名}_aw.py | login_aw.py |
| 路径 | aw/{平台}/{业务名}_aw.py | aw/web/login_aw.py |

### 步骤 4：生成代码

根据平台选择对应模板生成代码。

### 步骤 5：更新INDEX.md

在 `aw/INDEX.md` 对应平台表格添加记录：

```markdown
| 方法 | 说明 |
|------|------|
| `do_xxx()` | 执行xxx操作 |
| `should_xxx_success()` | 断言xxx成功 |
```

---

## AW 代码模板

### UI AW模板

```python
"""
{业务名}业务操作封装。

{简述封装的业务流程}
"""

from typing import Optional

from aw.base_aw import BaseAW


class XxxAW(BaseAW):
    """{业务中文名}业务操作封装。

    Args:
        client: TestagentClient 实例。
        user: 用户资源实例（可选）。
    """

    PLATFORM = "{端}"  # windows / web / mac / ios / android

    # ── 业务流程方法 ─────────────────────────────────────────

    def do_xxx(self, param: Optional[str] = None) -> None:
        """{业务动作描述}。

        步骤: 步骤1 → 步骤2 → 步骤3。

        Args:
            param: 参数说明（可选）。
        """
        # 使用 BaseAW 便捷方法，无需传 platform
        self.ocr_click("按钮")
        self.ocr_input("标签", "内容")

    # ── 断言方法 ─────────────────────────────────────────────

    def should_xxx_success(self) -> None:
        """断言{期望结果}。"""
        self.ocr_wait("成功", timeout=5000)
```

### API AW模板

```python
"""
{业务名} API 操作封装。

{简述封装的 API 操作}
"""

from typing import Dict, Any, Optional

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
        return self._post(url, data={"param": param})

    def do_xxx_with_id(self, id: str, param: Optional[str] = None) -> Dict[str, Any]:
        """{带ID的API操作}。

        Args:
            id: 资源ID。
            param: 参数说明（可选）。

        Returns:
            API 响应数据。
        """
        url = f"{self.BASE_URL}/api/xxx/{id}"
        return self._post(url, data={"param": param})

    # ── 断言方法 ─────────────────────────────────────────────

    def should_xxx_success(self, response: Dict[str, Any]) -> None:
        """断言 API 调用成功。"""
        assert response.get("code") == 0, f"API 调用失败: {response}"
```

---

## 扩展已有AW

当需要扩展已有AW时：

### 步骤 1：确认目标AW

读取 `aw/INDEX.md`，确认要扩展的AW类和文件路径。

### 步骤 2：确认新增方法

让用户描述新增方法的操作步骤。

### 步骤 3：生成方法代码

在已有AW类中添加新方法，遵循命名规范。

### 步骤 4：更新INDEX.md

在已有AW的方法表格中添加新方法记录。

---

## 修改已有AW

当需要修改已有AW方法时：

### 步骤 1：确认修改内容

让用户描述：
- 要修改的方法名
- 新的操作步骤

### 步骤 2：修改代码

直接修改方法实现，保留方法签名。

### 步骤 3：更新方法注释

更新方法的docstring，反映新的步骤。

---

## 核心原则

1. **必须与用户确认**：平台、步骤都不能跳过
2. **遵循命名规范**：{业务名}AW、do_*/should_*
3. **使用BaseAW便捷方法**：self.ocr_click() 而非 self.client.ocr_click()
4. **生成后更新INDEX.md**：确保索引同步
5. **中文注释**：docstring和注释使用中文