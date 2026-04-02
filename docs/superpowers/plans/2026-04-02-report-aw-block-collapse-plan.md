# 报告 AW 分块折叠展示实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将每个 AW 方法调用改为可折叠块，折叠显示精简信息，展开显示详情，失败块默认展开。

**Architecture:** 纯前端实现，修改 `report_generator.py` 的 HTML 生成逻辑，添加 CSS 样式和 JavaScript 事件处理，无后端逻辑变化。

**Tech Stack:** Python HTML 生成、CSS、JavaScript

---

## 文件结构

| 文件 | 改动类型 | 说明 |
|------|----------|------|
| `common/report_generator.py` | 修改 | HTML 结构、CSS 样式、JavaScript 逻辑 |

---

## 任务分解

### Task 1: 添加 CSS 样式

**Files:**
- Modify: `common/report_generator.py:86-272` (CSS 样式区域)

- [ ] **Step 1: 在现有 CSS 后添加新样式**

在 `<style>` 标签内，现有样式后添加：

```css
        /* AW 块容器 */
        .aw-block {{
            margin: 8px 0;
            border-radius: 8px;
            background: white;
            border: 1px solid #e9ecef;
            transition: all 0.2s;
        }}
        .aw-block:hover {{ background: #f8f9fa; }}
        .aw-block.failed {{
            border-left: 4px solid #dc3545;
            background: #fff5f5;
        }}
        .aw-block.success {{ border-left: 4px solid #28a745; }}

        /* 折叠标题 */
        .aw-header {{
            display: flex;
            align-items: center;
            padding: 12px 16px;
            cursor: pointer;
            gap: 12px;
        }}
        .aw-arrow {{
            color: #6c757d;
            font-size: 12px;
            transition: transform 0.2s;
        }}
        .aw-block.expanded .aw-arrow {{ transform: rotate(90deg); }}
        .aw-title {{
            font-weight: 500;
            color: #343a40;
            flex: 1;
        }}
        .aw-status {{
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 12px;
        }}
        .aw-status.success {{ background: #28a745; color: white; }}
        .aw-status.failed {{ background: #dc3545; color: white; }}
        .aw-duration {{ color: #868e96; font-size: 12px; }}

        /* 展开内容 */
        .aw-content {{
            display: none;
            padding: 12px 16px;
            border-top: 1px solid #e9ecef;
        }}
        .aw-block.expanded .aw-content {{ display: block; }}
        .aw-detail {{
            background: #f8f9fa;
            padding: 10px 12px;
            border-radius: 6px;
            font-family: 'Consolas', monospace;
            font-size: 12px;
        }}
```

位置：在 `.modal-close` 样式后（约第 272 行），`</style>` 标签前。

- [ ] **Step 2: 验证 CSS 语法正确**

检查双花括号 `{{}}` 转义正确（Python f-string 要求）。

- [ ] **Step 3: 提交 CSS 样式改动**

```bash
git add common/report_generator.py
git commit -m "feat(report): 添加 AW 分块折叠 CSS 样式"
```

---

### Task 2: 添加 JavaScript 逻辑

**Files:**
- Modify: `common/report_generator.py:299-304` (JavaScript 区域)

- [ ] **Step 1: 在现有 JavaScript 后添加折叠事件处理**

在现有 `<script>` 标签内，`showImage` 函数后添加：

```javascript
        // AW 块折叠/展开
        document.querySelectorAll('.aw-header').forEach(header => {{
            header.addEventListener('click', function() {{
                const block = this.closest('.aw-block');
                block.classList.toggle('expanded');
            }});
        }});
```

位置：在 `}}`（showImage 函数结束）后，`</script>` 标签前。

- [ ] **Step 2: 验证 JavaScript 语法正确**

检查花括号 `{{}}` 转义正确。

- [ ] **Step 3: 提交 JavaScript 改动**

```bash
git add common/report_generator.py
git commit -m "feat(report): 添加 AW 块折叠/展开事件处理"
```

---

### Task 3: 添加参数格式化辅助方法

**Files:**
- Modify: `common/report_generator.py` (新增方法)

- [ ] **Step 1: 在 `_clean_response_for_display` 方法后添加 `_format_aw_title` 方法**

在第 54 行后添加：

```python
    @staticmethod
    def _format_aw_title(aw_name: str, method: str, args: Dict[str, Any]) -> str:
        """格式化 AW 标题，显示关键参数。

        Args:
            aw_name: AW 类名。
            method: 方法名。
            args: 调用参数。

        Returns:
            格式化后的标题，如 "LoginAW.do_login(text=\"登录\")"。
        """
        # 需要显示的参数名（复用 report_logger.py 的逻辑）
        DISPLAY_ARGS = {
            "text", "label", "content", "image_path", "key", "url",
            "app_id", "x", "y", "from_x", "from_y", "to_x", "to_y",
            "duration_ms", "timeout", "index", "confidence"
        }

        # 移除用户信息字段（已在折叠标题中显示）
        HIDDEN_ARGS = {
            "platform", "user_id", "user_account", "user_name",
            "target_image", "image_base64", "screenshot"
        }

        # 过滤参数
        filtered_args = {
            k: v for k, v in args.items()
            if k in DISPLAY_ARGS and k not in HIDDEN_ARGS
        }

        # 格式化参数
        if not filtered_args:
            return f"{aw_name}.{method}()"

        parts = []
        for k, v in filtered_args.items():
            if isinstance(v, str):
                parts.append(f'{k}="{v}"')
            else:
                parts.append(f"{k}={v}")

        return f"{aw_name}.{method}({', '.join(parts)})"
```

