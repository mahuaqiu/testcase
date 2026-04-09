---
name: testcase-create
description: "自动化测试用例生成。单Skill直接执行全流程，生成前用户评审，生成后复查验证。"
---

# 自动化测试用例生成

直接执行测试用例生成全流程，无需Agent调用。需要AW操作时调用 testcase-aw Skill。

---

## 执行流程

```
步骤1: 读取项目规范
    ↓
步骤2: 分析用户输入（步骤完整性校验）
    ↓
步骤3: 查找相似用例（优先复用）
    ↓
步骤4: AW匹配分析
    ↓
步骤5: 输出计划 → 用户评审确认
    ↓
步骤6: 生成测试代码
    ↓
步骤7: 复查验证
```

---

### 步骤 1：读取项目规范

**必须**先读取以下文件：

| 文件 | 读取目的 |
|------|----------|
| `AGENTS.md` | 架构、命名规范、编码约定、并行执行模式 |
| `aw/INDEX.md` | 已有AW资源索引 |
| `config.yaml` | hooks配置（setup/teardown自动处理） |

---

### 步骤 2：分析用户输入

解析用户的测试描述，提取关键信息：

#### 2.1 信息提取

| 检查项  | 必要性 | 示例 |
|------|--------|------|
| 测试端  | 必要 | web / windows / mac / ios / android |
| 测试步骤 | 必要 | STEP 1, STEP 2, STEP 3... |
| 期望结果 | 必要 | 每步的验证点 |
| 前置步骤 | 可选 | 如 "已登录"、"api预约会议" |
| 角色   | 可选 | 主持人、与会者 → 自动转换为 userA, userB |
| 清理步骤 | 可选 | 如 "关闭浏览器" |

#### 2.2 步骤完整性校验（强制执行）

**必须**输出校验表格，确保所有STEP都被解析：

```
步骤完整性校验:

用户输入步骤数: {N}
解析步骤数: {M}

| 用户STEP | 解析内容 | 覆盖状态 |
|----------|----------|----------|
| STEP 1 | 登录操作 + 断言成功 | ✅ |
| STEP 2 | 创建会议 + 断言成功 | ✅ |
| STEP 3 | ❌ 遗漏 | ❌ |

校验结论: ✅ 全部覆盖 / ❌ 有遗漏需补充
```

**常见遗漏场景**：

| 用户描述            | 易遗漏内容 | 正确拆分 |
|-----------------|------------|----------|
| "离会后重新入会"       | 离会、断言离会成功、重新入会、断言入会 | 4个独立操作 |
| "portal设置关闭等候室" | API设置操作 | 单独一行 |
| "A做某事，B做某事"     | 可能只解析一半 | 拆分为A操作、B操作两行 |

#### 2.3 角色命名自动转换

遵循AGENTS.md规范：

| 用户输入角色     | 标准命名        |
|------------|-------------|
| 主持人、主持人A、A | userA       |
| 与会者、与会者B   | userB       |
| 嘉宾C        | userC       |
| 嘉宾、观众      | userA、userB |

**不询问角色命名，自动转换**。

#### 2.4 操作类型自动识别

| 操作描述 | 自动识别 | 原因 |
|----------|----------|------|
| "api预约会议" | API | 明确写api |
| "api取消会议" | API | 明确写api |
| 其他UI描述 | UI | 默认UI操作 |

**不明确时才询问**（如"portal设置"可能是API或UI）。

---

### 步骤 3：查找相似用例（优先复用）

**在查INDEX.md之前**，先在目标目录查找相似用例。

#### 3.1 查找范围与数量限制

使用 Glob 工具查找测试文件，**限制数量避免上下文溢出**：

```
优先级 1: 目标目录（最多3个）
优先级 2: 隔壁目录（最多2个）
```

**执行策略**：

```python
# 优先查找目标目录（按修改时间排序，取最新2个）
Glob(pattern="testcases/{平台}/{模块}/test_*.py")
# 结果按 modification time 排序，取前2个

# 目标目录匹配不足时，查隔壁目录（取最新2个）
Glob(pattern="testcases/{平台}/*/test_*.py")
# 结果按 modification time 排序，取前2个
```

**总数量限制**：最多读取 4 个相似用例（2个目标目录 + 2个隔壁目录）

#### 3.2 匹配逻辑

逐步骤对比，寻找可复用的步骤模式：

| 对比维度 | 匹配条件 |
|----------|----------|
| 操作类型 | UI/API 一致 |
| 操作对象 | 登录/入会/离会/准入等一致 |
| 角色 | 单用户/多用户一致 |
| 并行标识 | 是否并行一致 |

