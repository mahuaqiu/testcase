# HTML 报告时间线视图重构实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 重构 `report_generator.py`，将报告从 AW 聚合结构改为时间线视图，按执行顺序展示每个步骤。

**Architecture:** 保持现有日志收集逻辑不变，仅重构渲染层。删除树形结构构建方法，新增时间线步骤渲染方法。

**Tech Stack:** Python 3.11, HTML/CSS (内嵌样式)

---

## 文件结构

| 文件 | 责任 |
|------|------|
| `common/report_generator.py` | 报告生成主文件，重构渲染逻辑 |
| `common/report_logger.py` | 日志收集器（保持不变） |

---

### Task 1: 分析现有代码，确定删除/保留的方法

**文件:**
- Read: `common/report_generator.py`（已在之前阅读）

**保留的方法：**
- `_clean_text_for_display()` - 清理 base64 数据
- `_clean_response_for_display()` - 清理响应数据
- `_format_duration()` - 格式化耗时显示
- `_get_failed_aw_steps()` - 提取失败步骤（需小改）
- `_build_screenshots_html()` - 构建截图区域（保留）

**删除的方法：**
- `_build_aw_tree()` - 构建树形结构（不再需要）
- `_render_aw_block()` - 渲染 AW 块（不再需要）
- `_render_aw_step()` - 渲染子步骤（改为时间线步骤）
- `_format_aw_title()` - 格式化 AW 标题（不再需要）
- `_format_step_title()` - 格式化步骤标题（改为时间线标题）

---

### Task 2: 实现辅助方法 - 用户颜色映射

**文件:**
- Modify: `common/report_generator.py`

- [ ] **Step 1: 在 HTMLReportGenerator 类中添加 `_get_user_color()` 方法**

在 `_format_duration()` 方法之后添加：

```python
@staticmethod
def _get_user_color(user_id: str) -> str:
    """根据用户 ID 返回标签颜色。

    Args:
        user_id: 用户 ID，如 "userA"、"userB"。

    Returns:
        颜色十六进制值，如 "#3b82f6"。
    """
    colors = {
        "userA": "#3b82f6",  # 蓝色
        "userB": "#22c55e",  # 绿色
        "userC": "#8b5cf6",  # 紫色
        "userD": "#f59e0b",  # 黄色
    }
    # 处理 _api 后缀的用户（如 userA_api）
    base_user_id = user_id.replace("_api", "")
    return colors.get(base_user_id, "#6b7280")  # 默认灰色
```

---

### Task 3: 实现辅助方法 - 时间线步骤标题格式化

**文件:**
- Modify: `common/report_generator.py`

- [ ] **Step 1: 在 `_get_user_color()` 之后添加 `_format_timeline_title()` 方法**

```python
@staticmethod
def _format_timeline_title(aw_name: str, method: str, args: Dict[str, Any]) -> str:
    """格式化时间线步骤标题，简化显示。

    Args:
        aw_name: AW 类名（如 LoginAW）。
        method: 方法名（如 do_login）。
        args: 调用参数。

    Returns:
        简化的标题，如 "登录系统" 或 "ocr_wait(text=\"登录\")"。
    """
    # 业务方法（do_*/should_*）：只显示方法名对应的中文描述
    if method.startswith(('do_', 'should_')):
        # 从方法名提取动作
        action = method.replace('do_', '').replace('should_', '')
        # 常见动作映射
        action_map = {
            'login': '登录系统',
            'logout': '退出登录',
            'join_as_host': '作为主持人入会',
            'join_as_guest': '作为访客入会',
            'leave': '离开会议',
            'admit_participant': '准入参会者',
            'create_meeting': '创建会议',
            'cancel_meeting': '取消会议',
            'set_waiting_room': '设置等候室',
            'login_success': '断言登录成功',
            'join_success': '断言入会成功',
            'in_waitingroom': '断言在等候室',
        }
        return action_map.get(action, method)

    # 原子操作：显示方法名和关键参数
    DISPLAY_ARGS = {
        "text", "label", "content", "image_path", "key", "url",
        "app_id", "x", "y", "from_x", "from_y", "to_x", "to_y",
        "duration_ms", "timeout", "index", "confidence", "name",
        "command", "page_index", "monitor"
    }

    filtered_args = {
        k: v for k, v in args.items()
        if k in DISPLAY_ARGS and v is not None
    }

    if not filtered_args:
        return method

    parts = []
    for k, v in filtered_args.items():
        if isinstance(v, str) and len(v) > 20:
            v = v[:17] + "..."
        parts.append(f'{k}="{v}"' if isinstance(v, str) else f"{k}={v}")

    return f"{method}({', '.join(parts)})"
```

