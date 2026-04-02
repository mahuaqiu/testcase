# 报告两层折叠结构实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现两层折叠结构：业务方法作为可折叠块，原子操作作为子步骤

**Architecture:** 通过 inspect 自动识别调用栈中的 do_*/should_* 方法作为 parent_aw，按 parent_aw 分组构建树形结构

**Tech Stack:** Python、inspect、HTML、CSS、JavaScript

---

## 文件结构

| 文件 | 改动类型 | 说明 |
|------|----------|------|
| `common/report_logger.py` | 修改 | 增加 parent_aw 参数 |
| `aw/base_aw.py` | 修改 | 新增 _find_parent_aw 方法，传递 parent_aw |
| `common/report_generator.py` | 修改 | 新增分组和渲染方法，更新 CSS 和 JS |

---

## 任务分解

### Task 1: 修改 report_logger.py 增加 parent_aw 参数

**Files:**
- Modify: `common/report_logger.py:101-151` (log_aw_call 方法)

- [ ] **Step 1: 修改 log_aw_call 方法签名**

在第 101 行，增加 `parent_aw` 参数：

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

- [ ] **Step 2: 在日志条目中记录 parent_aw**

在第 125-136 行的日志条目中增加 `parent_aw` 字段：

```python
log_entry = {
    "time": datetime.now().strftime("%H:%M:%S.%f")[:-3],
    "type": "aw_call",
    "aw_name": aw_name,
    "method": method,
    "args": args,
    "success": success,
    "result": result,
    "duration_ms": duration_ms,
    "target_image": target_image,
    "target_image_path": target_image_path,
    "parent_aw": parent_aw  # 新增
}
```

- [ ] **Step 3: 提交改动**

```bash
git add common/report_logger.py
git commit -m "feat(report): 日志增加 parent_aw 字段"
```

---

### Task 2: 修改 base_aw.py 增加 parent_aw 自动识别

**Files:**
- Modify: `aw/base_aw.py` (新增方法和修改调用)

- [ ] **Step 1: 导入 inspect 模块**

在文件顶部导入区域添加：

```python
import inspect
```

- [ ] **Step 2: 新增 _find_parent_aw 方法**

在 `_execute_with_log` 方法前（约第 44 行）添加：

