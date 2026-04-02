# 报告两层折叠结构设计

## 背景

当前 HTML 报告中，每个 AW 调用步骤单独展示，导致页面很长。用户希望按业务方法分块展示，业务方法内部的原子操作作为子步骤折叠显示。

## 目标

实现两层折叠结构：
- **第一层**：业务方法（`do_*/should_*`）作为可折叠块，显示关键参数、状态、耗时
- **第二层**：原子操作（如 `ocr_click`、`wait`）作为子步骤，可展开查看详情

示例：
```
▼ LoginAW.do_login(username="138****") ✓ 1.5s
    ├─ ▶ ocr_wait("邮箱/帐号") ✓ 800ms
    ├─ ▶ ocr_input("邮箱/帐号", "138****") ✓ 200ms
    └─ ▶ ocr_click("登录") ✓ 150ms
```

## 设计

### 核心原则

1. **业务方法不产生日志**：`do_*/should_*` 方法不调用 `_execute_with_log`，不产生日志条目
2. **原子操作产生日志**：`ocr_click`、`wait` 等原子操作产生日志，记录 `parent_aw` 字段
3. **自动识别层级**：通过 `inspect` 调用栈自动识别最近的 `do_*/should_*` 方法作为 parent
4. **失败路径展开**：失败的业务方法块默认展开，成功的默认折叠

### 改动文件

| 文件 | 改动内容 |
|------|----------|
| `common/report_logger.py` | `log_aw_call` 增加 `parent_aw` 参数 |
| `aw/base_aw.py` | 新增 `_find_parent_aw()` 方法，`_execute_with_log` 传递 `parent_aw` |
| `common/report_generator.py` | 新增分组和渲染方法，更新 CSS 和 JS |

---

### 日志结构变更

**`report_logger.py` - `log_aw_call` 方法签名**

```python
def log_aw_call(
    self,
    aw_name: str,
    method: str,
    args: dict,
    success: bool,
    result: dict,
    duration_ms: int,
    target_image: str = "",
    target_image_path: str = "",
    parent_aw: str = ""  # 新增：父级 AW 标识
) -> None:
```

**日志条目示例**

原子操作日志：
```python
{
    "type": "aw_call",
    "aw_name": "LoginAW",
    "method": "ocr_click",
    "parent_aw": "LoginAW.do_login",  # 属于 do_login 业务方法
    "args": {"text": "登录", "user_id": "userA"},
    "success": True,
    "duration_ms": 150,
    ...
}
```

顶层原子操作（直接在测试用例中调用，无业务方法包裹）：
```python
{
    "type": "aw_call",
    "aw_name": "InitAW",
    "method": "wait",
    "parent_aw": "",  # 空，表示顶层
    ...
}
```

---

### 自动识别 parent_aw

**`base_aw.py` - 新增方法**

```python
import inspect

def _find_parent_aw(self) -> str:
    """从调用栈中查找最近的 do_*/should_* 方法作为 parent。

    Returns:
        父级 AW 标识，如 "LoginAW.do_login"。
        如果没找到业务方法，返回空字符串（顶层）。
    """
    stack = inspect.stack()
    aw_name = self._aw_name

    for frame_info in stack:
        func_name = frame_info.function
        if func_name.startswith(('do_', 'should_')):
            return f"{aw_name}.{func_name}"

    return ""
```

**`base_aw.py` - `_execute_with_log` 改动**

```python
def _execute_with_log(self, method, action_data, log_args):
    # 自动识别 parent_aw
    parent_aw = self._find_parent_aw()

    # ... 原有执行逻辑 ...

    logger.log_aw_call(
        aw_name=self._aw_name,
        method=method,
        args={...},
        success=success,
        result=full_result,
        duration_ms=duration_ms,
        parent_aw=parent_aw,  # 传递 parent_aw
        ...
    )
```

**识别示例**

```
测试用例
  └─ do_login()                    # 业务方法，不产生日志
       ├─ ocr_wait()               # parent_aw = "LoginAW.do_login"
       ├─ ocr_input()              # parent_aw = "LoginAW.do_login"
       └─ do_accept_privacy()      # 业务方法，不产生日志
            └─ ocr_click()         # parent_aw = "LoginAW.do_login"（找到最近的 do_login）
```

---

### 报告生成逻辑

**`report_generator.py` - 新增方法**

```python
@staticmethod
def _build_aw_tree(logs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """将日志按 parent_aw 分组构建树形结构。

    Returns:
        顶层块列表，每个块包含：
        - block_id: "LoginAW.do_login"
        - aw_name: "LoginAW"
        - method: "do_login"
        - args: 业务方法参数（从第一个子步骤提取）
        - success: 整体成功/失败
        - duration_ms: 总耗时
        - steps: 子步骤列表
    """
    # 按 parent_aw 分组
    groups = {}
    for log in logs:
        if log.get("type") != "aw_call":
            continue
        parent = log.get("parent_aw", "")
        if parent not in groups:
            groups[parent] = []
        groups[parent].append(log)

    # 构建顶层块（parent_aw == ""）
    # 以及业务方法块（parent_aw == "LoginAW.do_login"）
    ...
```

