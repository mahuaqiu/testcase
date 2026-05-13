# HTML 测试报告重构设计文档

## 背景

当前报告按 AW（业务操作类）聚合显示，结构为：
```
LoginAW.do_login()
  ├─ ocr_wait()
  ├─ ocr_click()
MeetingAW.do_join()
  ├─ activate_window()
```

**问题**：
1. 按用户执行顺序阅读不直观，需要在不同 AW 块之间跳转
2. 用户信息（姓名、手机、IP）显示不醒目
3. request_id 隐藏在深层，难以定位问题
4. 步骤过多时报告很长，AW 聚合结构不够紧凑

## 设计目标

重构为**时间线视图**：按执行时间顺序展示每个操作步骤，清晰显示用户、操作、结果。

## 最终设计

### 头部区域（保持原有结构）

- 用例名称、标题
- 状态徽章（通过/失败）
- 总耗时、执行时间

**失败时额外显示**：
- 失败步骤列表
- 错误堆栈信息

### 步骤列表（时间线）

每一步紧凑显示，布局为：

```
状态 + 用户标签 + 时间 + 耗时 + 姓名/手机/IP + 操作名
```

示例：
```
✓ userA 00:01:02 2.3s | 张三 · 13800138000 · 192.168.0.102 登录系统
```

**点击展开详情**：
- request_id
- 错误信息（失败时）
- 请求内容
- 响应内容
- 失败截图（失败时）

### 用户标签颜色区分

- userA：蓝色 (#3b82f6)
- userB：绿色 (#22c55e)
- userC：紫色 (#8b5cf6)
- 失败步骤：红色背景高亮，自动展开

## 技术实现要点

### 1. 日志结构调整

保持 `ReportLogger` 现有日志格式，`report_generator.py` 重构渲染逻辑：

- 不再按 `parent_aw` 聚合构建树形结构
- 直接按时间排序所有 `aw_call` 类型日志
- 每条日志渲染为独立步骤行

### 2. 步骤渲染逻辑

```python
def _render_timeline_step(log: Dict[str, Any]) -> str:
    """渲染单个时间线步骤。"""
    # 提取信息
    time = log.get("time", "")
    user_id = log.get("args", {}).get("user_id", "")
    user_name = log.get("args", {}).get("user_name", "")
    user_account = log.get("args", {}).get("user_account", "")
    user_ip = log.get("args", {}).get("user_ip", "")
    method = log.get("method", "")
    duration = log.get("duration_ms", 0)
    success = log.get("success", True)
    request_id = log.get("request_id", "")

    # 渲染一行
    ...

    # 渲染展开详情
    ...
```

### 3. 用户标签颜色映射

```python
def _get_user_color(user_id: str) -> str:
    """根据用户 ID 返回颜色。"""
    colors = {
        "userA": "#3b82f6",  # 蓝色
        "userB": "#22c55e",  # 绿色
        "userC": "#8b5cf6",  # 紫色
        "userD": "#f59e0b",  # 黄色
    }
    return colors.get(user_id, "#6b7280")  # 默认灰色
```

### 4. 失败步骤处理

- 失败步骤自动添加 `expanded` class
- 背景使用红色 (`#fef2f2`)
- 展开详情包含错误信息和截图

### 5. 文件修改范围

| 文件 | 改动 |
|------|------|
| `common/report_generator.py` | 重构 `generate()` 方法，删除 `_build_aw_tree()`、`_render_aw_block()`，新增 `_render_timeline_step()` |
| `common/report_logger.py` | 保持不变 |

## 预览

最终设计预览文件：`.superpowers/brainstorm/61162-1778690155/final-design.html`

## 风险评估

- **改动范围**：仅 `report_generator.py`，不影响日志收集逻辑
- **兼容性**：新报告格式，不影响测试执行流程
- **风险等级**：低，仅显示层重构