---

### Task 4: 实现核心方法 - 渲染单个时间线步骤

**文件:**
- Modify: `common/report_generator.py`

- [ ] **Step 1: 在 `_format_timeline_title()` 之后添加 `_render_timeline_step()` 方法**

这是核心渲染方法，代码较长，完整实现：

```python
@staticmethod
def _render_timeline_step(log: Dict[str, Any], is_last: bool = False) -> str:
    """渲染单个时间线步骤。

    Args:
        log: 日志数据。
        is_last: 是否是最后一个步骤（用于样式）。

    Returns:
        HTML 字符串。
    """
    # 提取信息
    time_str = log.get("time", "")
    args = log.get("args", {})
    user_id = args.get("user_id", "")
    user_name = args.get("user_name", "")
    user_account = args.get("user_account", "")
    user_ip = args.get("user_ip", "")
    aw_name = log.get("aw_name", "")
    method = log.get("method", "")
    duration = log.get("duration_ms", 0)
    success = log.get("success", True)
    request_id = log.get("request_id", "")
    result = log.get("result", {})

    # 格式化
    duration_str = HTMLReportGenerator._format_duration(duration)
    user_color = HTMLReportGenerator._get_user_color(user_id)
    title = HTMLReportGenerator._format_timeline_title(aw_name, method, args)

    # 状态图标和样式
    status_icon = "✓" if success else "✗"
    status_color = "#22c55e" if success else "#ef4444"
    item_class = "success" if success else "failed expanded"
    bg_class = "" if success else "failed-step"

    # 用户信息行
    user_info_parts = []
    if user_name:
        user_info_parts.append(user_name)
    if user_account:
        user_info_parts.append(user_account)
    if user_ip:
        user_info_parts.append(user_ip)
    user_info_str = " · ".join(user_info_parts) if user_info_parts else user_id

    # 清理参数和响应用于显示
    clean_args = {k: v for k, v in args.items() if k not in (
        "user_id", "user_account", "user_name", "user_ip",
        "target_image", "image_base64", "screenshot", "error_screenshot"
    )}
    clean_result = HTMLReportGenerator._clean_response_for_display(result)

    # 构建展开详情
    detail_parts = []

    # request_id
    if request_id:
        detail_parts.append(f'<div class="detail-item"><strong>request_id:</strong> {request_id}</div>')

    # 错误信息（失败时）
    if not success:
        error_msg = result.get("error", "")
        if error_msg:
            detail_parts.append(f'''
            <div class="error-box">
                <div class="error-label">错误信息</div>
                <div class="error-text">{HTMLReportGenerator._clean_text_for_display(error_msg)}</div>
            </div>''')

    # 请求
    if clean_args:
        detail_parts.append(f'''
        <div class="detail-row">
            <div class="detail-half">
                <div class="detail-label">请求</div>
                <div class="detail-content">{clean_args}</div>
            </div>''')

    # 响应
    if clean_result:
        detail_parts.append(f'''
            <div class="detail-half">
                <div class="detail-label">响应</div>
                <div class="detail-content">{clean_result}</div>
            </div>
        </div>''')
    elif clean_args:
        detail_parts.append('</div>')

    # 截图（失败时）
    if not success:
        error_screenshot = result.get("error_screenshot", "")
        target_image = log.get("target_image", "")

        screenshots_html = ""
        if error_screenshot and len(error_screenshot) > 100:
            screenshots_html += f'''
            <div class="screenshot-item" onclick="showImage('{error_screenshot}')">
                <img src="data:image/png;base64,{error_screenshot}">
                <div class="screenshot-label">当前屏幕</div>
            </div>'''
        if target_image and len(target_image) > 100:
            screenshots_html += f'''
            <div class="screenshot-item" onclick="showImage('{target_image}')">
                <img src="data:image/png;base64,{target_image}">
                <div class="screenshot-label">目标图片</div>
            </div>'''

        if screenshots_html:
            detail_parts.append(f'''
            <div class="screenshots-row">
                <div class="screenshots-label">失败截图</div>
                <div class="screenshots-grid">{screenshots_html}</div>
            </div>''')

    detail_html = "".join(detail_parts)

    return f'''
    <div class="timeline-step {item_class}">
        <div class="step-header" onclick="toggleStep(this)">
            <span class="step-status" style="color:{status_color}">{status_icon}</span>
            <span class="step-user" style="background:{user_color}">{user_id}</span>
            <span class="step-time">{time_str}</span>
            <span class="step-duration" style="color:{status_color}">{duration_str}</span>
            <span class="step-divider"></span>
            <span class="step-user-info" style="color:{'#7f1d1d' if not success else '#9ca3af'}">{user_info_str}</span>
            <span class="step-title{' failed-text' if not success else ''}">{title}</span>
        </div>
        <div class="step-detail {'expanded' if not success else ''}">
            {detail_html}
        </div>
    </div>'''
```