**块数据结构**

```python
{
    "block_id": "LoginAW.do_login",
    "aw_name": "LoginAW",
    "method": "do_login",
    "user_info": {"user_id": "userA", "user_name": "张三"},
    "args": {"username": "138****"},  # 业务方法参数
    "success": True,
    "duration_ms": 1500,  # 总耗时
    "steps": [  # 子步骤
        {"method": "ocr_wait", "args": {...}, "success": True, "duration_ms": 800},
        {"method": "ocr_input", "args": {...}, "success": True, "duration_ms": 200},
    ]
}
```

---

### HTML 结构

**业务方法块**

```html
<div class="aw-block expanded">  <!-- 失败时默认 expanded -->
  <div class="aw-header">
    <span class="aw-arrow">▶</span>
    <span class="log-time">09:30:15</span>
    <div class="log-type-wrapper">
      <span class="log-type type-aw_call">AW</span>
      <span class="log-user-id">userA</span>
      <span class="log-user-name">张三</span>
    </div>
    <span class="aw-title">LoginAW.do_login(username="138****")</span>
    <span class="aw-status success">✓</span>
    <span class="aw-duration">1500ms</span>
  </div>
  <div class="aw-content">
    <div class="aw-steps">
      <!-- 子步骤 -->
      <div class="aw-step">
        <span class="step-arrow">▶</span>
        <span class="step-title">ocr_wait("邮箱/帐号")</span>
        <span class="step-status success">✓</span>
        <span class="step-duration">800ms</span>
      </div>
      <div class="aw-step expanded">
        <span class="step-arrow">▶</span>
        <span class="step-title">ocr_input("邮箱/帐号", "138****")</span>
        <span class="step-status success">✓</span>
        <span class="step-duration">200ms</span>
        <div class="step-detail">
          参数: {"text": "邮箱/帐号", "content": "138****"}<br>
          结果: {"status": "success", "output": "..."}
        </div>
      </div>
    </div>
  </div>
</div>
```

---

### CSS 样式

**新增样式**

```css
/* 子步骤容器 */
.aw-steps {
  padding: 0 16px 12px 16px;
}

/* 原子操作步骤 */
.aw-step {
  display: flex;
  align-items: center;
  padding: 8px 12px;
  margin: 4px 0;
  background: #f8f9fa;
  border-radius: 6px;
  cursor: pointer;
  gap: 8px;
}
.aw-step:hover {
  background: #e9ecef;
}

.step-arrow {
  color: #6c757d;
  font-size: 10px;
  transition: transform 0.2s;
}
.aw-step.expanded .step-arrow {
  transform: rotate(90deg);
}

.step-title {
  font-weight: 500;
  color: #343a40;
  flex: 1;
}

.step-status {
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 11px;
}
.step-status.success { background: #28a745; color: white; }
.step-status.failed { background: #dc3545; color: white; }

.step-duration {
  color: #868e96;
  font-size: 11px;
}

/* 步骤详情 */
.step-detail {
  display: none;
  margin-top: 8px;
  padding: 8px 12px;
  background: #fff;
  border-radius: 4px;
  font-family: 'Consolas', monospace;
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-all;
}
.aw-step.expanded .step-detail {
  display: block;
}
```

---

### JavaScript 交互

```javascript
// 业务方法块折叠/展开
document.querySelectorAll('.aw-header').forEach(header => {
    header.addEventListener('click', function() {
        const block = this.closest('.aw-block');
        block.classList.toggle('expanded');
    });
});

// 原子操作步骤折叠/展开
document.querySelectorAll('.aw-step').forEach(step => {
    step.addEventListener('click', function(e) {
        if (e.target.closest('.step-detail')) return;
        this.classList.toggle('expanded');
    });
});
```

---

### 兼容性

- **向后兼容**：现有日志无 `parent_aw` 字段时，视为顶层块
- **无需修改现有 AW 代码**：自动识别业务方法，无需添加装饰器或手动标记

### 影响范围

- `common/report_logger.py`：约 5 行改动
- `aw/base_aw.py`：约 20 行改动（新增方法 + 修改调用）
- `common/report_generator.py`：约 100 行改动（新增方法 + CSS + JS）

---

## 测试验证

1. 运行测试用例，生成报告
2. 验证：
   - 业务方法块正确分组
   - 子步骤正确归属
   - 失败块默认展开
   - 折叠/展开交互正常