**输出步骤复用分析**：

```markdown
| 用户STEP | 相似用例步骤 | 可复用AW方法 | 复用状态 |
|----------|--------------|--------------|----------|
| STEP 1: 并行登录 | test_waitingroom_switch_001:24-26 | LoginAW.do_login | ✅ 可复用 |
| STEP 2: API创建会议 | test_waitingroom_switch_001:29-32 | MeetingManageAW.do_create_meeting | ✅ 可复用 |
| STEP 3: 主持人入会 | test_waitingroom_switch_001:35 | MeetingJoinAW.do_join_as_host | ✅ 可复用 |
```

#### 3.3 复用决策

**按步骤匹配，不计算整体相似度**：

| 步骤匹配情况 | 处理方式 |
|--------------|----------|
| 完全匹配 | 直接复用已有用例的AW调用模式 |
| 部分匹配 | 复用匹配步骤，补充缺失部分 |
| 无匹配 | 正常AW匹配流程 |

**复用优先级**：先查目标目录，再查隔壁目录，最后查 INDEX.md。

---

### 步骤 4：AW匹配分析

结合相似用例复用 + INDEX.md匹配：

#### 4.1 匹配优先级

| 优先级 | 匹配类型 | 处理方式 |
|--------|----------|----------|
| 1 | 完全匹配 | 直接使用已有AW方法 |
| 2 | 部分匹配 | 扩展已有AW（调用 testcase-aw） |
| 3 | 无匹配 | 新建AW（调用 testcase-aw） |

#### 4.2 输出匹配表格

```markdown
| 用户STEP | AW类 | 方法 | 匹配状态 |
|----------|------|------|----------|
| STEP 1: 登录 | LoginAW | do_login | ✅ 已有 |
| STEP 2: 创建会议 | MeetingManageAW | do_create_meeting | ✅ 已有 |
| STEP 3: 新操作 | - | - | ⚠️ 需新建 |
```

#### 4.3 需要AW操作时

发现需要新增/扩展AW时，调用 testcase-aw Skill：

```
Skill(skill="testcase-aw", args="需要新建 {业务}AW，{平台}端")
```

---

### 步骤 5：输出计划，用户评审

**生成完整计划后，必须让用户确认**。

#### 5.1 计划输出格式

```markdown
# 测试用例生成计划

## 基本信息
- 测试文件: testcases/{平台}/{模块}/test_{功能}_{场景}_{编号}.py
- 测试端: {平台}
- 用户资源: {"userA": "{平台}", "userB": "{平台}"}

## 步骤与AW映射
| 用户STEP | AW方法 | 操作类型 | 并行标识 | 状态 |
|----------|--------|----------|----------|------|
| STEP 1 | LoginAW.do_login | UI | - | ✅ 已有 |
| STEP 2 | MeetingManageAW.do_create_meeting | API | - | ✅ 已有 |
| STEP 3 | XxxAW.do_xxx | UI | parallel | ⚠️ 需新建 |

## 需要新增/扩展的AW
| AW类 | 方法 | 平台 | 文件路径 |
|------|------|------|----------|
| XxxAW | do_xxx | web | aw/web/xxx_aw.py |

## hooks自动处理
- setup: start_app（自动执行，无需编写）
- teardown: stop_app（自动执行，无需编写）

## 相似用例复用
- 复用 test_login_001.py 的登录流程引用模式
```

#### 5.2 用户确认

使用 AskUserQuestion：

```
问题: "请评审以上生成计划，确认是否执行？"
选项:
1. 确认执行
2. 需要修改（请在Other说明修改内容）
3. 取消
```

**用户选择"确认执行"后才进入步骤6**。

---

### 步骤 6：生成测试代码

用户确认后执行代码生成。

#### 6.1 测试用例模板

基于实际用例结构，标准模板如下：

```python
"""
{用例标题}测试用例。

测试场景: {场景详细描述}
"""

import pytest

from common.parallel import parallel


@pytest.mark.users({"userA": "{平台}", "userB": "{平台}"})
class TestClass:
    """{用例标题}测试。"""

    def test_{功能}_{场景}_{编号}(self, users):
        """测试{功能}，验证{结果}。"""
        userA = users["userA"]
        userB = users["userB"]
        userA_api = users["userA_api"]

        # 步骤 1: 并行登录
        with parallel():
            userA.do_login()
            userB.do_login()

        # 步骤 2: API 创建会议
        meeting = userA_api.do_create_meeting(
            subject="{会议主题}",
            waiting_room=True
        )

        # 步骤 3: 主持人入会
        userA.do_join_as_host(meeting)

        # 步骤 4: 与会者入会
        userB.do_join_as_guest(meeting)

        # 步骤 5: 并行断言入会状态
        with parallel():
            userA.should_join_success()
            userB.should_in_waitingroom()

        # 步骤 6: 准入与会者
        userA.do_admit_participant()
        userB.should_join_success()
```