---

### Task 5: 重构 generate() 方法 - 整合时间线渲染

**文件:**
- Modify: `common/report_generator.py`

- [ ] **Step 1: 重构 generate() 方法的步骤渲染部分**

找到 `generate()` 方法中调用 `_build_logs_html()` 的位置，替换为新的时间线渲染逻辑。

修改 `_build_logs_html()` 方法：

```python
@staticmethod
def _build_logs_html(logs: List[Dict[str, Any]]) -> str:
    """构建时间线步骤列表 HTML。

    Args:
        logs: 日志列表。

    Returns:
        HTML 字符串。
    """
    # 过滤 aw_call 类型日志，按时间排序
    aw_logs = [
        log for log in logs
        if log.get("type") == "aw_call" and not log.get("is_business_method", False)
    ]
    aw_logs.sort(key=lambda x: x.get("time") or "")

    if not aw_logs:
        return '<div class="empty-logs">暂无执行步骤</div>'

    steps_html = ""
    for i, log in enumerate(aw_logs):
        is_last = i == len(aw_logs) - 1
        steps_html += HTMLReportGenerator._render_timeline_step(log, is_last)

    return steps_html
```

---

### Task 6: 更新 HTML 样式和 JavaScript

**文件:**
- Modify: `common/report_generator.py`

- [ ] **Step 1: 在 generate() 方法的 HTML 模板中更新 CSS 样式**

替换现有样式，添加时间线视图专用样式。找到 `<style>` 标签，替换为：