```python
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

- [ ] **Step 3: 在 _execute_with_log 中调用 _find_parent_aw**

在同步执行模式的开头（约第 85 行后）添加：

```python
# 自动识别 parent_aw
parent_aw = self._find_parent_aw()
```

- [ ] **Step 4: 修改 log_aw_call 调用，传递 parent_aw**

在第 141-150 行的 `log_aw_call` 调用中增加 `parent_aw` 参数：

```python
logger.log_aw_call(
    aw_name=self._aw_name,
    method=method,
    args={"user_id": user_id, "user_account": user_account, "user_name": user_name, **log_args},
    success=success,
    result=full_result,
    duration_ms=duration_ms,
    target_image=target_image_base64,
    target_image_path=target_image_path,
    parent_aw=parent_aw,  # 新增
)
```

- [ ] **Step 5: 同样修改异常情况的 log_aw_call 调用**

在第 94-101 行的异常处理中也增加 `parent_aw` 参数：

```python
logger.log_aw_call(
    aw_name=self._aw_name,
    method=method,
    args=log_args,
    success=False,
    result={"error": str(e)},
    duration_ms=duration_ms,
    parent_aw=parent_aw,  # 新增
)
```

- [ ] **Step 6: 提交改动**

```bash
git add aw/base_aw.py
git commit -m "feat(aw): 自动识别 parent_aw 业务方法层级"
```

---

### Task 3: 新增报告分组方法 _build_aw_tree

**Files:**
- Modify: `common/report_generator.py` (新增方法)

- [ ] **Step 1: 在 _format_aw_title 方法后添加 _build_aw_tree 方法**

```python
@staticmethod
def _build_aw_tree(logs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """将日志按 parent_aw 分组构建树形结构。

    Args:
        logs: 原始日志列表。

    Returns:
        块列表，每个块包含业务方法信息和子步骤列表。
    """
    # 按 parent_aw 分组
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for log in logs:
        if log.get("type") != "aw_call":
            continue
        parent = log.get("parent_aw", "")
        if parent not in groups:
            groups[parent] = []
        groups[parent].append(log)

    # 构建业务方法块（parent_aw != "" 的日志属于某个业务方法）
    # 首先找出所有业务方法块
    business_blocks: Dict[str, Dict[str, Any]] = {}

    for parent_aw, steps in groups.items():
        if parent_aw == "":
            continue  # 顶层原子操作，后面处理

        # 从 parent_aw 解析 aw_name 和 method
        parts = parent_aw.rsplit(".", 1)
        if len(parts) != 2:
            continue
        aw_name, method = parts

        # 计算整体状态和耗时
        total_duration = sum(s.get("duration_ms", 0) for s in steps)
        all_success = all(s.get("success", True) for s in steps)

        # 从第一个步骤获取用户信息
        first_step = steps[0] if steps else {}
        args = first_step.get("args", {})
        user_info = {
            "user_id": args.get("user_id", ""),
            "user_name": args.get("user_name", ""),
            "user_account": args.get("user_account", ""),
        }

        business_blocks[parent_aw] = {
            "block_id": parent_aw,
            "aw_name": aw_name,
            "method": method,
            "user_info": user_info,
            "success": all_success,
            "duration_ms": total_duration,
            "steps": steps,
            "time": first_step.get("time", ""),
        }

    # 构建顶层块列表（parent_aw == "" 的原子操作 + 业务方法块）
    top_blocks: List[Dict[str, Any]] = []

    # 添加顶层原子操作（不属于任何业务方法）
    for log in groups.get("", []):
        aw_name = log.get("aw_name", "")
        method = log.get("method", "")
        block_id = f"{aw_name}.{method}"

        args = log.get("args", {})
        user_info = {
            "user_id": args.get("user_id", ""),
            "user_name": args.get("user_name", ""),
            "user_account": args.get("user_account", ""),
        }

        top_blocks.append({
            "block_id": block_id,
            "aw_name": aw_name,
            "method": method,
            "user_info": user_info,
            "success": log.get("success", True),
            "duration_ms": log.get("duration_ms", 0),
            "steps": [],  # 无子步骤
            "time": log.get("time", ""),
            "single_step": True,  # 标记为单步骤块
            "step_data": log,  # 保存原始日志数据
        })

    # 添加业务方法块
    for block_id, block in business_blocks.items():
        top_blocks.append(block)

    # 按时间排序
    top_blocks.sort(key=lambda b: b.get("time", ""))

    return top_blocks
```

- [ ] **Step 2: 提交改动**

```bash
git add common/report_generator.py
git commit -m "feat(report): 新增 _build_aw_tree 方法构建树形结构"
```

---

### Task 4: 新增渲染方法 _render_aw_block 和 _render_aw_step

**Files:**
- Modify: `common/report_generator.py` (新增方法)

- [ ] **Step 1: 添加 _format_step_title 辅助方法**

```python
@staticmethod
def _format_step_title(method: str, args: Dict[str, Any]) -> str:
    """格式化步骤标题，显示关键参数。

    Args:
        method: 方法名。
        args: 调用参数。

    Returns:
        格式化后的标题，如 "ocr_wait(text=\"登录\")"。
    """
    DISPLAY_ARGS = {
        "text", "label", "content", "image_path", "key", "url",
        "app_id", "x", "y", "from_x", "from_y", "to_x", "to_y",
        "duration_ms", "timeout", "index", "confidence"
    }

    HIDDEN_ARGS = {
        "platform", "user_id", "user_account", "user_name",
        "target_image", "image_base64", "screenshot"
    }

    filtered_args = {
        k: v for k, v in args.items()
        if k in DISPLAY_ARGS and k not in HIDDEN_ARGS
    }

    if not filtered_args:
        return f"{method}()"

    parts = []
    for k, v in filtered_args.items():
        if isinstance(v, str):
            parts.append(f'{k}="{v}"')
        else:
            parts.append(f"{k}={v}")

    return f"{method}({', '.join(parts)})"
```

- [ ] **Step 2: 添加 _render_aw_step 方法**

```python
@staticmethod
def _render_aw_step(step: Dict[str, Any]) -> str:
    """渲染单个原子操作步骤。

    Args:
        step: 步骤日志数据。

    Returns:
        HTML 字符串。
    """
    success = step.get("success", True)
    status_class = "success" if success else "failed"
    status_text = "✓" if success else "✗"

    method = step.get("method", "")
    args = step.get("args", {})
    step_title = HTMLReportGenerator._format_step_title(method, args)
    duration = step.get("duration_ms", 0)

    # 清理参数和结果用于详情显示
    clean_args = {k: v for k, v in args.items() if k not in ("user_id", "user_account", "user_name")}
    clean_result = HTMLReportGenerator._clean_response_for_display(step.get("result", {}))

    detail_parts = []
    if clean_args:
        detail_parts.append(f"参数: {clean_args}")
    detail_parts.append(f"结果: {clean_result}")
    detail_html = "<br>".join(detail_parts)

    # 失败时展示截图
    screenshots_html = ""
    if not success:
        result = step.get("result", {})
        error_screenshot = result.get("error_screenshot", "")
        target_image = step.get("target_image", "")

        screenshot_imgs = []
        if error_screenshot and len(error_screenshot) > 100:
            screenshot_imgs.append(f'''
                <div class="step-screenshot-wrapper">
                    <img src="data:image/png;base64,{error_screenshot}" class="step-screenshot" onclick="showImage('{error_screenshot}')">
                    <div class="step-screenshot-label">📸 当前屏幕</div>
                </div>''')
        if target_image and len(target_image) > 100:
            screenshot_imgs.append(f'''
                <div class="step-screenshot-wrapper">
                    <img src="data:image/png;base64,{target_image}" class="step-screenshot" onclick="showImage('{target_image}')">
                    <div class="step-screenshot-label">🎯 目标图片</div>
                </div>''')

        if screenshot_imgs:
            screenshots_html = f'<div class="step-screenshots">{"".join(screenshot_imgs)}</div>'

    return f'''
        <div class="aw-step">
            <span class="step-arrow">▶</span>
            <span class="step-title">{step_title}</span>
            <span class="step-status {status_class}">{status_text}</span>
            <span class="step-duration">{duration}ms</span>
            <div class="step-detail">{detail_html}</div>
            {screenshots_html}
        </div>'''
```

- [ ] **Step 3: 添加 _render_aw_block 方法**

```python
@staticmethod
def _render_aw_block(block: Dict[str, Any]) -> str:
    """渲染业务方法块（包含子步骤）。

    Args:
        block: 块数据。

    Returns:
        HTML 字符串。
    """
    success = block.get("success", True)
    item_class = "success" if success else "failed"
    expanded_class = "expanded" if not success else ""  # 失败块默认展开

    aw_name = block.get("aw_name", "")
    method = block.get("method", "")
    user_info = block.get("user_info", {})
    duration = block.get("duration_ms", 0)
    time_str = block.get("time", "")

    # 格式化标题
    block_title = f"{aw_name}.{method}()"

    # 格式化用户信息
    user_id_display = user_info.get("user_id", "") or "未知"
    user_name_display = user_info.get("user_name", "") or ""
    user_account_display = user_info.get("user_account", "") or ""

    # 单步骤块（顶层原子操作）
    if block.get("single_step"):
        step_data = block.get("step_data", {})
        step_html = HTMLReportGenerator._render_aw_step(step_data)
        return f'''
        <div class="aw-block {item_class} {expanded_class}">
            <div class="aw-header">
                <span class="aw-arrow">▶</span>
                <span class="log-time">{time_str}</span>
                <div class="log-type-wrapper">
                    <span class="log-type type-aw_call">AW</span>
                    <span class="log-user-id">{user_id_display}</span>
                    <span class="log-user-name">{user_name_display}</span>
                    <span class="log-user-account">{user_account_display}</span>
                </div>
                <span class="aw-title">{block_title}</span>
                <span class="aw-status {item_class}">{"✓" if success else "✗"}</span>
                <span class="aw-duration">{duration}ms</span>
            </div>
            <div class="aw-content">
                <div class="aw-steps">{step_html}</div>
            </div>
        </div>'''

    # 业务方法块（多步骤）
    steps = block.get("steps", [])
    steps_html = ""
    for step in steps:
        steps_html += HTMLReportGenerator._render_aw_step(step)

    status_text = "成功" if success else "失败"

    return f'''
    <div class="aw-block {item_class} {expanded_class}">
        <div class="aw-header">
            <span class="aw-arrow">▶</span>
            <span class="log-time">{time_str}</span>
            <div class="log-type-wrapper">
                <span class="log-type type-aw_call">AW</span>
                <span class="log-user-id">{user_id_display}</span>
                <span class="log-user-name">{user_name_display}</span>
                <span class="log-user-account">{user_account_display}</span>
            </div>
            <span class="aw-title">{block_title}</span>
            <span class="aw-status {item_class}">{status_text}</span>
            <span class="aw-duration">{duration}ms</span>
        </div>
        <div class="aw-content">
            <div class="aw-steps">{steps_html}</div>
        </div>
    </div>'''
```

- [ ] **Step 4: 提交改动**

```bash
git add common/report_generator.py
git commit -m "feat(report): 新增 _render_aw_block 和 _render_aw_step 方法"
```

---

### Task 5: 更新 CSS 样式

**Files:**
- Modify: `common/report_generator.py` (CSS 样式区域)

- [ ] **Step 1: 添加子步骤相关 CSS 样式**

在现有 `.aw-detail` 样式后添加：

```css
        /* 子步骤容器 */
        .aw-steps {{
            padding: 0 16px 12px 16px;
        }}

        /* 原子操作步骤 */
        .aw-step {{
            display: flex;
            align-items: center;
            padding: 8px 12px;
            margin: 4px 0;
            background: #f8f9fa;
            border-radius: 6px;
            cursor: pointer;
            gap: 8px;
            flex-wrap: wrap;
        }}
        .aw-step:hover {{ background: #e9ecef; }}

        .step-arrow {{
            color: #6c757d;
            font-size: 10px;
            transition: transform 0.2s;
        }}
        .aw-step.expanded .step-arrow {{ transform: rotate(90deg); }}

        .step-title {{
            font-weight: 500;
            color: #343a40;
            flex: 1;
        }}

        .step-status {{
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 11px;
        }}
        .step-status.success {{ background: #28a745; color: white; }}
        .step-status.failed {{ background: #dc3545; color: white; }}

        .step-duration {{
            color: #868e96;
            font-size: 11px;
        }}

        /* 步骤详情 */
        .step-detail {{
            display: none;
            width: 100%;
            margin-top: 8px;
            padding: 8px 12px;
            background: #fff;
            border-radius: 4px;
            font-family: 'Consolas', monospace;
            font-size: 12px;
            white-space: pre-wrap;
            word-break: break-all;
        }}
        .aw-step.expanded .step-detail {{ display: block; }}

        /* 步骤截图 */
        .step-screenshots {{
            width: 100%;
            margin-top: 8px;
            display: flex;
            flex-wrap: wrap;
            gap: 12px;
        }}
```

- [ ] **Step 2: 提交改动**

```bash
git add common/report_generator.py
git commit -m "feat(report): 添加子步骤 CSS 样式"
```

---

### Task 6: 更新 JavaScript 交互逻辑

**Files:**
- Modify: `common/report_generator.py` (JavaScript 区域)

- [ ] **Step 1: 添加原子操作步骤的折叠事件处理**

在现有 JavaScript 的 AW 块折叠事件处理后添加：

```javascript
        // 原子操作步骤折叠/展开
        document.querySelectorAll('.aw-step').forEach(step => {{
            step.addEventListener('click', function(e) {{
                if (e.target.closest('.step-detail') || e.target.closest('.step-screenshots')) return;
                this.classList.toggle('expanded');
            }});
        }});
```

- [ ] **Step 2: 提交改动**

```bash
git add common/report_generator.py
git commit -m "feat(report): 添加原子操作步骤折叠事件处理"
```

---

### Task 7: 修改 _build_logs_html 使用新的分组逻辑

**Files:**
- Modify: `common/report_generator.py` (_build_logs_html 方法)

- [ ] **Step 1: 替换 aw_call 处理逻辑，使用 _build_aw_tree**

找到 `_build_logs_html` 方法，修改为使用新的分组逻辑：

```python
@staticmethod
def _build_logs_html(logs: List[Dict[str, Any]]) -> str:
    """构建日志列表 HTML。"""
    items = []

    # 使用新的树形结构构建 AW 块
    aw_blocks = HTMLReportGenerator._build_aw_tree(logs)
    for block in aw_blocks:
        items.append(HTMLReportGenerator._render_aw_block(block))

    # 处理其他类型日志（step、error）
    for log in logs:
        log_type = log.get("type", "")
        time_str = log.get("time", "")

        if log_type == "step":
            items.append(f"""
            <div class="log-item">
                <span class="log-time">{time_str}</span>
                <span class="log-type type-step">步骤</span>
                <div class="log-content">
                    <div class="log-main">
                        <span class="log-name">{log.get('step', '')}</span>
                    </div>
                    {f'<div class="log-detail">{log.get("detail", "")}</div>' if log.get('detail') else ''}
                </div>
            </div>""")

        elif log_type == "error":
            items.append(f"""
            <div class="log-item failed">
                <span class="log-time">{time_str}</span>
                <span class="log-type type-error">错误</span>
                <div class="log-content">
                    <div class="log-main">
                        <span class="log-name" style="color: #dc3545;">{log.get('error', '')}</span>
                    </div>
                </div>
            </div>""")

    return "\n".join(items) if items else '<div class="log-item"><span style="color: #868e96;">暂无日志</span></div>'
```

- [ ] **Step 2: 提交改动**

```bash
git add common/report_generator.py
git commit -m "feat(report): 使用 _build_aw_tree 构建日志 HTML"
```

---

### Task 8: 验证和测试

**Files:**
- Test: 运行测试用例生成报告

- [ ] **Step 1: 运行测试用例**

```bash
source .venv/bin/activate
pytest testcases/web/login/test_login_success_001.py -v
```

预期：测试执行完成，在 `report/` 目录生成 HTML 报告。

- [ ] **Step 2: 打开报告验证效果**

检查：
- 业务方法块正确分组（如 `LoginAW.do_login` 包含多个子步骤）
- 子步骤正确归属（ocr_wait、ocr_input 等在 do_login 块内）
- 失败块默认展开
- 折叠/展开交互正常
- 原子操作步骤可展开查看详情

- [ ] **Step 3: 如有问题，修复并重新验证**

- [ ] **Step 4: 提交最终版本（如有修复）**

---

## 完成检查

- [ ] report_logger.py 增加 parent_aw 参数
- [ ] base_aw.py 自动识别 parent_aw
- [ ] report_generator.py 新增分组和渲染方法
- [ ] CSS 样式更新
- [ ] JavaScript 交互更新
- [ ] 视觉效果验证通过
- [ ] 所有改动已提交