#### 6.2 模板要点

| 要点 | 规范 | 示例 |
|------|------|------|
| 文件开头 | Docstring描述测试场景 | `"""等候室开关功能测试用例..."""` |
| 导入顺序 | pytest → 项目模块 | `import pytest` 然后 `from common.parallel import parallel` |
| 用户标记 | `@pytest.mark.users()` | `{"userA": "web", "userB": "web"}` |
| API用户 | 自动创建 `_api` 实例 | `userA_api = users["userA_api"]` |
| 步骤注释 | 每个步骤标注编号 | `# 步骤 1: 并行登录` |
| 并行操作 | `with parallel():` 包裹 | 并行登录、并行断言 |
| 断言分离 | 验证步骤不在并行块内 | 先操作后断言 |

#### 6.3 生成AW代码（需要时）

如果计划中标注需新建/扩展AW：
1. 先调用 testcase-aw Skill 完成AW生成
2. 再生成测试用例引用

#### 6.4 更新INDEX.md

新增/扩展AW后，更新 `aw/INDEX.md`：

```markdown
### XxxAW

> 文件路径：`aw/{平台}/xxx_aw.py`
> 功能概述：{业务概述}

| 方法 | 说明 |
|------|------|
| `do_xxx()` | 执行xxx操作 |
| `should_xxx_success()` | 断言xxx成功 |
```

---

### 步骤 7：复查验证

**生成完成后必须执行复查**。

#### 7.1 步骤覆盖验证

对比用户输入STEP与代码实现：

```markdown
| 用户STEP | 代码实现 | 覆盖状态 |
|----------|----------|----------|
| STEP 1 | userA.do_login() + should_login_success() | ✅ |
| STEP 2 | userA_api.do_create_meeting() | ✅ |
```

**遗漏时自动补充**。

#### 7.2 hooks 冲突验证

检查测试代码中的清理操作是否与 `config.yaml` 的 `hooks.teardown` 配置重复，重复则移除并标注 `# 已由 hooks.teardown 自动处理`。

#### 7.3 编码规范验证

| 检查项 | 规范要求 | 处理方式 |
|--------|----------|----------|
| 文件命名 | test_{功能}_{场景}_{编号}.py | 不符合则修正 |
| 类命名 | TestClass | 不符合则修正 |
| 方法命名 | test_{文件名} | 不符合则修正 |
| AW引用 | from aw.{平台}.{业务}_aw import XxxAW | 检查路径正确 |
| Docstring | 中文注释 | 缺失则补充 |

#### 7.3 INDEX.md同步验证

检查：
- 新增AW是否已添加到INDEX.md
- 方法列表是否完整

#### 7.4 复查结果输出

**通过**：
```
✅ 复查通过
- 步骤覆盖：{N}/{N} 用户STEP全部覆盖
- hooks冲突：无重复清理操作
- 编码规范：命名、格式符合AGENTS.md
- INDEX.md：已同步更新
```

**发现问题**：
```
⚠️ 发现问题，已修正：
- 遗漏STEP 3断言 → 已补充 should_xxx_success()
- hooks冲突：user.stop_app() 与 teardown.stop_app 重复 → 已移除
- 文件命名不规范 → 已修正为 test_xxx_001.py
- INDEX.md未更新 → 已补充XxxAW记录
```

---

## 核心原则

1**优先复用相似用例**：查INDEX.md前先查同目录用例
2**用户评审前置**：生成代码前必须让用户确认计划
3**生成后复查**：步骤覆盖、编码规范、INDEX.md同步
4**需要AW时调用 testcase-aw**：AW操作专用Skill
5**遵循命名规范**：详见AGENTS.md

---

## 命名规范速查

| 类型 | 命名规则 | 示例 |
|------|----------|------|
| AW文件 | {业务名}_aw.py | login_aw.py |
| AW类 | {业务名}AW | LoginAW |
| AW方法 | do_{动作} / should_{期望} | do_login() |
| 测试文件 | test_{功能}_{场景}_{编号}.py | test_login_success_001.py |
| 测试类 | TestClass | 固定名称 |
| 测试方法 | test_{文件名} | test_login_success_001 |