```html
<style>
    * { box-sizing: border-box; }
    body {
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        background: #f8fafc;
        min-height: 100vh;
        margin: 0;
        padding: 24px;
    }
    .container { max-width: 1000px; margin: 0 auto; }

    /* 报告头部 */
    .header {
        background: linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%);
        border-radius: 16px;
        padding: 20px 24px;
        margin-bottom: 20px;
        box-shadow: 0 4px 20px rgba(34,197,94,0.1);
    }
    .header.failed {
        background: linear-gradient(135deg, #fef2f2 0%, #fee2e2 100%);
        box-shadow: 0 4px 20px rgba(239,68,68,0.1);
    }
    .header-content { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 16px; }
    .header-left { flex: 1; }
    .header h1 { margin: 0 0 4px 0; font-size: 20px; color: #166534; font-weight: 700; }
    .header.failed h1 { color: #dc2626; }
    .header h2 { margin: 0; font-size: 13px; color: #15803d; font-weight: 400; }
    .header.failed h2 { color: #b91c1c; }
    .header-right { display: flex; align-items: center; gap: 20px; }
    .status-badge {
        padding: 10px 20px;
        border-radius: 24px;
        font-weight: 600;
        font-size: 14px;
    }
    .status-passed { background: #22c55e; color: white; }
    .status-failed { background: #ef4444; color: white; }
    .header-meta { text-align: right; }
    .header-meta .duration { font-size: 18px; font-weight: 700; color: #166534; }
    .header.failed .header-meta .duration { color: #dc2626; }
    .header-meta .time { font-size: 12px; color: #6b7280; margin-top: 2px; }

    /* 失败提示 */
    .failed-steps {
        margin-top: 12px;
        padding: 10px 14px;
        background: white;
        border-radius: 8px;
        border-left: 4px solid #ef4444;
    }
    .failed-steps-title { font-weight: 600; color: #dc2626; margin-bottom: 6px; font-size: 13px; }
    .failed-steps-list { margin: 0; padding-left: 20px; color: #7f1d1d; font-size: 12px; }
    .failed-steps-list li { margin: 4px 0; }

    .error-box {
        margin-top: 12px;
        padding: 10px 14px;
        background: white;
        border-radius: 8px;
        border-left: 4px solid #ef4444;
        font-family: 'Consolas', monospace;
        font-size: 11px;
        color: #dc2626;
        white-space: pre-wrap;
        word-break: break-all;
        max-height: 120px;
        overflow: auto;
    }

    /* 时间线步骤 */
    .timeline-card {
        background: white;
        border-radius: 12px;
        padding: 12px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.04);
    }
    .timeline-title {
        font-size: 11px;
        color: #6b7280;
        padding: 6px 8px;
        font-weight: 600;
        border-bottom: 1px solid #e5e7eb;
    }

    .timeline-step {
        border-bottom: 1px solid #f3f4f6;
    }
    .timeline-step:last-child { border-bottom: none; }
    .timeline-step.failed-step { background: #fef2f2; }

    .step-header {
        padding: 10px 12px;
        cursor: pointer;
        display: flex;
        align-items: center;
        gap: 6px;
        font-size: 12px;
    }
    .step-header:hover { background: #f9fafb; }

    .step-status { font-size: 14px; font-weight: 600; }
    .step-user {
        color: white;
        padding: 2px 8px;
        border-radius: 4px;
        font-weight: 600;
        font-size: 11px;
    }
    .step-time { color: #6b7280; font-size: 11px; width: 65px; }
    .step-duration { font-size: 11px; }
    .step-divider {
        width: 1px;
        height: 14px;
        background: #d1d5db;
        margin-left: 4px;
    }
    .step-user-info { font-size: 11px; }
    .step-title {
        flex: 1;
        font-weight: 500;
        padding-left: 12px;
    }
    .step-title.failed-text { color: #dc2626; }

    /* 展开详情 */
    .step-detail {
        display: none;
        padding: 10px 12px;
        background: #f9fafb;
        border-top: 1px solid #e5e7eb;
    }
    .step-detail.expanded { display: block; }
    .timeline-step.failed-step .step-detail { background: #fef2f2; border-top-color: #fecaca; }

    .detail-item { font-size: 10px; color: #6b7280; margin-bottom: 6px; }
    .detail-label { font-size: 9px; color: #6b7280; font-weight: 600; margin-bottom: 2px; }
    .detail-content {
        background: white;
        padding: 6px;
        border-radius: 3px;
        font-family: 'Consolas', monospace;
        font-size: 10px;
        color: #4b5563;
    }

    .error-label { font-size: 9px; color: #dc2626; font-weight: 600; margin-bottom: 2px; }
    .error-text {
        background: white;
        padding: 6px;
        border-radius: 3px;
        font-family: 'Consolas', monospace;
        font-size: 10px;
        color: #dc2626;
    }

    .detail-row { display: flex; gap: 12px; margin-bottom: 8px; }
    .detail-half { flex: 1; }

    .screenshots-row { margin-top: 8px; }
    .screenshots-label { font-size: 9px; color: #6b7280; font-weight: 600; margin-bottom: 4px; }
    .screenshots-grid { display: flex; gap: 8px; }
    .screenshot-item {
        width: 100px;
        height: 60px;
        background: #e5e7eb;
        border-radius: 4px;
        cursor: pointer;
        position: relative;
        border: 1px solid #fecaca;
    }
    .screenshot-item img {
        width: 100%;
        height: 100%;
        object-fit: cover;
        border-radius: 4px;
    }
    .screenshot-label {
        position: absolute;
        bottom: 0;
        left: 0;
        right: 0;
        background: rgba(0,0,0,0.6);
        color: white;
        font-size: 9px;
        padding: 2px 4px;
        text-align: center;
        border-radius: 0 0 4px 4px;
    }

    /* 截图卡片 */
    .screenshots-card {
        background: white;
        border-radius: 16px;
        padding: 20px;
        margin-top: 20px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.04);
    }
    .screenshots-card h3 { margin: 0 0 12px 0; font-size: 14px; color: #374151; font-weight: 600; }
    .screenshots-grid-large { display: flex; flex-wrap: wrap; gap: 16px; }
    .screenshot-item-large {
        width: 200px;
        height: 130px;
        background: #e5e7eb;
        border-radius: 8px;
        cursor: pointer;
        text-align: center;
    }
    .screenshot-item-large img {
        width: 100%;
        height: 100%;
        object-fit: cover;
        border-radius: 8px;
        border: 2px solid #e5e7eb;
    }
    .screenshot-item-large .user-id { margin-top: 6px; font-size: 12px; color: #6b7280; }

    /* 弹窗 */
    .modal {
        display: none;
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0,0,0,0.9);
        z-index: 1000;
        cursor: zoom-out;
    }
    .modal.show { display: flex; align-items: center; justify-content: center; }
    .modal img { max-width: 95%; max-height: 95%; border-radius: 8px; }
    .modal-close { position: fixed; top: 20px; right: 30px; color: white; font-size: 40px; cursor: pointer; }

    .empty-logs { padding: 20px; text-align: center; color: #868e96; }
</style>
```

