---
name: testcase-coder
description: "代码生成 Skill。读取 .cache/review.md，按计划生成 AW 和测试用例代码，更新 INDEX.md。"
---

# 代码生成 Skill

你是一个资深测试工程师，负责按计划生成测试代码。

## 输入输出

| 类型 | 文件 |
|------|------|
| 输入 | `.cache/review.md` |
| 输出 | 生成的代码文件 + 更新 `aw/INDEX.md` |

---

## 执行步骤

### 1. 读取输入文件

读取 `.cache/review.md`，获取审查通过的计划。

### 2. 按计划生成代码

严格按照计划执行，不超出计划范围。

### 3. 更新 INDEX.md

新增/扩展 AW 后，更新 `aw/INDEX.md`。

---

## 文件命名规范

| 类型 | 命名规则 | 示例 |
|------|----------|------|
| AW 文件 | `{业务名}_aw.py` | `login_aw.py` |
| AW 类 | `{业务名}AW` | `LoginAW` |
| AW 方法 | `do_{动作}` 或 `should_{期望}` | `do_login()`, `should_login_success()` |
| 测试文件 | `test_{功能}_{场景}_{编号}.py` | `test_login_success_001.py` |
| 测试类 | `TestClass` | 固定名称 |
| 测试方法 | `test_{文件名}` | `test_login_success_001` |

---

## AW 代码模板

### UI AW 模板

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
        self.ocr_click("按钮")
        self.ocr_input("标签", "内容")

    # ── 断言方法 ─────────────────────────────────────────────

    def should_xxx_success(self) -> None:
        """断言{期望结果}。"""
        self.ocr_wait("成功", timeout=5000)
```

### API AW 模板

```python
"""
{业务名} API 操作封装。

{简述封装的 API 操作}
"""

from typing import Dict, Any

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

    # ── 断言方法 ─────────────────────────────────────────────

    def should_xxx_success(self, response: Dict[str, Any]) -> None:
        """断言 API 调用成功。"""
        assert response.get("code") == 0, f"API 调用失败: {response}"
```

---

## 测试用例模板

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
        # ...

        # 清理步骤（hooks 自动处理）
```

---

## 更新 INDEX.md

### 新增 AW

在对应平台的表格中添加一行：

```markdown
| {AW类} | aw/{平台}/{文件名}.py | {功能概述} | {方法列表} |
```

### 扩展 AW

更新方法列表字段。

---

## 核心原则

1. **严格按计划执行**：不超出计划范围
2. **遵循命名规范**：详见 AGENTS.md
3. **更新 INDEX.md**：新增/扩展 AW 后同步更新索引

---

## 生成后检查

| 检查项 | 说明 |
|--------|------|
| 文件命名 | 符合规范 |
| 类命名 | 符合规范 |
| 方法命名 | do_*/should_* 开头 |
| Docstring | 中文注释 |
| INDEX.md | 已同步更新 |