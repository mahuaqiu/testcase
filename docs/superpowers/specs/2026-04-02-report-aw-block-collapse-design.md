# 报告 AW 分块折叠展示设计

## 背景

当前 HTML 报告中，每个 AW 调用步骤都以单独一行展示，导致一个用例执行下来页面很长，需要滚动查看。用户希望按 AW 方法分块展示，默认折叠，点击展开，失败的步骤默认展开以便快速定位问题。

## 目标

将每个 AW 方法调用（如 `LoginAW.do_login()`）作为一个可折叠块：
- 折叠时显示精简信息：时间、AW 名称、关键参数、状态、耗时
- 展开时显示详情：参数、结果、失败截图（如有）
- 失败块默认展开，成功块默认折叠
- 点击整行展开/折叠

## 设计

### 改动范围

仅修改 `common/report_generator.py`，改动点：

1. `_build_logs_html` 方法 - 修改 aw_call 类型日志的 HTML 结构
2. CSS 样式 - 新增折叠/展开相关样式
3. JavaScript - 新增点击事件处理

其他日志类型（step、error）保持不变，worker_call 继续隐藏。

### HTML 结构

每个 AW 调用改为可折叠块：

```html
<div class="aw-block expanded">  <!-- 失败时默认加 expanded，成功时不加 -->
  <div class="aw-header">
    <span class="aw-arrow">▶</span>
    <span class="log-time">09:30:15</span>
    <span class="aw-title">LoginAW.do_login(text="登录")</span>
    <span class="aw-status success">✓</span>
    <span class="aw-duration">152ms</span>
  </div>
  <div class="aw-content">
    <div class="aw-detail">参数: {...}<br>结果: {...}</div>
    <!-- 失败时的截图 -->
    <div class="aw-screenshots">
      <div class="step-screenshot-wrapper">
        <img src="data:image/png;base64,...">
        <div class="step-screenshot-label">📸 当前屏幕</div>
      </div>
      <div class="step-screenshot-wrapper">
        <img src="data:image/png;base64,...">
        <div class="step-screenshot-label">🎯 目标图片</div>
      </div>
    </div>
  </div>
</div>
```

**参数格式化**：
- 从 `args` 中提取关键参数（复用 `report_logger.py` 的 `_DISPLAY_ARGS`）
- 格式化为 `text="登录", timeout=5` 形式
- 移除 `user_id`、`user_account`、`user_name`（已在用户信息区显示）

**失败截图**：
- 仅失败块显示截图
- 当前屏幕截图和目标图片并排显示
- 点击截图调用现有 `showImage` 函数查看大图

### CSS 样式

新增样式：

```css
/* AW 块容器 */
.aw-block {
  margin: 8px 0;
  border-radius: 8px;
  background: white;
  border: 1px solid #e9ecef;
  transition: all 0.2s;
}

.aw-block:hover {
  background: #f8f9fa;
}

.aw-block.failed {
  border-left: 4px solid #dc3545;
  background: #fff5f5;
}

.aw-block.success {
  border-left: 4px solid #28a745;
}

/* 折叠标题 */
.aw-header {
  display: flex;
  align-items: center;
  padding: 12px 16px;
  cursor: pointer;
  gap: 12px;
}

.aw-arrow {
  color: #6c757d;
  font-size: 12px;
  transition: transform 0.2s;
}

.aw-block.expanded .aw-arrow {
  transform: rotate(90deg);
}

.aw-title {
  font-weight: 500;
  color: #343a40;
  flex: 1;
}

.aw-status {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
}

.aw-status.success { background: #28a745; color: white; }
.aw-status.failed { background: #dc3545; color: white; }

.aw-duration {
  color: #868e96;
  font-size: 12px;
}

/* 展开内容 */
.aw-content {
  display: none;
  padding: 12px 16px;
  border-top: 1px solid #e9ecef;
}

.aw-block.expanded .aw-content {
  display: block;
}

.aw-detail {
  background: #f8f9fa;
  padding: 10px 12px;
  border-radius: 6px;
  font-family: 'Consolas', monospace;
  font-size: 12px;
}
```

**关键设计**：
- 箭头用 CSS `transform: rotate(90deg)` 实现展开旋转效果
- 失败块红色左边框 + 浅红背景
- 成功块绿色左边框
- 点击区域为整个 `.aw-header`

### JavaScript 逻辑

新增点击事件处理：

```javascript
document.querySelectorAll('.aw-header').forEach(header => {
  header.addEventListener('click', function() {
    const block = this.closest('.aw-block');
    block.classList.toggle('expanded');
  });
});
```

**实现细节**：
- 事件绑定到 `.aw-header`
- 点击时切换 `expanded` 类
- 失败块后端渲染时已带 `expanded` 类，所以默认展开
- 用户可手动折叠失败的块

### 用户信息显示

保留现有用户信息显示逻辑：
- 折叠标题行中显示用户信息（复用现有的 `.log-type-wrapper` 结构）
- 用户信息在 AW 标签旁边，格式：`AW [userA - 张三(account123)]`

### 影响范围

- `common/report_generator.py`：约 60 行改动（HTML 结构 + CSS + JS）
- 不影响 `common/report_logger.py`
- 不影响其他日志类型的显示

### 兼容性

- 向后兼容：AW 调用日志结构变化，但数据格式不变
- 现有截图功能继续工作（`showImage` 函数）
- 现有失败步骤提取逻辑继续工作（`_get_failed_aw_steps`）