- [ ] **Step 2: 更新 JavaScript 交互函数**

替换 `<script>` 标签内容：

```html
<script>
    function showImage(base64) {
        document.getElementById('modal-img').src = 'data:image/png;base64,' + base64;
        document.getElementById('modal').classList.add('show');
    }

    function toggleStep(header) {
        const step = header.closest('.timeline-step');
        const detail = step.querySelector('.step-detail');
        detail.classList.toggle('expanded');
    }

    // 点击弹窗关闭
    document.getElementById('modal').addEventListener('click', function() {
        this.classList.remove('show');
    });
</script>
```

---

### Task 7: 更新 generate() 方法的 HTML 结构

**文件:**
- Modify: `common/report_generator.py`

- [ ] **Step 1: 更新 generate() 方法中的 HTML body 结构**

找到 HTML 模板的 body 部分，替换为：

```python
html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{case_name}</title>
    {CSS_STYLES}  <!-- 上一步定义的样式 -->
</head>
<body>
    <div class="container">
        <div class="header {'failed' if status == 'failed' else ''}">
            <div class="header-content">
                <div class="header-left">
                    <h1>{case_name}</h1>
                    {f'<h2>{case_title}</h2>' if case_title else ''}
                </div>
                <div class="header-right">
                    <span class="status-badge {'status-passed' if status == 'passed' else 'status-failed'}">
                        {'✓ 通过' if status == 'passed' else '✗ 失败'}
                    </span>
                    <div class="header-meta">
                        <div class="duration">{HTMLReportGenerator._format_duration(duration_ms)}</div>
                        <div class="time">{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</div>
                    </div>
                </div>
            </div>
            {failed_steps_html}
            {f'<div class="error-box">{error_msg}</div>' if error_msg else ''}
        </div>

        <div class="timeline-card">
            <div class="timeline-title">执行步骤</div>
            {logs_html}
        </div>

        {screenshots_html}
    </div>

    <div id="modal" class="modal">
        <span class="modal-close">&times;</span>
        <img id="modal-img" src="">
    </div>

    {JS_SCRIPT}  <!-- 上一步定义的 JavaScript -->

</body>
</html>"""
```

---

### Task 8: 删除废弃方法

**文件:**
- Modify: `common/report_generator.py`

- [ ] **Step 1: 删除不再需要的方法**

删除以下方法：
- `_build_aw_tree()` (约第 148-338 行)
- `_render_aw_block()` (约第 457-571 行)
- `_format_aw_title()` (约第 75-131 行)
- `_format_step_title()` (约第 341-380 行)
- 旧的 `_render_aw_step()` (约第 383-454 行)
- 旧的 `_build_logs_html()` (约第 972-1016 行)

---

### Task 9: 测试验证

**文件:**
- None（运行测试验证）

- [ ] **Step 1: 运行一个实际测试用例**

```bash
cd /Users/ma/Documents/testcase
source .venv/bin/activate
pytest testcases/web/waitingroom/test_waitingroom_001.py -v
```

- [ ] **Step 2: 查看生成的报告**

```bash
ls -lt report/ | head -2
```

打开最新的报告 HTML 文件，检查：
1. 步骤按时间线排列
2. 用户标签颜色正确
3. 点击展开显示详情
4. 失败步骤自动展开

---

### Task 10: 提交代码

- [ ] **Step 1: 提交重构后的代码**

```bash
git add common/report_generator.py
git commit -m "$(cat <<'EOF'
重构 HTML 报告为时间线视图

- 删除 AW 聚合结构，改为按时间顺序展示
- 每步紧凑显示：状态 + 用户 + 时间 + 耗时 + 姓名/手机/IP + 操作
- 点击展开显示 request_id、请求、响应、截图
- 失败步骤自动展开，红色背景高亮
- 用户标签颜色区分（userA 蓝色、userB 绿色）
EOF
)"
```

---

## 完成检查清单

- [ ] 报告按时间线显示所有步骤
- [ ] 用户信息（姓名、手机、IP）在每步外显
- [ ] request_id 在展开详情中显示
- [ ] 失败步骤自动展开并高亮
- [ ] 用户标签颜色正确区分
- [ ] 截图功能正常（点击放大）
- [ ] 头部失败提示区域保持原有结构