- [ ] **Step 2: 提交辅助方法改动**

```bash
git add common/report_generator.py
git commit -m "feat(report): 添加 AW 标题参数格式化方法"
```

---

### Task 4: 重构 aw_call 日志 HTML 结构

**Files:**
- Modify: `common/report_generator.py:340-442` (_build_logs_html 方法中的 aw_call 处理，约在文件中部查找 `elif log_type == "aw_call":`)

- [ ] **Step 1: 修改 aw_call 类型日志的 HTML 结构**

在 `_build_logs_html` 方法中找到 `elif log_type == "aw_call":` 处理代码块，替换为新的折叠块结构：

```python
            elif log_type == "aw_call":
                success = log.get("success", False)
                item_class = "success" if success else "failed"
                status_class = "success" if success else "failed"
                status_text = "成功" if success else "失败"

                # 失败块默认展开
                expanded_class = "expanded" if not success else ""

                # 格式化用户信息
                args = log.get("args", {})
                user_id = args.get("user_id", "")
                user_account = args.get("user_account", "")
                user_name = args.get("user_name", "")
                user_id_display = user_id if user_id else "未知"
                user_name_display = user_name if user_name else ""
                user_account_display = user_account if user_account else ""

                # 格式化标题（带关键参数）
                aw_title = HTMLReportGenerator._format_aw_title(
                    log.get("aw_name", ""),
                    log.get("method", ""),
                    args
                )

                # 清理参数用于详情显示
                clean_args = {k: v for k, v in args.items() if k not in ("user_id", "user_account", "user_name")}
                clean_result = HTMLReportGenerator._clean_response_for_display(log.get("result", {}))

                # 构建参数和结果详情
                detail_parts = []
                if clean_args:
                    detail_parts.append(f"参数: {clean_args}")
                detail_parts.append(f"结果: {clean_result}")
                detail_html = "<br>".join(detail_parts)

                # 失败时展示截图
                screenshots_html = ""
                if not success:
                    result = log.get("result", {})
                    error_screenshot = result.get("error_screenshot", "")
                    target_image = log.get("target_image", "")

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
                        screenshots_html = f'<div class="aw-screenshots" style="margin-top: 10px; display: flex; flex-wrap: wrap; gap: 12px;">{"".join(screenshot_imgs)}</div>'

                items.append(f"""
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
                    <span class="aw-title">{aw_title}</span>
                    <span class="aw-status {status_class}">{status_text}</span>
                    <span class="aw-duration">{log.get('duration_ms', 0)}ms</span>
                </div>
                <div class="aw-content">
                    <div class="aw-detail">{detail_html}</div>
                    {screenshots_html}
                </div>
            </div>""")
```

- [ ] **Step 2: 验证改动正确**

检查：
- 成功块无 `expanded` 类，失败块有
- 用户信息正确显示在 `.log-type-wrapper` 中
- 标题使用 `_format_aw_title` 格式化
- 截图在 `.aw-content` 内

- [ ] **Step 3: 提交 aw_call 结构改动**

```bash
git add common/report_generator.py
git commit -m "feat(report): 重构 aw_call 日志为可折叠块结构"
```

---

### Task 5: 验证视觉效果

**Files:**
- Test: 运行现有测试用例生成报告

- [ ] **Step 1: 运行一个测试用例**

```bash
source .venv/bin/activate
pytest testcases/web/waitingroom/test_waitingroom_switch_001.py -v
```

预期：测试执行完成，在 `report/` 目录生成 HTML 报告。

- [ ] **Step 2: 打开报告验证视觉效果**

```bash
open report/<timestamp>/test_waitingroom_switch_001.html
```

检查：
- AW 调用显示为可折叠块
- 成功块默认折叠，点击可展开
- 失败块默认展开，点击可折叠
- 箭头旋转效果正确
- 参数在标题中显示

- [ ] **Step 3: 如有问题，修复并重新验证**

如果发现 CSS 或 JavaScript 问题，修复后重新运行测试。

- [ ] **Step 4: 提交最终版本（如有修复）**

```bash
git add common/report_generator.py
git commit -m "fix(report): 修复折叠展示细节问题"
```

---

## 完成检查

- [ ] CSS 样式正确添加
- [ ] JavaScript 事件处理正确添加
- [ ] 参数格式化方法正确实现
- [ ] aw_call 日志结构正确重构
- [ ] 视觉效果验证通过
- [ ] 所有改动已提交